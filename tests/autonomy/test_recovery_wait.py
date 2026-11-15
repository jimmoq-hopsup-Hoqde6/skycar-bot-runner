from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/autonomy'))
import supervised_runtime as r


class RecoveryWaitTests(unittest.TestCase):
    def setUp(self):
        self.now=0
        self.sleeps=[]
        self.job=dict(steps=[
            dict(name='Publish arming receipt',status='completed',conclusion='success'),
            dict(name='Bounded recovery loop',status='in_progress',conclusion=None)])
    def sleep(self, seconds):
        self.sleeps.append(seconds);self.now+=seconds
    def go(self):
        return r.wait_for_recovery(12,'a'*40,'offline',Mock(),
                                   clock=lambda:self.now,sleep=self.sleep)
    def test_missing_receipt_then_live_loop(self):
        with patch.object(r,'discover_recovery',side_effect=[r.RecoveryNotReady(),(34,{'id':56})]),patch.object(r,'fetch_records',return_value=({}, {}, self.job)):
            self.assertEqual(self.go(),(34,{'id':56}))
        self.assertEqual(self.sleeps,[5])
    def test_queued_or_pending_loop_waits_then_is_rechecked(self):
        for state in ('queued','pending'):
            self.now=0;self.sleeps=[]
            waiting=dict(steps=[self.job['steps'][0],dict(self.job['steps'][1],status=state)])
            with patch.object(r,'discover_recovery',return_value=(34,{})),patch.object(r,'fetch_records',side_effect=[({}, {}, waiting),({}, {}, self.job)]) as records:
                self.assertEqual(self.go(),(34,{}));self.assertEqual(records.call_count,2)
            self.assertEqual(self.sleeps,[5])
    def test_visible_artifact_waits_for_publication_completion(self):
        waiting=dict(steps=[
            dict(self.job['steps'][0],status='in_progress',conclusion=None),
            dict(self.job['steps'][1],status='queued')])
        with patch.object(r,'discover_recovery',return_value=(34,{})),patch.object(r,'fetch_records',side_effect=[({}, {}, waiting),({}, {}, self.job)]) as records:
            self.assertEqual(self.go(),(34,{}))
            self.assertEqual(records.call_count,2)
        self.assertEqual(self.sleeps,[5])
    def test_unknown_auth_or_ambiguity_not_retried(self):
        for error in (r.RecoveryBlocked('authentication'),r.RecoveryBlocked('ambiguous'),RuntimeError('unknown')):
            self.sleeps=[]
            with patch.object(r,'discover_recovery',side_effect=error) as discover,self.assertRaises(type(error)):
                self.go()
            discover.assert_called_once();self.assertEqual(self.sleeps,[])
    def test_bad_live_record_not_retried(self):
        with patch.object(r,'discover_recovery',return_value=(34,{})),patch.object(r,'fetch_records',side_effect=r.RecoveryBlocked('scope')) as records,self.assertRaises(r.RecoveryBlocked):
            self.go()
        records.assert_called_once();self.assertEqual(self.sleeps,[])
    def test_malformed_terminal_or_unpublished_steps_fail(self):
        cases=[None,[],[None],self.job['steps']*2,
               [dict(self.job['steps'][0],status='in_progress'),self.job['steps'][1]],
               [dict(self.job['steps'][0],status='in_progress',conclusion=None),self.job['steps'][1]],
               [self.job['steps'][0],dict(self.job['steps'][1],status='completed')],
               [self.job['steps'][0],dict(self.job['steps'][1],conclusion='failure')]]
        for steps in cases:
            with self.subTest(steps=steps),patch.object(r,'discover_recovery',return_value=(34,{})),patch.object(r,'fetch_records',return_value=({}, {}, dict(steps=steps))),self.assertRaises(r.RecoveryBlocked):
                self.go()
            self.assertEqual(self.sleeps,[])
    def test_absence_has_finite_300_second_deadline(self):
        with patch.object(r,'discover_recovery',side_effect=r.RecoveryNotReady()) as discover,self.assertRaises(r.RecoveryBlocked):
            self.go()
        self.assertEqual(self.now,300);self.assertEqual(discover.call_count,60)
    def test_slow_ready_probe_cannot_return_after_deadline(self):
        def records(*args,**kwargs):
            self.now=301
            return {},{},self.job
        with patch.object(r,'discover_recovery',return_value=(34,{})),patch.object(r,'fetch_records',side_effect=records),self.assertRaises(r.RecoveryBlocked):
            self.go()
        self.assertEqual(self.sleeps,[])
    def test_full_final_gate_still_after_fingerprint_before_execution(self):
        import inspect
        source=inspect.getsource(r.main)
        self.assertLess(source.index("with phase('FINGERPRINT_VALIDATION')"),source.index('        verify('))
        self.assertLess(source.index('        verify('),source.index('with OpenAI(',source.index('        verify(')))
        self.assertLess(source.index('        verify('),source.index('execute(client,request'))
        self.assertNotIn('OpenAI',inspect.getsource(r.wait_for_recovery))

if __name__=='__main__':unittest.main()
