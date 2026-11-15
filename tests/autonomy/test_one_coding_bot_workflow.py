"""Offline regressions for the manual one-task workflow's safety boundaries."""
import unittest
from pathlib import Path
class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (Path(__file__).resolve().parents[2] / '.github/workflows/one-coding-bot.yml').read_text()
    def test_manual_opt_in(self):
        self.assertIn('workflow_dispatch:', self.workflow)
        self.assertIn('default: false', self.workflow)
        self.assertNotIn('schedule:', self.workflow)
    def test_review_gate(self):
        self.assertIn('environment: skycar-agent-pilot', self.workflow)
        self.assertIn('if: ${{ false }}', self.workflow)
        self.assertIn('REVIEWED_FINGERPRINT: ${{ needs.preflight.outputs.fingerprint }}', self.workflow)
        self.assertNotIn('inputs.request_fingerprint', self.workflow)
        self.assertIn("github.run_attempt == 1", self.workflow)
        self.assertIn("github.ref == 'refs/heads/main'", self.workflow)
    def test_secret_only_execution(self):
        self.assertEqual(self.workflow.count('$' + '{{ secrets.'), 1)
        self.assertIn("OPENAI_API_KEY: ''", self.workflow)
        self.assertIn('contents: read', self.workflow)
        self.assertNotIn('write', self.workflow.split('jobs:')[0])
    def test_dedicated_environment_key_name(self):
        self.assertIn('secrets.SKYCAR_PILOT_OPENAI_API_KEY', self.workflow)
        self.assertNotIn('secrets.OPENAI_API_KEY', self.workflow)
    def test_exact_source(self):
        self.assertEqual(self.workflow.count('persist-credentials: false'), 4)
        self.assertEqual(self.workflow.count('ref: f10a36fe98961dc1dcfbace37d9323752e1f3ffe'), 2)
    def test_separate_pinned_controller_and_input(self):
        self.assertEqual(self.workflow.count('ref: ${{ github.sha }}'), 2)
        self.assertEqual(self.workflow.count('path: controller'), 2)
        self.assertEqual(self.workflow.count('path: app'), 2)
        self.assertIn('--run-id "$TRUSTED_RUN_ID"', self.workflow)
        self.assertIn('GITHUB_STEP_SUMMARY', self.workflow)
    def test_evidence_not_publication(self):
        self.assertIn('if: always()', self.workflow)
        self.assertIn('review_pilot_artifact.py', self.workflow)
        for command in ('git push', 'gh pr create', 'gh pr merge', 'vercel deploy'):
            self.assertNotIn(command, self.workflow)
if __name__ == '__main__':
    unittest.main()

