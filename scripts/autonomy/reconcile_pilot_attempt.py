"""Reconstruct recovery identity from a trusted, durable GitHub Actions run record.

No scheduler, key loading, session creation or task submission. Call separately
from the failed runner. Empty filtered results are always unresolved because the
provider's metadata index is eventually consistent.
"""
import re
from recover_pilot_session import RecoveryBlocked, REPOSITORY, COMMIT, TASK

RUNNER_REPOSITORY = 'jimmoq-hopsup-Hoqde6/skycar-bot-runner'


def attempt_metadata(run_id, run_attempt, workflow_sha):
    # Native ints only; reject bools, supplied URLs, branch names and expressions.
    if type(run_id) is not int or not 1 <= run_id < 10**20:
        raise RecoveryBlocked('Invalid run identity')
    if type(run_attempt) is not int or run_attempt != 1:
        raise RecoveryBlocked('Only the original reviewed attempt is eligible')
    if not isinstance(workflow_sha, str) or not re.fullmatch('[0-9a-f]{40}', workflow_sha):
        raise RecoveryBlocked('Expected immutable workflow commit')
    return {'repository': REPOSITORY, 'commit': COMMIT, 'task': TASK,
            'runner_repository': RUNNER_REPOSITORY,
            'runner_run_id': str(run_id), 'runner_run_attempt': '1',
            'runner_workflow_sha': workflow_sha}


def reconcile(client, metadata, *, execute=False):
    """Read one bounded page and recover only an unambiguous exact match.

Caller must derive metadata from independently verified GitHub run data, not a
model artifact or user-editable dispatch input. Repeated checks require supervisor
scheduling; this primitive never sleeps or loops across pages indefinitely.
"""
    if type(execute) is not bool:
        raise RecoveryBlocked('Execution flag must be boolean')
    if not isinstance(metadata, dict):
        raise RecoveryBlocked('Invalid attempt metadata')
    try:
        expected = attempt_metadata(int(metadata['runner_run_id']),
                                    int(metadata['runner_run_attempt']),
                                    metadata['runner_workflow_sha'])
    except (KeyError, TypeError, ValueError):
        raise RecoveryBlocked('Incomplete attempt metadata') from None
    if metadata != expected:
        raise RecoveryBlocked('Unexpected attempt metadata')
    if not execute:
        return {'status': 'offline_plan', 'may_create_again': False}
    client = client.with_options(max_retries=0, timeout=20)
    sessions = client.beta.agents.sessions
    verified_sid = None
    try:
        # limit=2 is deliberate: duplicates cannot silently choose the first ID.
        page = sessions.list(metadata=expected, limit=2)
        matches = page.data
        if page.has_next_page() or len(matches) > 1:
            return {'status': 'ambiguous_manual_reconciliation', 'may_create_again': False}
        if not matches:
            return {'status': 'not_visible_yet_unresolved', 'may_create_again': False}
        candidate = matches[0]
        sid = candidate.id
        if not isinstance(sid, str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}', sid):
            raise RecoveryBlocked('Invalid provider session identity')
        if candidate.metadata != expected:
            raise RecoveryBlocked('Filtered result scope mismatch')
        current = sessions.retrieve(sid)
        if current.id != sid or current.metadata != expected:
            raise RecoveryBlocked('Retrieved session scope mismatch')
        verified_sid = sid
        try:
            sessions.events.create(sid, events=[{'type': 'agent.session.input.cancel'}])
        except Exception:
            pass
        result = sessions.delete(sid)
        if getattr(result, 'id', None) == sid and getattr(result, 'deleted', None) is True:
            return {'status': 'deletion_confirmed', 'session_id': sid, 'may_create_again': False}
        return {'status': 'cleanup_unconfirmed', 'session_id': sid, 'may_create_again': False}
    except RecoveryBlocked:
        raise
    except Exception:
        # Even deletion success followed by response loss must remain unresolved.
        outcome = {'status': 'provider_outcome_unresolved', 'may_create_again': False}
        if verified_sid is not None:
            outcome['session_id'] = verified_sid
        return outcome
