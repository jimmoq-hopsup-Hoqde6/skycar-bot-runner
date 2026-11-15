import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from test_bounded_coding_pilot import pilot, fake_client
import review_pilot_artifact as reviewer

SHA='f10a36fe98961dc1dcfbace37d9323752e1f3ffe'

def source_request():
    return pilot.build_request({p:b'# source\n' for p in pilot.ALLOWED_FILES},SHA,100)

def bound(): return pilot.bind_attempt(source_request(),123,1,'a'*40)

class IntegrationTests(unittest.TestCase):
    def test_legacy_execution_rejected_before_create(self):
        client,sessions=fake_client(); request=source_request()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(pilot.PilotError): pilot.execute(client,request,Path(tmp)/'out',pilot.fingerprint(request))
        sessions.create.assert_not_called()
    def test_fingerprint_binds_attempt_without_mutating_source(self):
        request=source_request(); original=copy.deepcopy(request)
        variants=[request,pilot.bind_attempt(request,123,1,'a'*40),pilot.bind_attempt(request,124,1,'a'*40),pilot.bind_attempt(request,123,1,'b'*40)]
        self.assertEqual(len({pilot.fingerprint(v) for v in variants}),4)
        self.assertEqual(request,original)
    def test_wrong_source_rejected(self):
        request=source_request(); request['metadata']['commit']='b'*40
        with self.assertRaises(pilot.PilotError): pilot.bind_attempt(request,123,1,'a'*40)
    def test_tampered_attempt_rejected_before_create(self):
        client,sessions=fake_client(); request=bound(); request['metadata']['runner_repository']='wrong/repo'
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(pilot.PilotError): pilot.execute(client,request,Path(tmp)/'out',pilot.fingerprint(request))
        sessions.create.assert_not_called()
    def test_creation_timeout_preserves_attempt(self):
        client,sessions=fake_client(); request=bound(); sessions.create.side_effect=TimeoutError()
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'out'
            with self.assertRaises(TimeoutError): pilot.execute(client,request,out,pilot.fingerprint(request))
            state=json.loads((out/'state.json').read_text())
            self.assertEqual(state['attempt_metadata'],request['metadata'])
            self.assertEqual(state['reconciliation'],'reconcile_pilot_attempt.reconcile')
        self.assertEqual(sessions.create.call_args.kwargs['metadata'],request['metadata'])
        sessions.create.assert_called_once(); sessions.stream.assert_not_called()
    def test_delete_requires_exact_boolean_and_id(self):
        for value in (None,NS(id='wrong',deleted=True),NS(id='sess_test',deleted=False),NS(id='sess_test',deleted=1)):
            client,sessions=fake_client(); request=bound(); sessions.delete.return_value=value
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'out'
                with self.assertRaises(pilot.PilotError): pilot.execute(client,request,out,pilot.fingerprint(request))
                state=json.loads((out/'state.json').read_text())
                self.assertEqual(state['cleanup'],'pending_manual_reconciliation')
                self.assertEqual(state['session_id'],'sess_test')
            sessions.delete.assert_called_once()
    def test_producer_output_passes_reviewer_without_executing_code(self):
        client,sessions=fake_client(); request=bound()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/'out'
            state=pilot.execute(client,request,out,pilot.fingerprint(request))
            self.assertEqual(state['cleanup'],'deletion_confirmed')
            with patch.object(reviewer,'source_snapshot',return_value={p:b'# original\n' for p in pilot.ALLOWED_FILES}):
                reviewer.review(root,SHA,out/'changes.json',out/'state.json',root/'review')
            self.assertTrue((root/'review/candidate.patch').exists())
            self.assertEqual(json.loads((root/'review/review.json').read_text())['status'],'scope_validated_NOT_TESTED_NOT_APPROVED')
    def test_old_unconfirmed_cleanup_not_accepted_by_reviewer(self):
        client,sessions=fake_client(); request=bound()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); out=root/'out'
            state=pilot.execute(client,request,out,pilot.fingerprint(request)); state['cleanup']='deletion_requested'
            (out/'state.json').write_text(json.dumps(state))
            with patch.object(reviewer,'source_snapshot',return_value={p:b'# original\n' for p in pilot.ALLOWED_FILES}), self.assertRaises(reviewer.PilotError):
                reviewer.review(root,SHA,out/'changes.json',out/'state.json',root/'review')

if __name__=='__main__': unittest.main()
