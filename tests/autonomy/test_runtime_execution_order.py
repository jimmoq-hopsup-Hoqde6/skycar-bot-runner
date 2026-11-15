"""Real CLI control flow with offline GitHub/provider substitutes."""
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/autonomy'))
import supervised_runtime as r
import supervised_recovery_handshake as h
import bounded_coding_pilot as pilot
from test_safe_pilot_diagnostics import records


class RuntimeExecutionOrderTests(unittest.TestCase):
    def exercise(self, *, expired=False, rejected_claim=False):
        receipt,p,recovery,job=records()
        trace=[]
        ticks=[0]
        def sleep(seconds):ticks[0]+=seconds
        original_wait=r.wait_for_recovery
        def wait(*args,**kwargs):
            return original_wait(*args,**kwargs,clock=lambda:ticks[0],sleep=sleep)
        def final_gate(pid,rid,sha,token,archive,clock,*,claim,opener):
            trace.append('verify')
            result=h.authorize(receipt,p,recovery,job,1181 if expired else 1020,claim=claim)
            trace.append('verified')
            return result
        fake_client=MagicMock()
        def client_factory(**kwargs):
            trace.append('provider_client')
            return fake_client
        def execute(*args):
            trace.append('execute')
        env=dict(GITHUB_TOKEN='offline-token',GITHUB_SHA='a'*40,GITHUB_RUN_ID='12',
                 GITHUB_RUN_ATTEMPT='1',GITHUB_REF='refs/heads/main',
                 GITHUB_REPOSITORY=h.RUNNER_REPOSITORY,CLAIM_ARTIFACT_ID='77',
                 OPENAI_API_KEY='offline-not-a-real-key',REVIEWED_FINGERPRINT='fingerprint')
        claim=dict(id=77,expired=False,workflow_run=dict(id=12,head_sha='a'*40))
        with ExitStack() as stack:
            def patched(target,**kwargs):return stack.enter_context(patch(target,**kwargs))
            stack.enter_context(patch.dict(os.environ,env,clear=True))
            patched('sys.argv',new=['supervised_runtime.py','execute','--root','/unused','--output','/unused/output'])
            patched('supervised_runtime.wait_for_recovery',side_effect=wait)
            discovery=patched('supervised_runtime.discover_recovery',side_effect=[r.RecoveryNotReady(),(34,{'id':56})])
            patched('supervised_runtime.fetch_records',return_value=(p,recovery,job))
            patched('supervised_runtime.download_archive',return_value=b'offline')
            patched('supervised_runtime.artifact_for',return_value=None if rejected_claim else claim)
            patched('supervised_runtime.verify',side_effect=final_gate)
            patched('bounded_coding_pilot.source_snapshot',return_value={})
            patched('bounded_coding_pilot.build_request',return_value={})
            patched('bounded_coding_pilot.bind_attempt',return_value={})
            patched('bounded_coding_pilot.fingerprint',return_value='fingerprint')
            provider=patched('openai.OpenAI',side_effect=client_factory)
            execution=patched('bounded_coding_pilot.execute',side_effect=execute)
            if expired or rejected_claim:
                with self.assertRaises(h.RecoveryBlocked):r.main()
                provider.assert_not_called();execution.assert_not_called()
                self.assertEqual(trace,['verify'])
            else:
                r.main()
                provider.assert_called_once();execution.assert_called_once()
                self.assertEqual(trace,['verify','verified','provider_client','execute'])
            self.assertEqual(discovery.call_count,2)
            self.assertEqual(ticks[0],5)

    def test_missing_then_fresh_executes_exactly_once_after_gate(self):
        self.exercise()
    def test_expired_receipt_never_constructs_provider(self):
        self.exercise(expired=True)
    def test_claim_failure_never_constructs_provider(self):
        self.exercise(rejected_claim=True)

if __name__=='__main__':unittest.main()
