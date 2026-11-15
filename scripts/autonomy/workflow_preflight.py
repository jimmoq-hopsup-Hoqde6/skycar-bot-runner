"""Offline, run-bound scope receipt. No credentials or provider calls."""
import json
import re
from pathlib import Path
from bounded_coding_pilot import build_request, bind_attempt, fingerprint, source_snapshot, ALLOWED_FILES, MODEL, TASK_ID, PilotError
from reconcile_pilot_attempt import RUNNER_REPOSITORY, COMMIT


def preflight(root, controller, context):
    if (context.get('GITHUB_REPOSITORY') != RUNNER_REPOSITORY or
            context.get('GITHUB_REF') != 'refs/heads/main' or
            context.get('GITHUB_EVENT_NAME') != 'workflow_dispatch' or
            context.get('GITHUB_RUN_ATTEMPT') != '1'):
        raise PilotError('Only the original default-branch manual run is eligible')
    run_id = context.get('GITHUB_RUN_ID', '')
    sha = context.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[1-9][0-9]{0,19}', run_id) or not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise PilotError('Invalid trusted run context')
    from bounded_coding_pilot import git
    if git(controller, 'rev-parse', 'HEAD').decode().strip() != sha:
        raise PilotError('Controller checkout differs from workflow commit')
    request = bind_attempt(build_request(source_snapshot(root, COMMIT), COMMIT, 100), int(run_id), 1, sha)
    return {'mode': 'offline_preflight', 'task': TASK_ID, 'sha': COMMIT,
            'paths': ALLOWED_FILES, 'model': MODEL, 'session_budget_cents': 100,
            'request_fingerprint': fingerprint(request), 'attempt_metadata': request['metadata'],
            'network': 'disabled', 'writes': 'artifact_only', 'schedule': 'none',
            'activation': 'BLOCKED_pending_independent_supervisor_and_cost_verification'}


if __name__ == '__main__':
    import argparse
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--controller', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(preflight(args.root, args.controller, os.environ), indent=2))
