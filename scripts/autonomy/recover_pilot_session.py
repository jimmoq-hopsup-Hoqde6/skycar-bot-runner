#!/usr/bin/env python3
"""Exact-session recovery primitive. No creation, inference, discovery or scheduling.

Use from an independently hosted supervisor with a trusted receipt. This module
alone is NOT a durable watchdog and never establishes an all-in spending ceiling.
"""
import re
import time

REPOSITORY = 'jimmoq-hopsup-Hoqde6/skycar-site'
COMMIT = 'f10a36fe98961dc1dcfbace37d9323752e1f3ffe'
TASK = 'queue-input-validation-v1'


class RecoveryBlocked(Exception):
    pass


def validate_receipt(receipt):
    """Receipt must come from the controller, not generated code/artifacts."""
    if not isinstance(receipt, dict) or set(receipt) != {'session_id', 'repository', 'commit', 'task'}:
        raise RecoveryBlocked('Incomplete trusted receipt; do not guess a session')
    sid = receipt['session_id']
    if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', sid):
        raise RecoveryBlocked('Invalid session identifier')
    if (receipt['repository'], receipt['commit'], receipt['task']) != (REPOSITORY, COMMIT, TASK):
        raise RecoveryBlocked('Receipt is outside reviewed pilot scope')
    return sid


def recover(client, receipt, *, execute=False, sleep=time.sleep):
    """Bounded, exact-session cleanup; default makes zero API calls.

A 404 is recorded as unavailable, NOT proof of deletion or zero billing. A
successful deletion response must explicitly identify this session and deleted=True.
No retry on authentication, rate-limit, transport, or ambiguous failures.
"""
    if type(execute) is not bool:
        raise RecoveryBlocked('Execution flag must be a boolean')
    sid = validate_receipt(receipt)
    if not execute:
        return {'status': 'offline_plan', 'session_id': sid}
    client = client.with_options(max_retries=0, timeout=20)
    sessions = client.beta.agents.sessions
    try:
        session = sessions.retrieve(sid)
    except Exception as exc:
        if getattr(exc, 'status_code', None) == 404:
            return {'status': 'unavailable_not_verified_deleted', 'session_id': sid}
        raise RecoveryBlocked('Session lookup failed; reconcile manually') from None
    if session.id != sid or session.metadata != {k: receipt[k] for k in ('repository', 'commit', 'task')}:
        raise RecoveryBlocked('Remote identity or metadata mismatch; no mutation performed')
    # Cancellation can fail for an already idle turn; exact-session deletion remains
    # safe. Never include provider error bodies or source/model output in receipts.
    cancel = 'requested'
    try:
        sessions.events.create(sid, events=[{'type': 'agent.session.input.cancel'}])
    except Exception:
        cancel = 'unconfirmed'
    for attempt in range(3):
        try:
            result = sessions.delete(sid)
        except Exception as exc:
            if getattr(exc, 'status_code', None) == 409 and attempt < 2:
                sleep(2)
                continue
            return {'status': 'cleanup_unconfirmed', 'session_id': sid, 'cancel': cancel}
        if getattr(result, 'id', None) == sid and getattr(result, 'deleted', None) is True:
            return {'status': 'deletion_confirmed', 'session_id': sid, 'cancel': cancel}
        return {'status': 'cleanup_unconfirmed', 'session_id': sid, 'cancel': cancel}
    raise AssertionError('Unreachable')
