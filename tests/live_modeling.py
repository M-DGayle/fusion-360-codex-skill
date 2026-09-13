"""End-to-end MCP writes in a new scratch document, never the user's geometry."""
import asyncio
import json
from pathlib import Path
import shutil
import sys
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OUT=Path(sys.argv[1])
OUT.mkdir(parents=True,exist_ok=True)


async def main():
    report={'checks':[]}
    config=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).parents[1]/'server.py')])
    async with stdio_client(config) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            async def call(name,args={}):
                response=await session.call_tool(name,args)
                assert not response.isError,str(response)
                data=response.structuredContent or json.loads(response.content[0].text)
                assert data['status']=='completed',str(data)
                return data
            async def execute(docid,code,key=None):
                return await call('execute_python',{'document_id':docid,'code':code,
                    'acknowledge_full_access':True,'request_id':key or str(uuid.uuid4())})
            def record(label,details):
                report['checks'].append({'check':label,'details':details})
                (OUT/'live-modeling-test.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            before=(await call('documents'))['result']['documents']
            original=next(d for d in before if d['active'])
            initial=(await call('inspect',{'document_id':original['document_id']}))['result']
            report['original_document']=original
            scratch=(await call('create_scratch_document',{'request_id':str(uuid.uuid4())}))['result']
            docid=scratch['document_id'];report['scratch_document']=scratch
            code="""
assert root.bRepBodies.count==0 and root.occurrences.count==0, 'Scratch design is not empty'
design.userParameters.add('bridge_test_depth',core.ValueInput.createByString('5 mm'),'mm','Bridge test only')
sk=root.sketches.add(root.xYConstructionPlane)
sk.name='FusionBridge scratch rectangle'
sk.sketchCurves.sketchLines.addTwoPointRectangle(core.Point3D.create(0,0,0),core.Point3D.create(2,1,0))
inp=root.features.extrudeFeatures.createInput(sk.profiles.item(0),fusion.FeatureOperations.NewBodyFeatureOperation)
inp.setOneSideExtent(fusion.DistanceExtentDefinition.create(core.ValueInput.createByString('bridge_test_depth')),fusion.ExtentDirections.PositiveExtentDirection)
feature=root.features.extrudeFeatures.add(inp)
feature.name='FusionBridge scratch block'
feature.bodies.item(0).name='FusionBridge validation body'
sk.isVisible=False
result={'volume_mm3':feature.bodies.item(0).volume*1000,'body_count':root.bRepBodies.count}
"""
            try:
                key=str(uuid.uuid4())
                created=await execute(docid,code,key)
                assert abs(created['result']['result']['volume_mm3']-1000)<0.01
                assert Path(created['result']['backup']).is_file()
                record('API rectangle extrusion and pre-edit archive',created)
                repeated=await execute(docid,code,key)
                assert repeated==created
                record('Replaying the same write ID did not duplicate geometry',repeated['request_id'])
                changed=await call('set_parameter',{'document_id':docid,'name':'bridge_test_depth','expression':'6 mm','request_id':str(uuid.uuid4())})
                view=(await call('inspect',{'document_id':docid}))['result']
                assert len(view['root_bodies'])==1 and abs(view['root_bodies'][0]['volume_mm3']-1200)<0.01
                record('Parameter-driven solid changes from 1000 to 1200 cubic mm',changed)
                for fmt in ('f3d','step','stl'):
                    args={'document_id':docid,'format':fmt,'filename':'bridge-validation.'+fmt}
                    if fmt=='stl':args['body_token']=view['root_bodies'][0]['token']
                    exported=(await call('export_file',args))['result']
                    assert Path(exported['path']).stat().st_size>0
                    shutil.copy2(exported['path'],OUT/('bridge-validation.'+fmt))
                    record('Export '+fmt,exported)
                await execute(docid,"""
sk=root.sketches.add(root.xYConstructionPlane)
sk.sketchCurves.sketchLines.addTwoPointRectangle(core.Point3D.create(1,0,0),core.Point3D.create(3,1,0))
inp=root.features.extrudeFeatures.createInput(sk.profiles.item(0),fusion.FeatureOperations.NewBodyFeatureOperation)
inp.setOneSideExtent(fusion.DistanceExtentDefinition.create(core.ValueInput.createByString('6 mm')),fusion.ExtentDirections.PositiveExtentDirection)
root.features.extrudeFeatures.add(inp)
result={'bodies':root.bRepBodies.count}
""")
                view=(await call('inspect',{'document_id':docid}))['result']
                overlap=(await call('check_interference',{'document_id':docid,'body_tokens':[b['token'] for b in view['root_bodies']]}))['result']
                assert len(overlap['overlaps'])==1 and abs(overlap['overlaps'][0]['volume_mm3']-600)<0.01
                record('Known overlap detected at 600 cubic mm',overlap)
                health=(await call('feature_health',{'document_id':docid}))['result']
                assert all(f['state']==0 for f in health['features'])
                record('Scratch feature health',health)
            finally:
                # Close only the scratch document created above, after mandatory backup.
                current=(await call('documents'))['result']['documents']
                active=next(d for d in current if d['active'])
                if active['document_id']==docid:
                    closed=await execute(docid,"""
assert any(p.name=='bridge_test_depth' for p in design.userParameters), 'Not the test document'
document=app.activeDocument
closed=document.close(False)
result={'scratch_closed':closed}
""")
                    record('Scratch closed with recovery archive preserved',closed)
            after=(await call('documents'))['result']['documents']
            active=next(d for d in after if d['active'])
            assert active['document_id']==original['document_id']
            assert active['modified']==original['modified']
            final=(await call('inspect',{'document_id':active['document_id']}))['result']
            def fingerprint(info):
                bodies=info['root_bodies']+[b for o in info['occurrences'] for b in o['bodies']]
                return sorted((b['name'],round(b['volume_mm3'],5),json.dumps(b['bounds_mm'],sort_keys=True)) for b in bodies)
            assert fingerprint(initial)==fingerprint(final)
            record('Original document active again; geometry fingerprint and modified flag unchanged',active)
            report['passed']=True
            (OUT/'live-modeling-test.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps({'passed':True,'checks':[x['check'] for x in report['checks']],'output':str(OUT)},indent=2))


asyncio.run(main())
