import importlib.util
import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request
import uuid

spec=importlib.util.spec_from_file_location('transport',Path(__file__).parents[1]/'addin'/'FusionBridge'/'transport.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.clock=10
        self.jobs=t.Jobs(lambda key:self.events.append(key) or True,lambda:self.clock)
        self.request={'request_id':str(uuid.uuid4()),'operation':'inspect','arguments':{}}

    def test_replay_once(self):
        self.jobs.submit(self.request);self.jobs.submit(self.request)
        self.assertEqual(len(self.events),1)
        key,_=self.jobs.next();self.assertIsNone(self.jobs.next())
        self.jobs.finish(key,{'ok':True})
        self.assertEqual(self.jobs.submit(self.request)['status'],'completed')

    def test_conflicting_id_rejected(self):
        self.jobs.submit(self.request)
        with self.assertRaises(ValueError):self.jobs.submit(self.request|{'operation':'execute_python'})

    def test_expired_never_runs(self):
        self.jobs.submit(self.request);self.clock=41
        self.assertIsNone(self.jobs.next())
        self.assertEqual(self.jobs.get(self.request['request_id'])['status'],'expired')

    def test_cancel_queued(self):
        self.jobs.submit(self.request);self.jobs.cancel(self.request['request_id'])
        self.assertIsNone(self.jobs.next())

    def test_running_cannot_cancel(self):
        self.jobs.submit(self.request);self.jobs.next()
        self.assertEqual(self.jobs.cancel(self.request['request_id'])['status'],'running')

    def test_bad_id(self):
        with self.assertRaises(ValueError):self.jobs.submit(self.request|{'request_id':'bad'})

    def test_event_failure(self):
        self.jobs.notify=lambda key:False
        self.assertEqual(self.jobs.submit(self.request)['status'],'failed')
        self.assertIsNone(self.jobs.next())

    def test_oversized_result(self):
        self.jobs.submit(self.request);self.jobs.next()
        self.jobs.finish(self.request['request_id'],'x'*t.MAX_RESULT)
        self.assertEqual(self.jobs.get(self.request['request_id'])['status'],'failed')

    def test_missing_callback_reports_expired(self):
        self.jobs.submit(self.request);self.clock=41
        self.assertEqual(self.jobs.get(self.request['request_id'])['status'],'expired')
        self.assertIsNone(self.jobs.next())

    def test_nested_callback_cannot_start_a_second_job(self):
        self.jobs.submit(self.request)
        second=self.request|{'request_id':str(uuid.uuid4())}
        self.jobs.submit(second)
        key,_=self.jobs.next()
        self.assertIsNone(self.jobs.next())
        self.jobs.finish(key,{'ok':True})
        next_key,_=self.jobs.next()
        self.assertEqual(next_key,second['request_id'])


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.jobs=t.Jobs(lambda _:True)
        self.server=t.make_server('test-token',self.jobs)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.server.shutdown();self.server.server_close()

    def request(self,headers=None,path='/health',data=None):
        req=urllib.request.Request(self.base+path,headers=headers or {},data=data)
        with self.opener.open(req,timeout=2) as result:return json.load(result)

    def test_authenticated_health(self):
        self.assertEqual(self.request({'Authorization':'Bearer test-token'})['service'],'fusion-bridge')

    def test_unauthorized(self):
        with self.assertRaises(urllib.error.HTTPError) as e:self.request()
        self.assertEqual(e.exception.code,403)

    def test_origin_denied(self):
        with self.assertRaises(urllib.error.HTTPError):self.request({'Authorization':'Bearer test-token','Origin':'http://evil.test'})

    def test_rebinding_host_denied(self):
        with self.assertRaises(urllib.error.HTTPError):self.request({'Authorization':'Bearer test-token','Host':'evil.test'})

    def test_http_submit(self):
        request={'request_id':str(uuid.uuid4()),'operation':'documents','arguments':{}}
        result=self.request({'Authorization':'Bearer test-token','Content-Type':'application/json'},'/jobs',json.dumps(request).encode())
        self.assertEqual(result['status'],'queued')

    def test_oversized_request(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.request({'Authorization':'Bearer test-token','Content-Type':'application/json'},'/jobs',b'x'*(t.MAX_BODY+1))


if __name__=='__main__':unittest.main()
