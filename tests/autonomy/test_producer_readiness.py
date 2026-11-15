"""No credentials/network: hostile GitHub records, immutable claims, timing races."""
import copy
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/autonomy'))
import producer_readiness as p
import supervised_runtime as r
from test_supervised_recovery_handshake import run


def archive(contents=b'12\n', name='one-use-claim.txt', extra=False):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr(name, contents)
        if extra:
            z.writestr('extra', b'no')
    return out.getvalue()


class ProducerReadinessTests(unittest.TestCase):
    def setUp(self):
        self.producer = run(12, p.PRODUCER_PATH)
        self.job = dict(id=78, run_id=12, run_attempt=1, head_sha='a'*40,
                        name='coding-task', status='in_progress', conclusion=None,
                        steps=[dict(name=p.PUBLISH_STEP, status='completed', conclusion='success'),
                               dict(name=p.EXECUTE_STEP, status='in_progress', conclusion=None)])
        self.jobs = dict(total_count=1, jobs=[self.job])
        self.raw = archive()
        self.artifact = dict(id=56, name=p.CLAIM_NAME, expired=False,
                             digest='sha256:'+hashlib.sha256(self.raw).hexdigest(),
                             workflow_run=dict(id=12, head_sha='a'*40))
        self.artifacts = dict(total_count=1, artifacts=[self.artifact])
        self.proof = dict(producer_run_id=12, workflow_sha='a'*40, run_attempt=1,
                          producer_job_id=78, claim_artifact_id=56, claim_digest=self.artifact['digest'])
        self.paths = []
        def read(path, token, opener):
            self.assertEqual(token, 'offline-token')
            self.paths.append(path)
            return {'/actions/runs/12':self.producer,
                    '/actions/runs/12/attempts/1/jobs?per_page=100':self.jobs,
                    '/actions/runs/12/artifacts?per_page=100':self.artifacts}[path]
        self.reader = patch.object(p, '_read', side_effect=read).start()
        self.addCleanup(patch.stopall)
        self.download = Mock(return_value=self.raw)
    def go(self, **kwargs):
        return p.observe_producer(12, 'a'*40, 'offline-token', Mock(), self.download, **kwargs)
    def blocked(self):
        with self.assertRaises(p.RecoveryBlocked): self.go()
    def test_exact_job_and_digest_bound_claim_rechecked_after_download(self):
        self.assertEqual(self.go(), self.proof)
        self.assertEqual(self.paths, ['/actions/runs/12', '/actions/runs/12/attempts/1/jobs?per_page=100',
                                      '/actions/runs/12/artifacts?per_page=100']*2)
        self.download.assert_called_once_with(56)
    def test_attempt_endpoint_binds_omitted_job_attempt(self):
        del self.job['run_attempt']
        self.assertEqual(self.go(), self.proof)
    def test_invalid_lookup_inputs_make_no_reads(self):
        for pid, sha, token in [(True,'a'*40,'x'),(12,'main','x'),(12,'a'*40,'x\nsecret')]:
            with self.subTest(pid=pid,sha=sha), self.assertRaises(p.RecoveryBlocked):
                p.observe_producer(pid,sha,token,Mock(),self.download)
        self.reader.assert_not_called(); self.download.assert_not_called()
    def test_wrong_producer_identity_or_terminal_state_never_downloads(self):
        original = copy.deepcopy(self.producer)
        for key, value in [('id',13),('head_sha','b'*40),('run_attempt',2),('run_attempt',True),
                           ('head_branch','feature'),('path',r.RECOVERY_PATH),('event','push'),
                           ('repository',{'full_name':'wrong/repo'}),('status','completed'),
                           ('conclusion','failure')]:
            self.producer.clear(); self.producer.update(original); self.producer[key]=value
            with self.subTest(key=key,value=value): self.blocked()
        self.download.assert_not_called()
    def test_missing_ambiguous_incomplete_or_malformed_jobs_fail(self):
        for jobs,count in [([],0),([self.job,self.job],2),([self.job],2),([None],1),([self.job],True)]:
            self.jobs.update(jobs=jobs,total_count=count)
            with self.subTest(count=count,jobs=jobs): self.blocked()
        self.download.assert_not_called()
    def test_wrong_job_identity_or_terminal_state_fails(self):
        original = copy.deepcopy(self.job)
        for key,value in [('id',True),('run_id',13),('head_sha','b'*40),('run_attempt',2),
                          ('run_attempt',True),('name','other'),('status','completed'),('conclusion','cancelled')]:
            self.job.clear();self.job.update(original);self.job[key]=value
            with self.subTest(key=key): self.blocked()
        self.download.assert_not_called()
    def test_known_queued_producer_job_is_waitable_without_claim_read(self):
        for state in ('queued','waiting','pending'):
            self.job['status']=state; self.job['steps']=[]
            with self.subTest(state=state), self.assertRaises(p.ProducerNotReady): self.go()
        self.download.assert_not_called()
        self.assertTrue(all('artifacts' not in path for path in self.paths))
    def test_known_unfinished_steps_wait_without_claim_read(self):
        for publish_state in ('queued','pending','in_progress','completed'):
            self.job['steps'][0].update(status=publish_state,conclusion='success' if publish_state=='completed' else None)
            self.job['steps'][1]['status']='pending'
            with self.subTest(state=publish_state), self.assertRaises(p.ProducerNotReady): self.go()
        self.download.assert_not_called()
    def test_missing_ambiguous_malformed_or_failed_steps_fail(self):
        good = copy.deepcopy(self.job['steps'])
        cases = [None,[],[None],good*2,[good[0]],
                 [dict(good[0],conclusion='failure'),good[1]],
                 [good[0],dict(good[1],status='completed')],
                 [dict(good[0],status='in_progress',conclusion=None),good[1]],
                 [good[0],dict(good[1],conclusion='failure')]]
        for steps in cases:
            self.job['steps']=steps
            with self.subTest(steps=steps): self.blocked()
        self.download.assert_not_called()
    def test_missing_ambiguous_incomplete_or_malformed_claim_fails(self):
        for entries,count in [([],0),([self.artifact,self.artifact],2),([self.artifact],2),([None],1),([self.artifact],True)]:
            self.artifacts.update(artifacts=entries,total_count=count)
            with self.subTest(count=count): self.blocked()
        self.download.assert_not_called()
    def test_claim_identity_and_digest_must_be_exact(self):
        original = copy.deepcopy(self.artifact)
        for key,value in [('id',True),('name','other'),('expired',True),('workflow_run',None),
                          ('workflow_run',{'id':13,'head_sha':'a'*40}),
                          ('workflow_run',{'id':12,'head_sha':'b'*40}),('digest','missing')]:
            self.artifact.clear();self.artifact.update(original);self.artifact[key]=value
            with self.subTest(key=key): self.blocked()
        self.download.assert_not_called()
    def test_claim_archive_must_contain_only_exact_producer_id(self):
        for raw in [archive(b'13\n'),archive(b'12'),archive(name='../one-use-claim.txt'),
                    archive(extra=True),archive(b'x'*33),b'not zip']:
            self.artifact['digest']='sha256:'+hashlib.sha256(raw).hexdigest()
            self.download.return_value=raw
            with self.subTest(raw=raw[:10]): self.blocked()
    def test_changed_archive_digest_is_rejected(self):
        self.download.return_value=archive(b'13\n')
        self.blocked()
    def test_claim_symlink_and_oversized_archive_fail(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            entry=zipfile.ZipInfo('one-use-claim.txt');entry.external_attr=0o120777 << 16
            z.writestr(entry,b'12\n')
        for raw in (out.getvalue(),b'x'*(p.MAX_ARCHIVE+1)):
            self.artifact['digest']='sha256:'+hashlib.sha256(raw).hexdigest()
            self.download.return_value=raw
            self.blocked()
    def test_malformed_nested_run_fails_closed(self):
        for value in (None,[],42):
            self.producer['repository']=value
            self.blocked()
        self.download.assert_not_called()
    def test_expected_binding_rejects_replaced_claim_job_or_malformed_proof(self):
        for key,value in [('claim_artifact_id',99),('producer_job_id',99),('claim_digest','sha256:'+'b'*64),
                          ('run_attempt',2),('producer_run_id',13),('workflow_sha','b'*40)]:
            proof=dict(self.proof);proof[key]=value
            with self.subTest(key=key),self.assertRaises(p.RecoveryBlocked):self.go(expected=proof)
        for proof in ({},dict(self.proof,unexpected=True),None):
            if proof is not None:
                with self.assertRaises(p.RecoveryBlocked):self.go(expected=proof)
        self.download.assert_not_called()
    def test_producer_cancellation_during_download_blocks_readiness(self):
        def download(_):
            self.producer.update(status='completed',conclusion='cancelled')
            return self.raw
        self.download.side_effect=download
        self.blocked()
    def test_claim_replacement_during_download_blocks_readiness(self):
        def download(_):
            self.artifact['id']=99
            return self.raw
        # Each authenticated response is a distinct object, as with real JSON.
        original=self.reader.side_effect
        self.reader.side_effect=lambda *args:copy.deepcopy(original(*args))
        self.download.side_effect=download
        self.blocked()


class ProducerWaitTests(unittest.TestCase):
    def setUp(self): self.now=0;self.sleeps=[]
    def sleep(self, seconds): self.sleeps.append(seconds);self.now+=seconds
    def go(self):
        return p.wait_for_producer(12,'a'*40,'offline',Mock(),Mock(),clock=lambda:self.now,sleep=self.sleep)
    def test_only_positive_pending_state_retries_then_returns_binding(self):
        with patch.object(p,'observe_producer',side_effect=[p.ProducerNotReady(),{'binding':'exact'}]) as probe:
            self.assertEqual(self.go(),{'binding':'exact'});self.assertEqual(probe.call_count,2)
        self.assertEqual(self.sleeps,[5])
    def test_missing_or_unknown_failure_not_retried(self):
        for error in (p.RecoveryBlocked('missing job'),RuntimeError('unknown')):
            with patch.object(p,'observe_producer',side_effect=error) as probe,self.assertRaises(type(error)):self.go()
            probe.assert_called_once()
        self.assertEqual(self.sleeps,[])
    def test_deadline_is_finite_and_does_not_arm(self):
        with patch.object(p,'observe_producer',side_effect=p.ProducerNotReady()) as probe,self.assertRaises(p.RecoveryBlocked):self.go()
        self.assertEqual(self.now,300);self.assertEqual(probe.call_count,60)
    def test_slow_success_cannot_return_after_deadline(self):
        def observe(*args):self.now=301;return {'binding':'exact'}
        with patch.object(p,'observe_producer',side_effect=observe),self.assertRaises(p.RecoveryBlocked):self.go()
        self.assertEqual(self.sleeps,[])


class RecoveryApprovalOrderTests(unittest.TestCase):
    def setUp(self):
        self.proof=dict(producer_run_id=12,workflow_sha='a'*40,run_attempt=1,
                        producer_job_id=78,claim_artifact_id=56,claim_digest='sha256:'+'a'*64)
        self.producer=run(12,p.PRODUCER_PATH);self.recovery=run(34,r.RECOVERY_PATH)
    def exercise(self, *, block_at=None, probe_ok=True):
        trace=[];checks=[0]
        def readiness(*args,**kwargs):
            self.assertEqual(kwargs['expected'],self.proof)
            checks[0]+=1;trace.append('ready'+str(checks[0]))
            if checks[0]==block_at:raise p.RecoveryBlocked('producer stopped or claim changed')
            return self.proof
        client=MagicMock()
        def factory(**kwargs):trace.append('client');return client
        def provider_read(**kwargs):
            from reconcile_pilot_attempt import attempt_metadata
            self.assertEqual(kwargs,dict(metadata=attempt_metadata(12,1,'a'*40),limit=2))
            trace.append('provider_read');page=Mock(data=[] if probe_ok else ['existing'])
            page.has_next_page.return_value=False;return page
        client.__enter__.return_value.beta.agents.sessions.list.side_effect=provider_read
        def write(*args):trace.append('receipt');return True
        with patch.dict(os.environ,{'OPENAI_API_KEY':'offline-placeholder'},clear=True), \
             patch.object(r,'records',return_value=(self.producer,self.recovery)), \
             patch.object(r,'observe_producer',side_effect=readiness), \
             patch.object(r,'write',side_effect=write),patch.object(r.time,'time',return_value=1000):
            def go():return r.stage_recovery(12,34,'a'*40,'offline',Mock(),self.proof,Path('/unused'),factory)
            if block_at or not probe_ok:
                with self.assertRaises(p.RecoveryBlocked):go()
            else:
                receipt=go();self.assertEqual(receipt['armed_at'],1000)
                self.assertEqual(receipt['stop_at'],2200)
        return trace
    def test_ready_check_before_provider_and_again_before_receipt(self):
        self.assertEqual(self.exercise(),['ready1','client','provider_read','ready2','receipt'])
    def test_delayed_approval_after_producer_stops_no_client_no_receipt(self):
        self.assertEqual(self.exercise(block_at=1),['ready1'])
    def test_cancellation_during_provider_probe_no_receipt(self):
        self.assertEqual(self.exercise(block_at=2),['ready1','client','provider_read','ready2'])
    def test_failed_provider_probe_never_persists_receipt(self):
        self.assertEqual(self.exercise(probe_ok=False),['ready1','client','provider_read'])
    def test_wait_cli_has_no_provider_access_or_api_key(self):
        env=dict(GITHUB_TOKEN='offline-token',GITHUB_SHA='a'*40,GITHUB_RUN_ID='34',
                 GITHUB_RUN_ATTEMPT='1',GITHUB_REF='refs/heads/main',GITHUB_REPOSITORY='jimmoq-hopsup-Hoqde6/skycar-bot-runner')
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,env,clear=True), \
             patch.object(sys,'argv',['runtime','wait-producer','--producer-id','12','--output',tmp+'/ready.json']), \
             patch.object(r,'wait_for_producer',return_value=self.proof),patch('openai.OpenAI') as provider:
            r.main();self.assertTrue(Path(tmp+'/ready.json').exists());provider.assert_not_called()
    def test_workflow_has_secret_free_dependency_and_preserves_permissions(self):
        root=Path(__file__).resolve().parents[2]
        workflow=(root/'.github/workflows/supervised-recovery.yml').read_text()
        waiting=workflow.split('  wait-for-producer:',1)[1].split('  supervised-recovery:',1)[0]
        protected=workflow.split('  supervised-recovery:',1)[1]
        self.assertNotIn('secrets.',waiting);self.assertNotIn('environment:',waiting)
        self.assertNotIn('pip install',waiting);self.assertIn('timeout-minutes: 7',waiting)
        self.assertIn('supervised_runtime.py wait-producer',waiting)
        self.assertIn('needs: wait-for-producer',protected)
        self.assertIn("needs.wait-for-producer.result == 'success'",protected)
        self.assertIn('environment: skycar-agent-pilot',protected)
        for field in ('producer_job_id','claim_artifact_id','claim_digest'):
            self.assertIn('needs.wait-for-producer.outputs.'+field,protected)
        self.assertEqual(workflow.count('secrets.SKYCAR_PILOT_OPENAI_API_KEY'),2)
        self.assertEqual(workflow.split('permissions:\n',1)[1].split('concurrency:',1)[0],'  contents: read\n  actions: read\n')
        self.assertNotIn('schedule:',workflow);self.assertIn('default: false',workflow)
        self.assertIn('Recovery guard',workflow)
        self.assertIn('Producer:',(root/'.github/workflows/one-coding-bot.yml').read_text())

if __name__=='__main__':unittest.main()
