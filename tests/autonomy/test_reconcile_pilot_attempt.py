import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/autonomy'))
import reconcile_pilot_attempt as r

class AttemptTests(unittest.TestCase):
    def setUp(self):
        self.m = r.attempt_metadata(123,1,'a'*40)
        self.client=MagicMock(); self.client.with_options.return_value=self.client
        self.s=self.client.beta.agents.sessions
        self.session=NS(id='sess_test',metadata=self.m)
        self.page=MagicMock(); self.page.data=[self.session]; self.page.has_next_page.return_value=False
        self.s.list.return_value=self.page; self.s.retrieve.return_value=self.session
        self.s.delete.return_value=NS(id='sess_test',deleted=True)
    def go(self): return r.reconcile(self.client,self.m,execute=True)
    def test_identity_reconstructs_deterministically(self):
        self.assertEqual(self.m,r.attempt_metadata(123,1,'a'*40))
        self.assertNotEqual(self.m,r.attempt_metadata(124,1,'a'*40))
    def test_bad_run_identity(self):
        for args in ((True,1,'a'*40),(0,1,'a'*40),(123,2,'a'*40),(123,1,'main')):
            with self.assertRaises(r.RecoveryBlocked): r.attempt_metadata(*args)
    def test_offline_default_no_calls(self):
        self.assertEqual(r.reconcile(self.client,self.m)['status'],'offline_plan')
        self.assertFalse(self.client.mock_calls)
    def test_strict_opt_in(self):
        with self.assertRaises(r.RecoveryBlocked): r.reconcile(self.client,self.m,execute='false')
        self.assertFalse(self.client.mock_calls)
    def test_missing_or_extra_metadata(self):
        for value in ({},dict(self.m,extra='x'),dict(self.m,runner_run_id='0123')):
            with self.assertRaises(r.RecoveryBlocked): r.reconcile(self.client,value,execute=True)
        self.assertFalse(self.client.mock_calls)
    def test_eventual_consistency_never_authorizes_retry(self):
        self.page.data=[]
        self.assertEqual(self.go(),dict(status='not_visible_yet_unresolved',may_create_again=False))
        self.s.delete.assert_not_called()
    def test_duplicates_never_choose_first(self):
        self.page.data=[self.session,self.session]
        self.assertEqual(self.go()['status'],'ambiguous_manual_reconciliation')
        self.s.delete.assert_not_called()
    def test_pagination_stays_unresolved(self):
        self.page.has_next_page.return_value=True
        self.assertEqual(self.go()['status'],'ambiguous_manual_reconciliation')
        self.s.delete.assert_not_called()
    def test_filtered_mismatch_fails_closed(self):
        self.page.data=[NS(id='sess_other',metadata={})]
        with self.assertRaises(r.RecoveryBlocked): self.go()
        self.s.delete.assert_not_called()
    def test_retrieve_mismatch_fails_closed(self):
        self.s.retrieve.return_value=NS(id='sess_other',metadata=self.m)
        with self.assertRaises(r.RecoveryBlocked): self.go()
        self.s.delete.assert_not_called()
    def test_exact_match_cleanup(self):
        self.assertEqual(self.go()['status'],'deletion_confirmed')
        self.s.list.assert_called_once_with(metadata=self.m,limit=2)
        self.s.delete.assert_called_once_with('sess_test')
        self.s.create.assert_not_called(); self.s.stream.assert_not_called()
        self.client.with_options.assert_called_once_with(max_retries=0,timeout=20)
    def test_lost_delete_response_not_success(self):
        self.s.delete.side_effect=TimeoutError()
        result = self.go()
        self.assertEqual(result['status'],'provider_outcome_unresolved')
        self.assertEqual(result['session_id'],'sess_test')
        self.s.delete.assert_called_once()
    def test_ambiguous_delete_response_not_success(self):
        self.s.delete.return_value=None
        self.assertEqual(self.go()['status'],'cleanup_unconfirmed')
    def test_cancel_failure_still_deletes(self):
        self.s.events.create.side_effect=RuntimeError()
        self.assertEqual(self.go()['status'],'deletion_confirmed')

if __name__=='__main__': unittest.main()

class SDKAttemptContractTests(unittest.TestCase):
    def test_real_sdk_filtered_lookup_cancel_delete_without_network(self):
        from openai import OpenAI
        import httpx2
        metadata=r.attempt_metadata(123,1,'a'*40)
        calls=[]
        session={'id':'sess_test','object':'agent.session','created_at':0,'last_active_at':0,
                 'agent':{'model':'gpt-6-astra'},'environment':{'type':'openai_hosted','id':'env_test'},
                 'metadata':metadata,'required_actions':[],'status':'idle','vault_ids':[]}
        def handle(req):
            calls.append((req.method,req.url.path))
            if req.method=='GET' and req.url.path.endswith('/sessions'):
                for key,value in metadata.items():
                    self.assertEqual(req.url.params.get('metadata['+key+']'),value)
                self.assertEqual(req.url.params.get('limit'),'2')
                return httpx2.Response(200,json={'object':'list','data':[session],'has_more':False})
            if req.method=='GET': return httpx2.Response(200,json=session)
            if req.method=='DELETE': return httpx2.Response(200,json={'id':'sess_test','object':'agent.session.deleted','deleted':True})
            if req.url.path.endswith('/events'): return httpx2.Response(200,json={})
            self.fail('Unexpected API path')
        with OpenAI(api_key='offline-test-only',http_client=httpx2.Client(transport=httpx2.MockTransport(handle))) as client:
            self.assertEqual(r.reconcile(client,metadata,execute=True)['status'],'deletion_confirmed')
        self.assertEqual([method for method,path in calls],['GET','GET','POST','DELETE'])
