"""One read-only inventory of fixed attempt. No creation, cancellation or deletion."""
import json
import os
import re
from pathlib import Path

METADATA = {
    'repository': 'jimmoq-hopsup-Hoqde6/skycar-site',
    'commit': 'f10a36fe98961dc1dcfbace37d9323752e1f3ffe',
    'task': 'queue-input-validation-v1',
    'runner_repository': 'jimmoq-hopsup-Hoqde6/skycar-bot-runner',
    'runner_run_id': '43710989241',
    'runner_run_attempt': '1',
    'runner_workflow_sha': 'b3ccfe2453a6412086cff24b0d66c96fc2eed710',
}
PROJECT = 'proj_6X0oPYbwi6a70uC4NP5AXiso'
ORGANIZATION = 'org-V1oEpSPDNO3avc8qQT0useW2'


def inventory(client):
    result = {'schema': 'skycar-readonly-inventory-v1',
              'producer_run_id': 43710989241, 'may_create_again': False,
              'supervision_required': True}
    try:
        sessions = client.with_options(max_retries=0, timeout=20).beta.agents.sessions
        page = sessions.list(metadata=dict(METADATA), limit=2)
        matches = page.data
        if page.has_next_page() or len(matches) > 1:
            return dict(result, status='ambiguous_unresolved')
        if not matches:
            return dict(result, status='not_visible_unresolved')
        candidate = matches[0]
        sid = candidate.id
        if (not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', sid)
                or candidate.metadata != METADATA):
            return dict(result, status='scope_mismatch_unresolved')
        current = sessions.retrieve(sid)
        if current.id != sid or current.metadata != METADATA:
            return dict(result, status='scope_mismatch_unresolved')
        # Only validated ID is emitted. No raw status, metadata, events or exception.
        return dict(result, status='matching_session_present', session_id=sid)
    except Exception:
        return dict(result, status='provider_read_failed_unresolved')


def trusted_context(env):
    return (env.get('GITHUB_REPOSITORY') == METADATA['runner_repository']
            and env.get('GITHUB_REF') == 'refs/heads/main'
            and env.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
            and env.get('GITHUB_RUN_ATTEMPT') == '1')


def main():
    if not trusted_context(os.environ):
        raise SystemExit('Inventory blocked: untrusted context')
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from openai import OpenAI
    with OpenAI(api_key=os.environ['OPENAI_API_KEY'], project=PROJECT,
                organization=ORGANIZATION, base_url='https://api.openai.com/v1',
                max_retries=0, timeout=20) as client:
        result = inventory(client)
    args.output.write_text(json.dumps(result, sort_keys=True))
    # Successful observation is not cleanup or permission for another pilot.
    if result['status'] != 'matching_session_present':
        raise SystemExit('Inventory unresolved; inspect safe artifact')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Inventory failed; no retry or creation authorized') from None
