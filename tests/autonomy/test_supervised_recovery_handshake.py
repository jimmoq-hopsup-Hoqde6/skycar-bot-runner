import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/autonomy'))
import supervised_recovery_handshake as h


def run(rid,path):
    return dict(id=rid,head_sha='a'*40,repository={'full_name':h.RUNNER_REPOSITORY},event='workflow_dispatch',head_branch='main',path=path,run_attempt=1,status='in_progress',conclusion=None)

class HandshakeTests(unittest.TestCase):
    def setup_records(self):
        p=run(12,h.PRODUCER_PATH);r=run(34,h.RECOVERY_PATH)
        receipt=h.arm(p,r,1000,lambda m:True,lambda x:True)
        job=dict(run_id=34,run_attempt=1,head_sha='a'*40,name='supervised-recovery',status='in_progress',conclusion=None,steps=[dict(name='Publish arming receipt',status='completed',conclusion='success'),dict(name='Bounded recovery loop',status='in_progress')])
        return receipt,p,r,job
    def assert_gate_rejects_before_claim(self, receipt, p, r, j, now):
        claim=Mock(return_value=True)
        with self.assertRaises(h.RecoveryBlocked):h.authorize(receipt,p,r,j,now,claim=claim)
        claim.assert_not_called()
    def test_fresh_independent_proof(self):
        receipt,p,r,j=self.setup_records()
        out=h.authorize(receipt,p,r,j,1020,claim=lambda m:True)
        self.assertTrue(out['authorized_for_one_creation']);self.assertFalse(out['hard_deadline_guaranteed'])
    def test_probe_and_durable_ack_required(self):
        p=run(12,h.PRODUCER_PATH);r=run(34,h.RECOVERY_PATH)
        for probe,persist in [(False,True),(True,False),(1,True)]:
            with self.subTest(probe=probe,persist=persist),self.assertRaises(h.RecoveryBlocked):h.arm(p,r,1000,lambda m:probe,lambda x:persist)
    def test_run_scope_fail_closed(self):
        for key,value in [('event','pull_request'),('head_branch','feature'),('path','other'),('run_attempt',2),('head_sha','main'),('id',True),('status','completed')]:
            receipt,p,r,j=self.setup_records();p[key]=value
            with self.subTest(key=key):self.assert_gate_rejects_before_claim(receipt,p,r,j,1020)
    def test_stale_future_tampered_or_duplicate(self):
        for field,value in [('armed_at',1100),('armed_at',900),('stop_at',999999),('producer_run_id',99),('recovery_run_id',12),('workflow_sha','b'*40),('schema','wrong')]:
            receipt,p,r,j=self.setup_records();receipt[field]=value
            with self.subTest(field=field):self.assert_gate_rejects_before_claim(receipt,p,r,j,1020)
        receipt,p,r,j=self.setup_records()
        self.assert_gate_rejects_before_claim(receipt,p,r,j,1181)
    def test_job_and_loop_must_be_live(self):
        for field,value in [('status','queued'),('run_id',999),('head_sha','b'*40),('conclusion','cancelled'),('name','other')]:
            receipt,p,r,j=self.setup_records();j[field]=value
            with self.subTest(field=field):self.assert_gate_rejects_before_claim(receipt,p,r,j,1020)
        receipt,p,r,j=self.setup_records();j['steps'][1]['status']='queued'
        self.assert_gate_rejects_before_claim(receipt,p,r,j,1020)
    def test_metadata_tampering_and_unknown_receipt_fields(self):
        receipt,p,r,j=self.setup_records();receipt['metadata']['runner_run_id']='99'
        self.assert_gate_rejects_before_claim(receipt,p,r,j,1020)
        receipt,p,r,j=self.setup_records();receipt['token']='not-allowed'
        self.assert_gate_rejects_before_claim(receipt,p,r,j,1020)
    def test_cleanup_is_finite_unknown_never_recreates(self):
        receipt,p,r,j=self.setup_records();ticks=[0];saved=[]
        def sleep(n):ticks[0]+=n
        with patch.object(h,'reconcile',return_value={'status':'not_visible_yet_unresolved','may_create_again':False}) as rec:
            out=h.cleanup_window(Mock(),receipt['metadata'],deadline=1000,clock=lambda:ticks[0],sleep=sleep,persist=lambda x:saved.append(x) or True)
        self.assertEqual(rec.call_count,h.MAX_POLLS);self.assertFalse(out['may_create_again']);self.assertTrue(out['supervision_required'])
    def test_confirmation_and_persistence(self):
        receipt,p,r,j=self.setup_records()
        with patch.object(h,'reconcile',return_value={'status':'deletion_confirmed','session_id':'s1','may_create_again':False}) as rec:
            out=h.cleanup_window(Mock(),receipt['metadata'],deadline=10,clock=lambda:0,sleep=Mock(),persist=lambda x:True)
            self.assertEqual(out['status'],'deletion_confirmed');self.assertEqual(rec.call_count,1)
            out=h.cleanup_window(Mock(),receipt['metadata'],deadline=10,clock=lambda:0,sleep=Mock(),persist=lambda x:False)
            self.assertEqual(out['status'],'result_persistence_unconfirmed')
            self.assertEqual(out['session_id'],'s1')
            self.assertEqual(out['reconciliation_status'],'deletion_confirmed')
    def test_persistence_timeout_retains_verified_identity(self):
        receipt,p,r,j=self.setup_records()
        with patch.object(h,'reconcile',return_value={'status':'deletion_confirmed','session_id':'s1','may_create_again':False}):
            out=h.cleanup_window(Mock(),receipt['metadata'],deadline=10,clock=lambda:0,sleep=Mock(),persist=Mock(side_effect=TimeoutError()))
        self.assertEqual(out['session_id'],'s1');self.assertEqual(out['status'],'result_persistence_unconfirmed')
    def test_expired_window_no_provider_call(self):
        receipt,p,r,j=self.setup_records()
        with patch.object(h,'reconcile') as rec:
            out=h.cleanup_window(Mock(),receipt['metadata'],deadline=10,clock=lambda:10,sleep=Mock(),persist=lambda x:True)
        rec.assert_not_called();self.assertFalse(out['may_create_again'])
    def test_single_use_claim_required_and_replay_rejected(self):
        receipt,p,r,j=self.setup_records();claimed=[]
        def claim(m):
            if claimed:return False
            claimed.append(m);return True
        with self.assertRaises(h.RecoveryBlocked):h.authorize(receipt,p,r,j,1020)
        h.authorize(receipt,p,r,j,1020,claim=claim)
        with self.assertRaises(h.RecoveryBlocked):h.authorize(receipt,p,r,j,1020,claim=claim)
    def test_workflow_separate_concurrency_hard_disabled_no_secret(self):
        text=(Path(__file__).resolve().parents[2]/'.github/workflows/supervised-recovery.yml').read_text()
        self.assertIn('if: ${{ false }}',text);self.assertIn('group: skycar-supervised-recovery',text)
        self.assertEqual(text.count('secrets.SKYCAR_PILOT_OPENAI_API_KEY'),2)
        self.assertNotIn('secrets.OPENAI_API_KEY',text);self.assertIn('environment: skycar-agent-pilot',text)
        self.assertIn('name: Publish arming receipt',text);self.assertIn('name: Bounded recovery loop',text)

if __name__=='__main__':unittest.main()
