import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/autonomy'))
import inventory_previous_attempt as m

class Sessions:
    def __init__(self, entries=(), more=False, current=None, fail=False):
        self.entries=list(entries); self.more=more; self.current=current; self.fail=fail; self.calls=[]
    def list(self, **kw):
        self.calls.append(('list', kw))
        if self.fail: raise RuntimeError('sk-secret-do-not-emit')
        return NS(data=self.entries, has_next_page=lambda:self.more)
    def retrieve(self, sid):
        self.calls.append(('retrieve', sid)); return self.current or self.entries[0]
    def __getattr__(self, name):
        raise AssertionError('Non-read operation: '+name)

class Client:
    def __init__(self, sessions): self.beta=NS(agents=NS(sessions=sessions))
    def with_options(self, **kw):
        assert kw == {'max_retries':0,'timeout':20}
        return self

class Tests(unittest.TestCase):
    def run_inventory(self,s):
        r=m.inventory(Client(s)); self.assertFalse(r['may_create_again']); self.assertTrue(r['supervision_required']); return r
    def test_empty_remains_unresolved(self):
        s=Sessions(); self.assertEqual(self.run_inventory(s)['status'],'not_visible_unresolved')
        self.assertEqual(s.calls,[('list',{'metadata':m.METADATA,'limit':2})])
    def test_present_verified_with_read_only_calls(self):
        s=Sessions([NS(id='session_123',metadata=m.METADATA)])
        self.assertEqual(self.run_inventory(s)['session_id'],'session_123')
        self.assertEqual([c[0] for c in s.calls],['list','retrieve'])
    def test_duplicates_and_pagination_stop(self):
        for s in (Sessions([None,None]),Sessions([],more=True)):
            self.assertEqual(self.run_inventory(s)['status'],'ambiguous_unresolved'); self.assertEqual(len(s.calls),1)
    def test_invalid_id_and_metadata_stop(self):
        for c in (NS(id='bad\nsecret',metadata=m.METADATA),NS(id='valid',metadata={})):
            s=Sessions([c]); self.assertEqual(self.run_inventory(s)['status'],'scope_mismatch_unresolved'); self.assertEqual(len(s.calls),1)
    def test_retrieved_identity_mismatch(self):
        s=Sessions([NS(id='valid',metadata=m.METADATA)],current=NS(id='other',metadata=m.METADATA))
        self.assertEqual(self.run_inventory(s)['status'],'scope_mismatch_unresolved')
    def test_exception_not_leaked(self):
        r=self.run_inventory(Sessions(fail=True)); self.assertNotIn('sk-secret',str(r)); self.assertEqual(r['status'],'provider_read_failed_unresolved')
    def test_context_all_fields_required(self):
        env={'GITHUB_REPOSITORY':m.METADATA['runner_repository'],'GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_RUN_ATTEMPT':'1'}
        self.assertTrue(m.trusted_context(env))
        for k in env:
            wrong=dict(env); wrong[k]='other'; self.assertFalse(m.trusted_context(wrong))
    def test_workflow_keeps_protection_and_no_inputs(self):
        w=(Path(__file__).resolve().parents[2]/'.github/workflows/previous-attempt-inventory.yml').read_text()
        self.assertIn('environment: skycar-agent-pilot',w); self.assertNotIn('inputs:',w)
        self.assertIn('persist-credentials: false',w); self.assertNotIn('actions: write',w)
        self.assertEqual(w.count('SKYCAR_PILOT_OPENAI_API_KEY'),1)

if __name__=='__main__': unittest.main()
