import copy
from email.message import Message
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/autonomy'))
import github_recovery_records as g


class Response:
    def __init__(self, data, url, status=200, link=None, raw=None):
        self.raw = json.dumps(data).encode() if raw is None else raw
        self.url, self.status = url, status
        self.headers = Message(); self.headers['Content-Type'] = 'application/json'
        if link: self.headers['Link'] = link
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def geturl(self): return self.url
    def read(self, limit): return self.raw[:limit]


class GitHubRecordsTests(unittest.TestCase):
    def setUp(self):
        self.sha = 'a'*40
        def run(rid, path):
            return dict(id=rid,head_sha=self.sha,repository={'full_name':g.RUNNER_REPOSITORY},
                        event='workflow_dispatch',head_branch='main',path=path,run_attempt=1,
                        status='in_progress',conclusion=None)
        self.producer = run(12,g.PRODUCER_PATH); self.recovery = run(34,g.RECOVERY_PATH)
        self.job = dict(id=56,run_id=34,head_sha=self.sha,run_attempt=1,
                        name='supervised-recovery',status='in_progress',conclusion=None,steps=[])
        self.payloads = [self.producer,self.recovery,dict(total_count=1,jobs=[self.job])]
        self.opener = Mock()
        self.requests = []
        def open_(request, timeout):
            self.requests.append(request)
            self.assertEqual(timeout,15)
            return Response(self.payloads[len(self.requests)-1],request.full_url)
        self.opener.open.side_effect = open_
    def go(self):
        return g.fetch_records(12,34,self.sha,'offline-token',opener=self.opener)
    def test_exact_bounded_reads(self):
        self.assertEqual(self.go(),(self.producer,self.recovery,self.job))
        self.assertEqual([r.full_url for r in self.requests],[g.BASE+'/actions/runs/12',
            g.BASE+'/actions/runs/34',g.BASE+'/actions/runs/34/attempts/1/jobs?per_page=100'])
        self.assertTrue(all(r.get_method()=='GET' for r in self.requests))
    def test_documented_job_without_attempt_is_bound_by_exact_endpoint(self):
        del self.job['run_attempt']
        _,_,job=self.go()
        self.assertEqual(job['run_attempt'],1)
        self.assertIn('/attempts/1/jobs?',self.requests[-1].full_url)
        self.assertNotIn('run_attempt',self.job)
    def test_bad_inputs_make_no_calls(self):
        for pid,rid,sha,token in [(True,34,self.sha,'x'),(12,12,self.sha,'x'),
                                (12,34,'main','x'),(12,34,self.sha,'x\nsecret')]:
            with self.assertRaises(g.RecoveryBlocked):
                g.fetch_records(pid,rid,sha,token,opener=self.opener)
        self.opener.open.assert_not_called()
    def test_wrong_run_stops_before_jobs(self):
        self.producer['head_sha']='b'*40
        with self.assertRaises(g.RecoveryBlocked): self.go()
        self.assertEqual(len(self.requests),1)
    def test_duplicate_or_incomplete_jobs_rejected(self):
        for page in [dict(total_count=2,jobs=[self.job,self.job]),dict(total_count=2,jobs=[self.job]),
                     dict(total_count=101,jobs=[]),dict(total_count=True,jobs=[self.job])]:
            with self.subTest(page=page):
                self.requests=[]; self.payloads[2]=page
                with self.assertRaises(g.RecoveryBlocked): self.go()
    def test_wrong_job_scope_rejected(self):
        for key,value in [('run_id',99),('head_sha','b'*40),('run_attempt',2),('status','completed')]:
            with self.subTest(key=key):
                self.requests=[]; job=copy.deepcopy(self.job);job[key]=value
                self.payloads[2]=dict(total_count=1,jobs=[job])
                with self.assertRaises(g.RecoveryBlocked): self.go()
    def test_redirect_handler_refuses(self):
        with self.assertRaises(g.RecoveryBlocked):
            g.NoRedirect().redirect_request(None,None,302,'',{},'https://other.example')
    def test_unexpected_response_rejected(self):
        for change in [dict(status=302),dict(link='<next>; rel="next"'),
                       dict(raw=b'x'*(g.MAX_BYTES+1)),dict(raw=b'{"x":1,"x":2}'),
                       dict(url='https://other.example')]:
            with self.subTest(change=list(change)):
                args=dict(data=self.producer,url=g.BASE+'/actions/runs/12');args.update(change)
                self.opener.open.side_effect=None;self.opener.open.return_value=Response(**args)
                with self.assertRaises(g.RecoveryBlocked):self.go()
    def test_errors_do_not_leak_credentials(self):
        self.opener.open.side_effect=RuntimeError('offline-token secret provider body')
        with self.assertRaises(g.RecoveryBlocked) as ctx:self.go()
        self.assertNotIn('offline-token',str(ctx.exception));self.assertNotIn('provider body',str(ctx.exception))


if __name__ == '__main__': unittest.main()
