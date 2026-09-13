"""Authenticated loopback job transport. No Autodesk imports or calls here."""
import hashlib
import hmac
import json
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 256 * 1024
MAX_RESULT = 2 * 1024 * 1024


class Jobs:
    def __init__(self, notify, clock=time.monotonic):
        self.notify, self.clock = notify, clock
        self.lock = threading.RLock()
        self.pending = queue.Queue(maxsize=32)
        self.records = {}
        self.running_key = None

    def submit(self, request):
        if not isinstance(request, dict):
            raise ValueError('Expected a JSON object')
        key = request.get('request_id', '')
        uuid.UUID(key)
        if not isinstance(request.get('operation'), str) or not isinstance(request.get('arguments', {}), dict):
            raise ValueError('Invalid operation/arguments')
        digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        with self.lock:
            if key in self.records:
                if self.records[key]['digest'] != digest:
                    raise ValueError('request_id already used for different arguments')
                return self.get(key)
            if len(self.records) >= 1000 or self.pending.full():
                raise ValueError('Job capacity reached; stop/start the add-in when idle')
            self.records[key] = dict(request=request, digest=digest, status='queued', expires=self.clock()+30)
            self.pending.put_nowait(key)
        try:
            if not self.notify(key):
                raise RuntimeError('Fusion did not accept the custom event')
        except Exception as exc:
            self.finish(key, error=str(exc))
        return self.get(key)

    def get(self, key):
        with self.lock:
            item = self.records.get(key)
            if item is None:
                raise KeyError('Unknown job; do not resubmit an uncertain write with a new ID')
            if item['status']=='queued' and self.clock()>=item['expires']:
                item['status']='expired'
            return {k:v for k,v in item.items() if k in ('status','result','error')} | {'request_id':key}

    def cancel(self, key):
        with self.lock:
            item = self.records[key]
            if item['status'] == 'queued':
                item['status'] = 'cancelled'
            return self.get(key)

    def next(self):
        with self.lock:
            if self.running_key is not None:
                return None
            while not self.pending.empty():
                key = self.pending.get_nowait()
                item = self.records[key]
                if item['status'] != 'queued':
                    continue
                if self.clock() >= item['expires']:
                    item['status']='expired'
                    continue
                item['status']='running'
                self.running_key=key
                return key, item['request']
        return None

    def finish(self, key, result=None, error=None):
        with self.lock:
            if error is None and len(json.dumps(result).encode()) > MAX_RESULT:
                error = 'Result exceeds 2 MiB; work may have completed. Inspect the model before retrying.'
            item=self.records[key]
            if self.running_key==key:
                self.running_key=None
            item['status']='failed' if error else 'completed'
            item['error' if error else 'result']=error if error else result


def make_server(token, jobs):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def reply(self, status, payload):
            data=json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            expected=f'127.0.0.1:{self.server.server_port}'
            auth=self.headers.get('Authorization','')
            return (self.headers.get('Host')==expected and not self.headers.get('Origin')
                    and hmac.compare_digest(auth,'Bearer '+token))

        def dispatch(self):
            if not self.authorized():
                self.reply(403,{'error':'Forbidden'})
                return
            try:
                if self.command=='GET' and self.path=='/health':
                    self.reply(200,{'service':'fusion-bridge','version':'0.1.0','jobs':len(jobs.records)})
                elif self.command=='GET' and self.path.startswith('/jobs/'):
                    self.reply(200,jobs.get(self.path[len('/jobs/'):]))
                elif self.command=='POST' and self.path in ('/jobs','/cancel'):
                    length=int(self.headers.get('Content-Length','0'))
                    if self.headers.get('Transfer-Encoding') or not 0 < length <= MAX_BODY:
                        raise ValueError('Invalid or excessive request size')
                    if self.headers.get('Content-Type')!='application/json':
                        raise ValueError('Expected application/json')
                    request=json.loads(self.rfile.read(length))
                    value=jobs.submit(request) if self.path=='/jobs' else jobs.cancel(request['request_id'])
                    self.reply(202,value)
                else:
                    self.reply(404,{'error':'Not found'})
            except (ValueError, KeyError, TypeError) as exc:
                self.reply(400,{'error':str(exc)})

        do_GET=dispatch
        do_POST=dispatch

    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    return server
