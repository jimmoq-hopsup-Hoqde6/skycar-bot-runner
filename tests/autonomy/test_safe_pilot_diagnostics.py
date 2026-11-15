import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/autonomy'))
import safe_pilot_diagnostics as d
import supervised_recovery_handshake as h


def records():
    def run(rid, path):
        return dict(id=rid,head_sha='a'*40,repository={'full_name':h.RUNNER_REPOSITORY},
                    event='workflow_dispatch',head_branch='main',path=path,run_attempt=1,
                    status='in_progress',conclusion=None)
    p,r=run(12,h.PRODUCER_PATH),run(34,h.RECOVERY_PATH)
    receipt=h.arm(p,r,1000,lambda m:True,lambda x:True)
    j=dict(run_id=34,run_attempt=1,head_sha='a'*40,name='supervised-recovery',
           status='in_progress',conclusion=None,steps=[
               dict(name='Publish arming receipt',status='completed',conclusion='success'),
               dict(name='Bounded recovery loop',status='in_progress')])
    return receipt,p,r,j


class DiagnosticsTests(unittest.TestCase):
    def test_unknown_exception_never_serialized(self):
        class SecretError(Exception):
            def __str__(self):
                raise AssertionError('Must never serialize')
        for error in (RuntimeError('sk-secret https://secret.example/body'), SecretError()):
            out=io.StringIO()
            with contextlib.redirect_stderr(out), self.assertRaises(type(error)):
                with d.phase('ARCHIVE_DOWNLOAD'):
                    raise error
            self.assertEqual(out.getvalue(),
                'PILOT_PHASE ARCHIVE_DOWNLOAD START\n'
                'PILOT_PHASE ARCHIVE_DOWNLOAD BLOCKED UNEXPECTED_FAILURE\n')

    def test_untrusted_reason_and_phase_cannot_be_logged(self):
        error=d.DiagnosticBlocked('sk-secret')
        error.code='sk-secret'
        self.assertEqual(d.reason(error),'UNEXPECTED_FAILURE')
        out=io.StringIO()
        with contextlib.redirect_stderr(out), self.assertRaises(h.RecoveryBlocked):
            with d.phase('sk-secret'): pass
        self.assertEqual(out.getvalue(),'')

    def test_expired_receipt_identified_before_claim_or_execution(self):
        receipt,p,r,j=records();claim=Mock(return_value=True);execute=Mock()
        out=io.StringIO()
        with contextlib.redirect_stderr(out), self.assertRaises(d.DiagnosticBlocked) as ctx:
            with d.phase('AUTHORIZATION'):
                h.authorize(receipt,p,r,j,1181,claim=claim)
                execute()
        self.assertEqual(ctx.exception.code,'RECEIPT_EXPIRED')
        self.assertIn('BLOCKED RECEIPT_EXPIRED',out.getvalue())
        claim.assert_not_called();execute.assert_not_called()

    def test_exact_180_second_boundary_remains_accepted(self):
        receipt,p,r,j=records();claim=Mock(return_value=True)
        self.assertEqual(h.MAX_RECEIPT_AGE,180)
        self.assertTrue(h.authorize(receipt,p,r,j,1180,claim=claim)['authorized_for_one_creation'])
        claim.assert_called_once()

    def test_identity_and_claim_have_distinct_safe_codes(self):
        receipt,p,r,j=records();receipt['producer_run_id']=99
        with self.assertRaises(d.DiagnosticBlocked) as ctx:
            h.authorize(receipt,p,r,j,1020,claim=Mock(return_value=True))
        self.assertEqual(ctx.exception.code,'RECEIPT_MISMATCH')
        receipt,p,r,j=records()
        with self.assertRaises(d.DiagnosticBlocked) as ctx:
            h.authorize(receipt,p,r,j,1020,claim=lambda m:False)
        self.assertEqual(ctx.exception.code,'CLAIM_REJECTED')

if __name__ == '__main__': unittest.main()
