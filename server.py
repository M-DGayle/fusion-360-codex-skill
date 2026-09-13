"""MCP stdio facade using the official SDK. The add-in owns Fusion API access."""
from typing import Any, Literal
from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent, ToolAnnotations
from bridge_client import Client
import json

mcp=FastMCP('fusion-bridge',instructions='Direct Fusion API tools. Start with documents, then inspect the exact document_id. Never infer permission to edit from a read-only request. Python has full user/process access and is NOT sandboxed. For writes, preserve request_id and inspect job_status after any timeout; never blindly resubmit. Fusion must be open with FusionBridge loaded. Distinguish CAD checks from physical validation.')
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)
WRITE=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False)
LOCAL=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)


def call(operation,arguments=None,request_id=None):
    job=Client().call(operation,arguments,request_id)
    if job.get('status')=='failed':raise RuntimeError(json.dumps(job))
    return job


@mcp.tool(annotations=READ)
def status() -> dict:
    """Check authenticated local bridge liveness; does not query the CAD model."""
    return Client().http('/health')


@mcp.tool(annotations=READ)
def documents() -> dict:
    """List open Fusion documents and session-scoped IDs. Use the intended active document ID for all subsequent operations."""
    return call('documents')


@mcp.tool(annotations=READ)
def inspect(document_id:str, offset:int=0, limit:int=100) -> dict:
    """Read bodies, assembly-context entity tokens, bounds in mm, volumes, and user parameters. Page occurrences with offset/limit."""
    return call('inspect',dict(document_id=document_id,offset=offset,limit=limit))


@mcp.tool(annotations=READ)
def feature_health(document_id:str) -> dict:
    """Read feature errors/warnings and joint validity for the target design."""
    return call('health',dict(document_id=document_id))


@mcp.tool(annotations=READ)
def check_interference(document_id:str, body_tokens:list[str]) -> dict:
    """Check 2-40 explicitly selected assembly-context bodies for overlapping solids. Does not move them."""
    return call('interference',dict(document_id=document_id,body_tokens=body_tokens))


@mcp.tool(annotations=LOCAL,structured_output=False)
def capture_viewport(document_id:str,width:int=1200,height:int=900) -> Any:
    """Return a real Fusion viewport PNG directly, without screenshots or Computer Use; creates a unique local artifact."""
    job=call('capture',dict(document_id=document_id,width=width,height=height))
    if job['status']!='completed':return [TextContent(type='text',text=json.dumps(job))]
    result=job['result']
    return [TextContent(type='text',text=json.dumps({'path':result['path'],'request_id':job['request_id']})),
            ImageContent(type='image',mimeType='image/png',data=result['png_base64'])]


@mcp.tool(annotations=LOCAL)
def export_file(document_id:str,format:Literal['f3d','step','stl'],filename:str,body_token:str|None=None) -> dict:
    """Export to a new unique local artifact folder, never overwrite. STL requires one body token. No cloud save."""
    return call('export',dict(document_id=document_id,format=format,filename=filename,body_token=body_token))


@mcp.tool(annotations=WRITE)
def set_parameter(document_id:str,name:str,expression:str,request_id:str) -> dict:
    """Change one user parameter after a mandatory recovery archive. Does not save to cloud. Use a new UUID per intended edit; reuse exactly that UUID for an uncertain retry."""
    return call('set_parameter',dict(document_id=document_id,name=name,expression=expression),request_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=True))
def execute_python(document_id:str,code:str,acknowledge_full_access:bool,request_id:str) -> dict:
    """PRIVILEGED, NOT SANDBOXED: run Python on Fusion's main thread after a mandatory F3D backup. Has full filesystem/network/process authority; document guard is NOT a security sandbox. Scope code to the user's request. Variables: app, design, root, core, fusion, adsk, math, artifact_dir. Set result to JSON-serializable data. Native lengths are cm, angles radians. No forced interruption or automatic rollback; errors may leave partial changes. Never use UI automation from this tool. New UUID per intended edit; retain it for recovery."""
    return call('execute_python',dict(document_id=document_id,code=code,acknowledge_full_access=acknowledge_full_access),request_id)


@mcp.tool(annotations=WRITE)
def save_document(document_id:str,description:str,request_id:str) -> dict:
    """Save a new version of an already-saved Fusion document; may sync to Autodesk. Only use when saving is authorized. Unsaved documents need a user-chosen project or local archive export."""
    return call('save',dict(document_id=document_id,description=description),request_id)


@mcp.tool(annotations=LOCAL)
def create_scratch_document(request_id:str) -> dict:
    """Create and activate a new unsaved Fusion design for prototyping/testing. Existing documents remain open and unchanged."""
    return call('create_scratch',{},request_id)


@mcp.tool(annotations=READ)
def job_status(request_id:str) -> dict:
    """Retrieve a job outcome after a pending response/timeout. Unknown IDs after add-in restart require manual state inspection before another edit."""
    return Client().job(request_id)


@mcp.tool(annotations=LOCAL)
def cancel_queued_job(request_id:str) -> dict:
    """Cancel only a not-yet-started job. Running Fusion code cannot safely be force-interrupted; inspect its status instead."""
    return Client().http('/cancel',dict(request_id=request_id))


if __name__=='__main__':mcp.run(transport='stdio')
