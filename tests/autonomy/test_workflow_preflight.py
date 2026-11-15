import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/autonomy'))
import workflow_preflight as p

class WorkflowPreflightTests(unittest.TestCase):
    def context(self):
        return dict(GITHUB_REPOSITORY=p.RUNNER_REPOSITORY,GITHUB_REF='refs/heads/main',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_RUN_ATTEMPT='1',GITHUB_RUN_ID='123',GITHUB_SHA='a'*40)
    def run_scope(self,c):
        with patch('bounded_coding_pilot.git',return_value=('a'*40+'\n').encode()), patch.object(p,'source_snapshot',return_value={x:b'# source\n' for x in p.ALLOWED_FILES}):
            return p.preflight(Path('app'),Path('controller'),c)
    def test_exact_context_and_no_activation(self):
        out=self.run_scope(self.context())
        self.assertEqual(out['attempt_metadata']['runner_run_id'],'123')
        self.assertEqual(out['sha'],p.COMMIT)
        self.assertTrue(out['activation'].startswith('AWAITING'))
    def test_reject_untrusted_context(self):
        for field,value in [('GITHUB_REPOSITORY','wrong/repo'),('GITHUB_REF','refs/heads/other'),('GITHUB_EVENT_NAME','pull_request'),('GITHUB_RUN_ATTEMPT','2'),('GITHUB_RUN_ID','0123'),('GITHUB_RUN_ID','x'),('GITHUB_SHA','main')]:
            c=self.context();c[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(p.PilotError):self.run_scope(c)
    def test_reject_controller_mismatch(self):
        c=self.context();c['GITHUB_SHA']='b'*40
        with self.assertRaises(p.PilotError):self.run_scope(c)
    def test_run_identity_changes_fingerprint(self):
        c=self.context();a=self.run_scope(c);c['GITHUB_RUN_ID']='124'
        self.assertNotEqual(a['request_fingerprint'],self.run_scope(c)['request_fingerprint'])

if __name__=='__main__':unittest.main()
