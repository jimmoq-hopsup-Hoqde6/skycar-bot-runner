import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
import unittest

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).resolve().parents[2] / 'scripts/autonomy/recover_pilot_session.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class APIError(Exception):
    def __init__(self, status): self.status_code = status

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.receipt = dict(session_id='sess_test', repository=r.REPOSITORY, commit=r.COMMIT, task=r.TASK)
        self.client = MagicMock()
        self.client.with_options.return_value = self.client
        self.s = self.client.beta.agents.sessions
        self.s.retrieve.return_value = NS(id='sess_test', metadata={k:self.receipt[k] for k in ('repository','commit','task')})
        self.s.delete.return_value = NS(id='sess_test', deleted=True)
        self.sleep = MagicMock()
    def run_cleanup(self): return r.recover(self.client, self.receipt, execute=True, sleep=self.sleep)
    def test_default_is_offline(self):
        self.assertEqual(r.recover(self.client, self.receipt)['status'], 'offline_plan')
        self.assertFalse(self.client.mock_calls)
    def test_nonboolean_execution_rejected(self):
        for value in ('false', 1, object(), None):
            with self.assertRaises(r.RecoveryBlocked): r.recover(self.client, self.receipt, execute=value)
        self.assertFalse(self.client.mock_calls)
    def test_transport_retries_disabled(self):
        self.run_cleanup()
        self.client.with_options.assert_called_once_with(max_retries=0, timeout=20)
    def test_invalid_receipts_make_no_calls(self):
        for change in ({'session_id':None}, {'session_id':'../other'}, {'commit':'a'*40}, {'repository':'other'}, {'task':'other'}):
            with self.assertRaises(r.RecoveryBlocked): r.recover(self.client, dict(self.receipt, **change), execute=True)
        self.assertFalse(self.client.mock_calls)
    def test_missing_id_rejected(self):
        del self.receipt['session_id']
        with self.assertRaises(r.RecoveryBlocked): self.run_cleanup()
        self.assertFalse(self.client.mock_calls)
    def test_mismatch_never_mutates(self):
        for session in (NS(id='other',metadata={}), NS(id='sess_test',metadata={})):
            self.s.retrieve.return_value=session
            with self.assertRaises(r.RecoveryBlocked): self.run_cleanup()
        self.s.delete.assert_not_called(); self.s.events.create.assert_not_called()
    def test_success_confirms_exact_session(self):
        self.assertEqual(self.run_cleanup()['status'], 'deletion_confirmed')
        self.s.events.create.assert_called_once_with('sess_test', events=[{'type':'agent.session.input.cancel'}])
        self.s.delete.assert_called_once_with('sess_test')
        self.s.create.assert_not_called(); self.s.stream.assert_not_called()
    def test_conflicts_bounded(self):
        self.s.delete.side_effect=APIError(409)
        self.assertEqual(self.run_cleanup()['status'], 'cleanup_unconfirmed')
        self.assertEqual(self.s.delete.call_count,3); self.assertEqual(self.sleep.call_count,2)
    def test_conflict_then_success(self):
        self.s.delete.side_effect=[APIError(409),NS(id='sess_test',deleted=True)]
        self.assertEqual(self.run_cleanup()['status'],'deletion_confirmed')
    def test_nonconflict_not_retried(self):
        self.s.delete.side_effect=APIError(429)
        self.assertEqual(self.run_cleanup()['status'],'cleanup_unconfirmed')
        self.s.delete.assert_called_once(); self.sleep.assert_not_called()
    def test_404_not_false_success(self):
        self.s.retrieve.side_effect=APIError(404)
        self.assertEqual(self.run_cleanup()['status'],'unavailable_not_verified_deleted')
        self.s.delete.assert_not_called()
    def test_auth_lookup_fails_closed(self):
        self.s.retrieve.side_effect=APIError(401)
        with self.assertRaises(r.RecoveryBlocked): self.run_cleanup()
        self.s.delete.assert_not_called()
    def test_cancel_failure_still_deletes(self):
        self.s.events.create.side_effect=APIError(409)
        self.assertEqual(self.run_cleanup()['cancel'],'unconfirmed')
        self.s.delete.assert_called_once()
    def test_delete_requires_positive_exact_response(self):
        for result in (NS(id='other',deleted=True),NS(id='sess_test',deleted=False),None):
            self.s.delete.return_value=result
            self.assertEqual(self.run_cleanup()['status'],'cleanup_unconfirmed')

if __name__ == '__main__': unittest.main()
