"""Read exact GitHub recovery records. No dispatch, mutation, or secret loading.

The caller supplies its existing GitHub read token. URLs are fixed to this repo;
redirects are forbidden. One bounded jobs page is accepted, never guessed through.
"""
import json
import urllib.request
from recover_pilot_session import RecoveryBlocked
from supervised_recovery_handshake import trusted_run, PRODUCER_PATH, RECOVERY_PATH
from reconcile_pilot_attempt import RUNNER_REPOSITORY

BASE = 'https://api.github.com/repos/' + RUNNER_REPOSITORY
MAX_BYTES = 1_000_000
TIMEOUT = 15


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RecoveryBlocked('GitHub redirect refused')


def _id(value):
    if type(value) is not int or not 1 <= value < 10**20:
        raise RecoveryBlocked('Invalid GitHub run ID')
    return str(value)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryBlocked('Duplicate GitHub response field')
        result[key] = value
    return result


def _read(path, token, opener):
    request = urllib.request.Request(BASE + path, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'skycar-supervised-recovery',
    })
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            if response.status != 200 or response.geturl() != request.full_url:
                raise RecoveryBlocked('Unexpected GitHub response')
            # An unconsumed page could contain another matching job.
            if response.headers.get('Link'):
                raise RecoveryBlocked('Paginated GitHub response requires reconciliation')
            if response.headers.get_content_type() != 'application/json':
                raise RecoveryBlocked('Unexpected GitHub content type')
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise RecoveryBlocked('GitHub response too large')
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique)
        if not isinstance(data, dict):
            raise RecoveryBlocked('Invalid GitHub response shape')
        return data
    except RecoveryBlocked:
        raise
    except Exception:
        # Do not expose request headers, provider bodies, tokens, or URLs from errors.
        raise RecoveryBlocked('GitHub read failed; reconcile manually') from None


def fetch_records(producer_id, recovery_id, expected_sha, token, *, opener=None):
    """Return independently fetched run/run/job records for authorize().

Only live first attempts on the exact reviewed main-branch SHA are accepted.
This does not approve a deployment, arm cleanup, or provide a durable claim.
"""
    pid, rid = _id(producer_id), _id(recovery_id)
    if pid == rid:
        raise RecoveryBlocked('Separate recovery run required')
    import re
    if not isinstance(expected_sha, str) or not re.fullmatch('[a-f0-9]{40}', expected_sha):
        raise RecoveryBlocked('Invalid reviewed SHA')
    if not isinstance(token, str) or not token or any(c.isspace() for c in token):
        raise RecoveryBlocked('Existing GitHub read credential required')
    if opener is None:
        opener = urllib.request.build_opener(NoRedirect())
    producer = _read('/actions/runs/' + pid, token, opener)
    trusted_run(producer, PRODUCER_PATH, expected_id=producer_id, expected_sha=expected_sha)
    recovery = _read('/actions/runs/' + rid, token, opener)
    trusted_run(recovery, RECOVERY_PATH, expected_id=recovery_id, expected_sha=expected_sha)
    if recovery['status'] != 'in_progress':
        raise RecoveryBlocked('Recovery is not running')
    page = _read('/actions/runs/' + rid + '/attempts/1/jobs?per_page=100', token, opener)
    jobs, count = page.get('jobs'), page.get('total_count')
    if (not isinstance(jobs, list) or type(count) is not int or
            not 1 <= count <= 100 or count != len(jobs)):
        raise RecoveryBlocked('Incomplete or oversized GitHub jobs page')
    if any(not isinstance(j, dict) or j.get('run_id') != recovery_id or
           j.get('head_sha') != expected_sha or j.get('run_attempt') != 1 for j in jobs):
        raise RecoveryBlocked('GitHub job identity mismatch')
    matches = [j for j in jobs if j.get('name') == 'supervised-recovery']
    if len(matches) != 1:
        raise RecoveryBlocked('Recovery job absent or ambiguous')
    job = matches[0]
    if job.get('status') != 'in_progress' or job.get('conclusion') is not None:
        raise RecoveryBlocked('Recovery job is not live')
    return producer, recovery, job
