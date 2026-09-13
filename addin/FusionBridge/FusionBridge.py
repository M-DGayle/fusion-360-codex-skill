"""Fusion main-thread dispatcher. Loaded by Fusion as a persistent add-in."""
import base64
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import secrets
import threading
import time
import traceback
import uuid
import adsk.core as C
import adsk.fusion as F

spec=importlib.util.spec_from_file_location('fusion_bridge_transport',Path(__file__).with_name('transport.py'))
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
STATE=Path.home()/'.fusion-bridge'
EVENT='FusionBridgeDispatchV1'
app=None
server=None
handler=None
custom_event=None
jobs=None
documents={}
session=''


def doc_id(doc):
    for key, value in list(documents.items()):
        if not value.isValid:
            del documents[key]
        elif value==doc:
            return key
    key=session+':'+uuid.uuid4().hex
    documents[key]=doc
    return key


def active_design(args):
    doc=app.activeDocument
    if doc is None or args.get('document_id')!=doc_id(doc):
        raise ValueError('Document mismatch. Call documents, inspect the intended active design, and use its document_id.')
    design=F.Design.cast(doc.products.itemByProductType('DesignProductType'))
    if design is None:
        raise ValueError('The target document does not contain a Design product')
    return doc,design


def point(p):
    return [v*10 for v in p.asArray()]


def body_info(b):
    bb=b.boundingBox
    return {'name':b.name,'token':b.entityToken,'solid':b.isSolid,
            'visible':b.isVisible,'volume_mm3':b.volume*1000,
            'bounds_mm':{'min':point(bb.minPoint),'max':point(bb.maxPoint)},
            'faces':b.faces.count,'edges':b.edges.count}


def resolve(design,token,kind):
    items=design.findEntityByToken(token)
    matches=[x for x in items if kind.cast(x)]
    if len(matches)!=1:
        raise ValueError('Entity no longer uniquely resolves; inspect again')
    return matches[0]


def artifact(name,suffix):
    if not name or Path(name).name!=name or '/' in name or '\\' in name or ':' in name:
        raise ValueError('Use a plain filename, not a path')
    if not name.lower().endswith(suffix):
        raise ValueError('Filename must end in '+suffix)
    folder=STATE/'artifacts'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    return folder/name


def backup(design):
    path=artifact('before-edit.f3d','.f3d')
    if not design.exportManager.execute(design.exportManager.createFusionArchiveExportOptions(str(path))):
        raise RuntimeError('Recovery archive failed; edit refused')
    return str(path)


def dispatch(operation,args):
    # Never terminate or commit an interactive command belonging to the user.
    if app.userInterface.activeCommand not in ('SelectCommand',''):
        raise RuntimeError('Fusion is busy in '+app.userInterface.activeCommand+'. Finish/cancel it yourself, then retry.')
    if operation=='documents':
        return {'fusion_version':app.version,'active_command':app.userInterface.activeCommand,
                'documents':[{'document_id':doc_id(d),'name':d.name,'active':d==app.activeDocument,
                              'modified':d.isModified,'saved':d.isSaved} for d in app.documents]}
    if operation=='create_scratch':
        # Intentionally creates an unsaved document, never closes/replaces another one.
        doc=app.documents.add(C.DocumentTypes.FusionDesignDocumentType)
        return {'document_id':doc_id(doc),'name':doc.name,'saved':False}
    doc,design=active_design(args)
    root=design.rootComponent
    if operation=='inspect':
        offset=int(args.get('offset',0));limit=int(args.get('limit',100))
        if offset<0 or not 1<=limit<=250:raise ValueError('Invalid page bounds')
        occurrences=list(root.allOccurrences)
        return {'document_id':doc_id(doc),'name':doc.name,'modified':doc.isModified,
                'root_bodies':[body_info(b) for b in root.bRepBodies],
                'occurrence_count':len(occurrences),'offset':offset,
                'occurrences':[{'name':o.fullPathName,'token':o.entityToken,'component':o.component.name,
                                'visible':o.isVisible,'bodies':[body_info(b) for b in o.bRepBodies]} for o in occurrences[offset:offset+limit]],
                'parameters':[{'name':p.name,'expression':p.expression,'unit':p.unit,'value_internal':p.value} for p in design.userParameters],
                'units_note':'Geometry lengths mm; volumes mm^3. Parameter value_internal follows Fusion native units; use expression.'}
    if operation=='health':
        return {'features':[{'component':c.name,'name':f.name,'state':int(f.healthState),
                             'message':f.errorOrWarningMessage} for c in design.allComponents for f in c.features],
                'joints':[{'component':c.name,'name':j.name,'token':j.entityToken,'valid':j.isValid}
                          for c in design.allComponents for coll in (c.joints,c.asBuiltJoints) for j in coll]}
    if operation=='capture':
        width=int(args.get('width',1200));height=int(args.get('height',900))
        if not 320<=width<=2000 or not 240<=height<=2000:raise ValueError('Invalid image dimensions')
        path=artifact('viewport.png','.png')
        app.activeViewport.refresh()
        if not app.activeViewport.saveAsImageFile(str(path),width,height):raise RuntimeError('Capture failed')
        return {'path':str(path),'png_base64':base64.b64encode(path.read_bytes()).decode()}
    if operation=='interference':
        tokens=args.get('body_tokens',[])
        if not 2<=len(tokens)<=40:raise ValueError('Choose between 2 and 40 body tokens in assembly context')
        coll=C.ObjectCollection.create()
        for token in tokens:coll.add(resolve(design,token,F.BRepBody))
        inp=design.createInterferenceInput(coll);inp.areCoincidentFacesIncluded=False
        result=design.analyzeInterference(inp)
        if result is None:raise RuntimeError('No interference result returned')
        return {'overlaps':[{'first':x.entityOne.name,'second':x.entityTwo.name,'volume_mm3':x.interferenceBody.volume*1000} for x in result]}
    if operation=='export':
        fmt=args.get('format')
        if fmt not in ('f3d','step','stl'):raise ValueError('Supported formats: f3d, step, stl')
        path=artifact(args.get('filename','design.'+fmt),'.'+fmt)
        manager=design.exportManager
        if fmt=='f3d':opt=manager.createFusionArchiveExportOptions(str(path))
        elif fmt=='step':opt=manager.createSTEPExportOptions(str(path))
        else:
            token=args.get('body_token')
            if not token:raise ValueError('STL requires one explicit body_token')
            opt=manager.createSTLExportOptions(resolve(design,token,F.BRepBody),str(path))
            opt.meshRefinement=F.MeshRefinementSettings.MeshRefinementHigh;opt.isBinaryFormat=True
        if not manager.execute(opt):raise RuntimeError('Export failed')
        return {'path':str(path),'bytes':path.stat().st_size}
    if operation=='save':
        if not doc.isSaved:raise ValueError('Save this new document to a chosen Fusion project yourself, or export a local F3D archive')
        return {'saved':doc.save(args.get('description','Saved through Fusion Bridge'))}
    if operation=='set_parameter':
        param=design.userParameters.itemByName(args.get('name',''))
        if param is None:raise ValueError('Unknown user parameter')
        expression=args.get('expression')
        if not isinstance(expression,str) or not design.unitsManager.isValidExpression(expression,param.unit):
            raise ValueError('Invalid parameter expression')
        recovery=backup(design)
        try:
            old=param.expression;param.expression=expression
            return {'name':param.name,'before':old,'after':param.expression,'backup':recovery,'saved':False}
        except Exception as exc:
            raise RuntimeError(str(exc)+'; changes may be partial. Recovery archive: '+recovery) from exc
    if operation=='execute_python':
        if args.get('acknowledge_full_access') is not True:
            raise ValueError('General Python is NOT sandboxed. Explicit acknowledge_full_access=true is required.')
        source=args.get('code','')
        if not isinstance(source,str) or not source.strip() or len(source)>100000:raise ValueError('Invalid code')
        code=compile(source,'<fusion-bridge>','exec')
        recovery=backup(design)
        namespace={'app':app,'design':design,'root':root,'adsk':__import__('adsk'),
                   'core':C,'fusion':F,'math':math,'result':None,'artifact_dir':str(STATE/'artifacts')}
        try:
            exec(code,namespace)
            result=namespace.get('result')
            json.dumps(result,allow_nan=False)
            return {'result':result,'backup':recovery,'saved':False,
                    'warning':'Code has full process privileges; no automatic rollback or forced interruption.'}
        except BaseException as exc:
            raise RuntimeError(type(exc).__name__+': '+str(exc)+'; changes may be partial. Recovery archive: '+recovery) from exc
    raise ValueError('Unknown operation: '+operation)


class Handler(C.CustomEventHandler):
    def notify(self,args):
        job=jobs.next()
        if job is None:return
        key,request=job
        started=time.time()
        try:
            jobs.finish(key,result=dispatch(request['operation'],request.get('arguments',{})))
        except BaseException as exc:
            jobs.finish(key,error=type(exc).__name__+': '+str(exc))
        finally:
            # Some Autodesk operations pump events internally. A nested callback
            # must not run a second job; wake queued work after the outer job ends.
            if not jobs.pending.empty():
                app.fireCustomEvent(EVENT,'drain')
            record={'request_id':key,'operation':request['operation'],'status':jobs.get(key)['status'],
                    'duration_s':round(time.time()-started,3),'time':time.time(),
                    'argument_hash':hashlib.sha256(json.dumps(request.get('arguments',{}),sort_keys=True).encode()).hexdigest()}
            with (STATE/'audit.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')


def run(context):
    global app,server,handler,jobs,session,custom_event
    if server is not None:return
    app=C.Application.get();STATE.mkdir(parents=True,exist_ok=True)
    session=uuid.uuid4().hex
    handler=Handler()
    custom_event=app.registerCustomEvent(EVENT)
    if custom_event is None or not custom_event.add(handler):
        raise RuntimeError('Could not register the Fusion main-thread event handler')
    def signal(key):
        # This installed Fusion build returns False even for delivered events.
        # A queued/running/completed callback result, not the return flag, is proof.
        # If no callback arrives, the job stays pending and expires before execution.
        app.fireCustomEvent(EVENT,key)
        return True
    jobs=transport.Jobs(signal)
    token=secrets.token_urlsafe(48)
    try:
        server=transport.make_server(token,jobs)
        threading.Thread(target=server.serve_forever,daemon=True,name='FusionBridgeLoopback').start()
        temp=STATE/'connection.tmp'
        temp.write_text(json.dumps({'host':'127.0.0.1','port':server.server_port,'token':token,
                                    'session':session,'pid':os.getpid(),'version':'0.1.0'}),encoding='utf-8')
        temp.replace(STATE/'connection.json')
    except Exception:
        app.unregisterCustomEvent(EVENT)
        if server:server.server_close()
        server=None
        raise


def stop(context):
    global server,handler,custom_event
    if server:
        server.shutdown();server.server_close();server=None
    if app:app.unregisterCustomEvent(EVENT)
    path=STATE/'connection.json'
    if path.exists():
        try:
            if json.loads(path.read_text())['session']==session:path.unlink()
        except (OSError,ValueError,KeyError):pass
    handler=None
    custom_event=None
