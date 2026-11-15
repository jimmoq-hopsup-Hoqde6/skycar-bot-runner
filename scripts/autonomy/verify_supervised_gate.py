"""Trusted GitHub records + digest-bound archive -> one-use supervised gate.

Archive bytes come from a separate bounded download step. Metadata is fetched
from the exact authenticated GitHub run, never accepted from downloaded content.
No provider calls, dispatch, credential loading or artifact extraction occurs.
"""
import urllib.request
from safe_pilot_diagnostics import phase
from github_recovery_records import fetch_records, _read, NoRedirect
from recovery_receipt import read_receipt
from supervised_recovery_handshake import authorize, RecoveryBlocked


def verify(producer_id, recovery_id, sha, token, archive, clock, *, claim, opener=None):
    opener = opener or urllib.request.build_opener(NoRedirect())
    with phase('INITIAL_RECORDS'):
        producer, recovery, job = fetch_records(producer_id, recovery_id, sha, token, opener=opener)
    with phase('RECEIPT_METADATA'):
        page = _read('/actions/runs/' + str(recovery_id) + '/artifacts?per_page=100', token, opener)
        artifacts = page.get('artifacts')
        if (not isinstance(artifacts, list) or type(page.get('total_count')) is not int
                or not 1 <= page['total_count'] <= 100 or page['total_count'] != len(artifacts)
                or any(not isinstance(a, dict) for a in artifacts)):
            raise RecoveryBlocked('Incomplete recovery artifact listing')
        matches = [a for a in artifacts if a.get('name') == 'pilot-recovery-armed-' + str(producer_id)]
        if len(matches) != 1:
            raise RecoveryBlocked('Arming artifact absent or ambiguous')
    with phase('RECEIPT_VERIFICATION'):
        receipt = read_receipt(matches[0], archive, recovery, producer_id)
    # Re-fetch after archive validation to narrow the time-of-check race. A process
    # can still fail immediately afterward; this is not future liveness proof.
    with phase('LIVE_RECORD_RECHECK'):
        producer, recovery, job = fetch_records(producer_id, recovery_id, sha, token, opener=opener)
    with phase('AUTHORIZATION'):
        return authorize(receipt, producer, recovery, job, clock(), claim=claim)
