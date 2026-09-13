"""Local bridge client and CLI. Never log the connection bearer token."""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

STATE=Path.home()/'.fusion-bridge'


class Client:
    def __init__(self, state=STATE):
        self.state=Path(state)
        try:self.config=json.loads((self.state/'connection.json').read_text(encoding='utf-8'))
        except (OSError,ValueError) as exc:
            raise RuntimeError('Fusion Bridge is not active. Start the FusionBridge add-in inside Fusion.') from exc
        if self.config.get('host')!='127.0.0.1' or not isinstance(self.config.get('port'),int) or not 1<=self.config['port']<=65535:
            raise ValueError('Invalid local connection configuration')
        self.base=f"http://127.0.0.1:{self.config['port']}"
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def http(self,path,data=None):
        headers={'Authorization':'Bearer '+self.config['token']}
        if data is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(self.base+path,headers=headers,data=None if data is None else json.dumps(data).encode())
        try:
            with self.opener.open(req,timeout=5) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError('Bridge rejected request: '+exc.read(4096).decode(errors='replace')) from None
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            raise RuntimeError('Fusion Bridge is unreachable or timed out. Do not repeat uncertain edits; inspect their job ID.') from exc

    def job(self,key):
        uuid.UUID(key)
        return self.http('/jobs/'+key)

    def call(self,operation,arguments=None,request_id=None,wait_seconds=15):
        key=request_id or str(uuid.uuid4())
        try:
            result=self.http('/jobs',{'request_id':key,'operation':operation,'arguments':arguments or {}})
        except Exception as exc:
            raise RuntimeError(f'{exc} Request ID: {key}; use job_status before retrying.') from None
        end=time.monotonic()+min(max(wait_seconds,0),20)
        while result['status'] in ('queued','running') and time.monotonic()<end:
            time.sleep(0.1)
            try:result=self.job(key)
            except Exception as exc:raise RuntimeError(f'{exc} Request ID: {key}') from None
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation')
    parser.add_argument('--arguments',default='{}')
    parser.add_argument('--arguments-file',type=Path)
    parser.add_argument('--request-id')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    client=Client()
    arguments=json.loads(args.arguments_file.read_text(encoding='utf-8') if args.arguments_file else args.arguments)
    if args.operation=='status':result=client.http('/health')
    elif args.operation=='job_status':result=client.job(args.request_id)
    else:result=client.call(args.operation,arguments,args.request_id)
    if isinstance(result.get('result'),dict):result['result'].pop('png_base64',None)
    content=json.dumps(result,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(content,encoding='utf-8')
    print(content)
    if result.get('status') in ('failed','cancelled','expired'):raise SystemExit(1)


if __name__=='__main__':main()
