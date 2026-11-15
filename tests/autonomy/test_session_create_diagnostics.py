import contextlib
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
import httpx2
import openai
from test_producer_attempt_integration import bound, pilot
from test_bounded_coding_pilot import fake_client
from types import SimpleNamespace as NS
import session_create_diagnostics as d

SECRET = 'sk-SECRET-body-header-request'

class CreationDiagnosticsTests(unittest.TestCase):
    def exercise(self, handler, category, status=None):
        count=[]
        def transport(request):
            count.append(request)
            return handler(request)
        logs=io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(logs), patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden')):
            with openai.OpenAI(api_key=SECRET,max_retries=0,http_client=httpx2.Client(transport=httpx2.MockTransport(transport))) as client:
                request=bound(); out=Path(tmp)/'out'
                with self.assertRaises(BaseException):
                    pilot.execute(client,request,out,pilot.fingerprint(request))
            state=json.loads((out/'state.json').read_text())
        self.assertEqual(len(count),1)
        self.assertEqual(state['status'],'blocked_reconcile_before_retry')
        self.assertEqual(state['cleanup'],'creation_outcome_unknown_do_not_retry')
        self.assertIsNone(state['session_id']); self.assertIsNone(state['turn_id'])
        expected={'phase':'SESSION_CREATE','category':category}
        if status is not None: expected['http_status']=status
        self.assertEqual(state['creation_diagnostic'],expected)
        self.assertNotIn(SECRET,json.dumps(state)+logs.getvalue())
        self.assertNotIn('COMPLETE',logs.getvalue())
    def test_http_failures(self):
        for status,category in [(400,'BadRequestError'),(401,'AuthenticationError'),(403,'PermissionDeniedError'),(429,'RateLimitError'),(500,'InternalServerError'),(503,'InternalServerError')]:
            with self.subTest(status=status):
                self.exercise(lambda r:httpx2.Response(status,json={'error':{'message':SECRET,'code':SECRET}},headers={'x-request-id':SECRET}),category,status)
    def test_timeout_and_connection(self):
        for error,category in [(httpx2.ReadTimeout,'APITimeoutError'),(httpx2.ConnectError,'APIConnectionError')]:
            def handler(r): raise error(SECRET,request=r)
            self.exercise(handler,category)
    def test_malformed_success(self):
        for body in [{}, {'id':None}, {'id':SECRET+'/'}, {'id':123}, {'id':''},
                     {'id':'a'*129}, {'id':'../escape'}, {'id':'id\nforged'},
                     {'id':'id\x00bad'}, {'id':'https://example.invalid'}, {'id':'ä'}]:
            with self.subTest(body=body):
                self.exercise(lambda r:httpx2.Response(200,json=body),'MALFORMED_SESSION_RESPONSE')
    def test_arbitrary_exception_never_inspected_or_rendered(self):
        class Evil(Exception):
            @property
            def status_code(self): raise AssertionError('do not inspect')
            def __str__(self): raise AssertionError('do not render')
        self.assertEqual(d.classify(Evil()),{'phase':'SESSION_CREATE','category':'UNKNOWN'})
    def test_invalid_status_is_omitted(self):
        for status in [True,'403',399,600,None]:
            error=openai.BadRequestError(SECRET,response=httpx2.Response(400,request=httpx2.Request('POST','https://example.invalid')),body=SECRET)
            error.status_code=status
            self.assertNotIn('http_status',d.classify(error))

    def test_valid_non_sess_id_is_retained_for_cleanup(self):
        for sid in ['different_prefix-123', 'x', 'A'*128]:
            with self.subTest(sid=sid), tempfile.TemporaryDirectory() as tmp:
                client,sessions=fake_client()
                sessions.create.return_value=NS(id=sid,spend_control=None)
                sessions.delete.return_value=NS(id=sid,deleted=True)
                request=bound(); out=Path(tmp)/'out'
                with self.assertRaises(pilot.PilotError):
                    pilot.execute(client,request,out,pilot.fingerprint(request))
                state=json.loads((out/'state.json').read_text())
                self.assertEqual(state['session_id'],sid)
                self.assertEqual(state['cleanup'],'deletion_confirmed')
                self.assertNotIn('creation_diagnostic',state)
                sessions.delete.assert_called_once_with(sid)
                sessions.stream.assert_not_called()
