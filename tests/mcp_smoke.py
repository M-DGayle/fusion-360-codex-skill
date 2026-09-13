"""Verify the actual MCP stdio process. --live also tests the active Fusion model read-only."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(live,output):
    report={}
    config=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).parents[1]/'server.py')])
    async with stdio_client(config) as (read,write):
        async with ClientSession(read,write) as session:
            init=await session.initialize()
            report['server']=init.serverInfo.model_dump()
            listing=await session.list_tools()
            report['tools']=[t.name for t in listing.tools]
            assert len(listing.tools)==13
            for t in listing.tools:
                assert t.inputSchema.get('type')=='object'
            if live:
                async def call(name,args={}):
                    response=await session.call_tool(name,args)
                    assert not response.isError, str(response)
                    if name=='capture_viewport':
                        assert any(c.type=='image' for c in response.content)
                        return {'image_received':True,'metadata':response.content[0].text}
                    data=response.structuredContent
                    if data is None:data=json.loads(response.content[0].text)
                    assert data.get('status','completed')=='completed',str(data)
                    return data
                report['bridge_status']=await call('status')
                docs=(await call('documents'))['result']['documents']
                active=next(d for d in docs if d['active'])
                report['active_document']=active
                docid=active['document_id']
                report['inspection']=(await call('inspect',{'document_id':docid}))['result']
                report['health']=(await call('feature_health',{'document_id':docid}))['result']
                report['capture']=await call('capture_viewport',{'document_id':docid})
                rejection=await session.call_tool('inspect',{'document_id':'wrong-document'})
                assert rejection.isError
                report['wrong_document_rejected']=True
                rejection=await session.call_tool('execute_python',{'document_id':docid,'code':'result=1','acknowledge_full_access':False,'request_id':'aa509594-d92e-4ab4-bc0c-a4bf8c4b9d2'})
                assert rejection.isError
                report['unacknowledged_python_rejected']=True
    if output:
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('inspection','health')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args();asyncio.run(main(args.live,args.output))
