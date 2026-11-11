import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[2] / 'scripts/autonomy/team_bootstrap.py'
spec = importlib.util.spec_from_file_location('team', path)
team = importlib.util.module_from_spec(spec)
spec.loader.exec_module(team)


class TeamTests(unittest.TestCase):
    def test_role_sessions_are_isolated_and_bounded(self):
        self.assertEqual(len(team.ROLES), 9)
        for role in team.ROLES:
            pilot, req = team.request_for(role, 'a' * 40, {}, {})
            self.assertEqual(req['spend_control']['limit'], 100)
            self.assertEqual(req['environment']['network']['access'], 'disabled')
            self.assertEqual(req['environment']['env'], {})
            self.assertFalse(req['agent']['multi_agent']['enabled'])
            other = next(r for r in team.ROLES if r != role)
            with self.assertRaises(pilot.PilotError):
                pilot.validate_artifact(json.dumps({'task_id': pilot.TASK_ID, 'files': [
                    {'path': 'reports/' + other + '.md', 'content': 'wrong role'}]}).encode())

    def test_handoffs_are_bound_to_request_fingerprint(self):
        pilot, req = team.request_for('qa', 'a' * 40, {}, {'backend': 'first'})
        _, changed = team.request_for('qa', 'a' * 40, {}, {'backend': 'second'})
        self.assertNotEqual(pilot.fingerprint(req), pilot.fingerprint(changed))

    def test_fail_closed_and_do_not_run_remaining_roles(self):
        calls = []
        original = team.request_for
        def prepare(role, *args):
            pilot, req = original(role, *args)
            def execute(*args):
                calls.append(role)
                raise pilot.PilotError('blocked')
            pilot.execute = execute
            return pilot, req
        with tempfile.TemporaryDirectory() as temp, patch.object(team, 'request_for', prepare):
            out = Path(temp) / 'cycle'
            with self.assertRaises(Exception):
                team.run(None, out, 'a' * 40, {})
            self.assertEqual(calls, ['project-manager'])
            self.assertEqual(json.loads((out / 'summary.json').read_text())['status'], 'blocked_reconcile_before_retry')

    def test_all_roles_receive_preceding_reports(self):
        seen = {}
        original = team.request_for
        def prepare(role, sha, context, previous):
            seen[role] = set(previous)
            pilot, req = original(role, sha, context, previous)
            def execute(client, request, out, token):
                out.mkdir()
                (out / 'changes.json').write_text(json.dumps({'task_id': pilot.TASK_ID,
                    'files': [{'path': pilot.ALLOWED_FILES[0], 'content': role + ' report'}]}))
                return {'status': 'artifact_validated_NOT_TESTED'}
            pilot.execute = execute
            return pilot, req
        with tempfile.TemporaryDirectory() as temp, patch.object(team, 'request_for', prepare):
            out = Path(temp) / 'cycle'
            result = team.run(None, out, 'a' * 40, {})
            self.assertEqual(len(result['roles']), 9)
            self.assertIn('qa', seen['security'])
            self.assertIn('security', seen['release'])
            with self.assertRaises(FileExistsError):
                team.run(None, out, 'a' * 40, {})

    def test_unknown_role_and_oversize_context_blocked(self):
        with self.assertRaises(ValueError):
            team.new_pilot('../../escape')
        with self.assertRaises(ValueError):
            team.request_for('qa', 'a' * 40, {'large': 'x' * 500_001}, {})
