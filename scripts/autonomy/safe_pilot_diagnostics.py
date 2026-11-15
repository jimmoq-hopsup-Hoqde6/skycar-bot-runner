"""Constant-only diagnostics. Never serialize exceptions or external values."""
from contextlib import contextmanager
import sys
from recover_pilot_session import RecoveryBlocked

REASONS = frozenset({
    'RECEIPT_MISMATCH', 'RECEIPT_EXPIRED', 'LEASE_INSUFFICIENT',
    'RECOVERY_NOT_LIVE', 'CLAIM_REJECTED', 'FINGERPRINT_MISMATCH',
})
PHASES = frozenset({
    'DISCOVERY', 'ARCHIVE_DOWNLOAD', 'INITIAL_RECORDS', 'RECEIPT_VERIFICATION',
    'RECEIPT_METADATA', 'LIVE_RECORD_RECHECK', 'AUTHORIZATION', 'FINGERPRINT_VALIDATION',
    'EXECUTION_ENTRY',
})


class DiagnosticBlocked(RecoveryBlocked):
    def __init__(self, code):
        self.code = code if type(code) is str and code in REASONS else 'UNEXPECTED_FAILURE'
        super().__init__('Supervised gate blocked')


def reason(error):
    # Only this exact local error type can supply a reason, and even its code
    # is revalidated: no str(error), repr(error), traceback or provider content.
    code = error.code if type(error) is DiagnosticBlocked else None
    return code if type(code) is str and code in REASONS else 'UNEXPECTED_FAILURE'


@contextmanager
def phase(name):
    if type(name) is not str or name not in PHASES:
        raise RecoveryBlocked('Unknown diagnostic phase')
    print('PILOT_PHASE ' + name + ' START', file=sys.stderr, flush=True)
    try:
        yield
    except Exception as error:
        print('PILOT_PHASE ' + name + ' BLOCKED ' + reason(error),
              file=sys.stderr, flush=True)
        raise
    print('PILOT_PHASE ' + name + ' COMPLETE', file=sys.stderr, flush=True)
