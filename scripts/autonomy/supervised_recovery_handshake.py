"""Offline-testable supervised handshake. No key loading, networking or dispatch.

All records must be independently fetched by a trusted adapter. This module does
not authenticate dicts; a receipt from an artifact alone is never sufficient.
"""
import re
from reconcile_pilot_attempt import attempt_metadata, reconcile, RUNNER_REPOSITORY
from recover_pilot_session import RecoveryBlocked

SCHEMA = 'skycar-supervised-recovery-v1'
PRODUCER_PATH = '.github/workflows/one-coding-bot.yml'
RECOVERY_PATH = '.github/workflows/supervised-recovery.yml'
LEASE_SECONDS = 1200
MAX_RECEIPT_AGE = 180
PRODUCER_SECONDS = 600
CLEANUP_MARGIN = 120
POLL_SECONDS = 20
MAX_POLLS = 6


def integer(value, name):
    if type(value) is not int or value < 1:
        raise RecoveryBlocked('Invalid ' + name)
    return value


def trusted_run(run, path, *, expected_id=None, expected_sha=None):
    if not isinstance(run, dict):
        raise RecoveryBlocked('Missing trusted run')
    rid = integer(run.get('id'), 'run id')
    sha = run.get('head_sha')
    if (not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{40}', sha)
            or run.get('repository', {}).get('full_name') != RUNNER_REPOSITORY
            or run.get('event') != 'workflow_dispatch' or run.get('head_branch') != 'main'
            or run.get('path') != path or type(run.get('run_attempt')) is not int or run.get('run_attempt') != 1
            or run.get('status') not in ('queued', 'waiting', 'in_progress')
            or run.get('conclusion') is not None):
        raise RecoveryBlocked('Run is outside supervised scope')
    if expected_id is not None and rid != expected_id:
        raise RecoveryBlocked('Run identity changed')
    if expected_sha is not None and sha != expected_sha:
        raise RecoveryBlocked('Controller revision changed')
    return rid, sha


def arm(producer_run, recovery_run, now, probe, persist):
    """Require successful provider-read probe and durable receipt before proceeding.

probe must use the correct project and exact metadata; persist must durably write
and positively acknowledge this exact receipt. Neither callback may create a
session. Exception/negative acknowledgement means no producer authorization.
"""
    integer(now, 'time')
    pid, sha = trusted_run(producer_run, PRODUCER_PATH)
    rid, _ = trusted_run(recovery_run, RECOVERY_PATH, expected_sha=sha)
    if rid == pid or recovery_run['status'] != 'in_progress':
        raise RecoveryBlocked('Separate running recovery required')
    metadata = attempt_metadata(pid, 1, sha)
    if probe(metadata) is not True:
        raise RecoveryBlocked('Recovery provider read not verified')
    receipt = dict(schema=SCHEMA, producer_run_id=pid, recovery_run_id=rid,
                   workflow_sha=sha, metadata=metadata, armed_at=now,
                   stop_at=now + LEASE_SECONDS)
    if persist(receipt) is not True:
        raise RecoveryBlocked('No durable arming acknowledgement')
    return receipt


def authorize(receipt, producer_run, recovery_run, recovery_job, now, *, claim=None):
    """Fresh receipt + independently fetched live job proof; never a lifetime guarantee."""
    integer(now, 'time')
    if not isinstance(receipt, dict) or set(receipt) != {'schema','producer_run_id','recovery_run_id','workflow_sha','metadata','armed_at','stop_at'}:
        raise RecoveryBlocked('Invalid receipt shape')
    pid, sha = trusted_run(producer_run, PRODUCER_PATH)
    rid, _ = trusted_run(recovery_run, RECOVERY_PATH, expected_sha=sha)
    armed = integer(receipt['armed_at'], 'armed time')
    stop = integer(receipt['stop_at'], 'stop time')
    if (receipt['schema'] != SCHEMA or receipt['producer_run_id'] != pid
            or receipt['recovery_run_id'] != rid or pid == rid
            or receipt['workflow_sha'] != sha or receipt['metadata'] != attempt_metadata(pid, 1, sha)
            or stop != armed + LEASE_SECONDS or not 0 <= now - armed <= MAX_RECEIPT_AGE
            or stop - now < PRODUCER_SECONDS + CLEANUP_MARGIN
            or recovery_run['status'] != 'in_progress'):
        raise RecoveryBlocked('Stale or mismatched arming receipt')
    if (recovery_job.get('run_id') != rid or recovery_job.get('run_attempt') != 1
            or recovery_job.get('head_sha') != sha or recovery_job.get('name') != 'supervised-recovery'
            or recovery_job.get('status') != 'in_progress' or recovery_job.get('conclusion') is not None):
        raise RecoveryBlocked('Recovery job is not independently verified running')
    steps = recovery_job.get('steps', [])
    arm_steps = [s for s in steps if s.get('name') == 'Publish arming receipt']
    loops = [s for s in steps if s.get('name') == 'Bounded recovery loop']
    if (len(arm_steps) != 1 or arm_steps[0].get('status') != 'completed' or arm_steps[0].get('conclusion') != 'success'
            or len(loops) != 1 or loops[0].get('status') != 'in_progress'):
        raise RecoveryBlocked('No positive arming and live loop proof')
    # Adapter must atomically claim one immutable producer identity in durable storage.
    # A failed/lost claim response is unresolved, never permission to retry creation.
    if claim is None or claim(receipt['metadata']) is not True:
        raise RecoveryBlocked('Single-use durable claim not acknowledged')
    return {'authorized_for_one_creation': True, 'metadata': receipt['metadata'],
            'latest_cleanup_at': stop, 'hard_deadline_guaranteed': False}


def cleanup_window(client, metadata, *, deadline, clock, sleep, persist):
    """Finite reconciliation only. Unknown outcomes never authorize recreation.

Call only after supervised task deadline/cancellation. Caller owns that trigger.
No raw exceptions, generated text or key values are included in persisted result.
"""
    last = {'status': 'deadline_exhausted_unresolved', 'may_create_again': False}
    for _ in range(MAX_POLLS):
        if clock() >= deadline:
            break
        try:
            last = reconcile(client, metadata, execute=True)
        except Exception:
            last = {'status': 'reconciliation_blocked_unresolved', 'may_create_again': False}
        try:
            saved = persist(last) is True
        except Exception:
            saved = False
        if not saved:
            return dict(last, status='result_persistence_unconfirmed',
                        reconciliation_status=last['status'], may_create_again=False)
        if last['status'] == 'deletion_confirmed':
            return last
        remaining = deadline - clock()
        if remaining <= 0:
            break
        sleep(min(POLL_SECONDS, remaining))
    return dict(last, may_create_again=False, supervision_required=True)
