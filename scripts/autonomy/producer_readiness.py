"""Secret-free, GET-only producer readiness gate; never arms recovery itself.

Only a positively identified queued job or unfinished prerequisite is waitable.
Missing/ambiguous identities, terminal states and malformed records fail closed.
The immutable claim is digest-checked without extracting or executing its ZIP.
"""
import hashlib
import io
import re
import time
import zipfile
from github_recovery_records import _id, _read
from recovery_receipt import MAX_ARCHIVE
from supervised_recovery_handshake import RecoveryBlocked, trusted_run, PRODUCER_PATH

WAIT_SECONDS = 300
POLL_SECONDS = 5
CLAIM_NAME = 'pilot-one-use-claim'
PUBLISH_STEP = 'Publish one-use claim'
EXECUTE_STEP = 'Execute one approved artifact-only task'
PROOF_FIELDS = {'producer_run_id', 'workflow_sha', 'run_attempt',
                'producer_job_id', 'claim_artifact_id', 'claim_digest'}


class ProducerNotReady(RecoveryBlocked):
    """Trusted prerequisite still pending; never permission to publish a receipt."""


def validate_proof(proof, pid, sha):
    if (not isinstance(proof, dict) or set(proof) != PROOF_FIELDS
            or type(proof['producer_run_id']) is not int or proof['producer_run_id'] != pid
            or proof['workflow_sha'] != sha or type(proof['run_attempt']) is not int
            or proof['run_attempt'] != 1
            or type(proof['producer_job_id']) is not int or proof['producer_job_id'] < 1
            or type(proof['claim_artifact_id']) is not int or proof['claim_artifact_id'] < 1
            or not isinstance(proof['claim_digest'], str)
            or not re.fullmatch('sha256:[a-f0-9]{64}', proof['claim_digest'])):
        raise RecoveryBlocked('Invalid producer readiness binding')


def live_producer(pid, sha, token, opener):
    producer = _read('/actions/runs/' + str(pid), token, opener)
    if not isinstance(producer, dict) or not isinstance(producer.get('repository'), dict):
        raise RecoveryBlocked('Malformed producer run')
    trusted_run(producer, PRODUCER_PATH, expected_id=pid, expected_sha=sha)
    page = _read('/actions/runs/' + str(pid) + '/attempts/1/jobs?per_page=100', token, opener)
    jobs, count = page.get('jobs'), page.get('total_count')
    if (not isinstance(jobs, list) or type(count) is not int
            or not 1 <= count <= 100 or count != len(jobs)
            or any(not isinstance(j, dict) or type(j.get('run_id')) is not int
                   or j['run_id'] != pid or j.get('head_sha') != sha
                   or ('run_attempt' in j and (type(j['run_attempt']) is not int
                                              or j['run_attempt'] != 1)) for j in jobs)):
        raise RecoveryBlocked('Incomplete or mismatched producer jobs')
    matches = [j for j in jobs if j.get('name') == 'coding-task']
    if len(matches) != 1:
        raise RecoveryBlocked('Producer job absent or ambiguous')
    job = matches[0]
    if (type(job.get('id')) is not int or job['id'] < 1
            or job.get('conclusion') is not None):
        raise RecoveryBlocked('Invalid or terminal producer job')
    if job.get('status') in ('queued', 'waiting', 'pending'):
        raise ProducerNotReady('Producer job not started')
    if job.get('status') != 'in_progress' or producer['status'] != 'in_progress':
        raise RecoveryBlocked('Producer is not live')
    steps = job.get('steps')
    if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
        raise RecoveryBlocked('Malformed producer steps')
    publication = [s for s in steps if s.get('name') == PUBLISH_STEP]
    execution = [s for s in steps if s.get('name') == EXECUTE_STEP]
    if len(publication) != 1 or len(execution) != 1:
        raise RecoveryBlocked('Producer steps absent or ambiguous')
    publication, execution = publication[0], execution[0]
    published = publication.get('status') == 'completed' and publication.get('conclusion') == 'success'
    if execution.get('conclusion') is not None:
        raise RecoveryBlocked('Producer execution is terminal')
    if published and execution.get('status') == 'in_progress':
        return producer, job
    if (execution.get('status') in ('queued', 'pending') and
            (published or (publication.get('status') in ('queued', 'pending', 'in_progress')
                           and publication.get('conclusion') is None))):
        raise ProducerNotReady('Producer prerequisites not completed')
    raise RecoveryBlocked('Producer execution is not safely waitable')


def claim_artifact(pid, sha, token, opener):
    page = _read('/actions/runs/' + str(pid) + '/artifacts?per_page=100', token, opener)
    entries, count = page.get('artifacts'), page.get('total_count')
    if (not isinstance(entries, list) or type(count) is not int or not 1 <= count <= 100
            or count != len(entries) or any(not isinstance(a, dict) for a in entries)):
        raise RecoveryBlocked('Incomplete producer artifacts')
    matches = [a for a in entries if a.get('name') == CLAIM_NAME]
    if len(matches) != 1:
        raise RecoveryBlocked('Published producer claim absent or ambiguous')
    artifact = matches[0]
    run = artifact.get('workflow_run')
    if (type(artifact.get('id')) is not int or artifact['id'] < 1
            or artifact.get('expired') is not False or not isinstance(run, dict)
            or type(run.get('id')) is not int or run['id'] != pid
            or run.get('head_sha') != sha or not isinstance(artifact.get('digest'), str)
            or not re.fullmatch('sha256:[a-f0-9]{64}', artifact['digest'])):
        raise RecoveryBlocked('Producer claim identity mismatch')
    return artifact


def read_claim(artifact, archive, pid):
    if (not isinstance(archive, bytes) or not 0 < len(archive) <= MAX_ARCHIVE
            or artifact['digest'] != 'sha256:' + hashlib.sha256(archive).hexdigest()):
        raise RecoveryBlocked('Producer claim archive digest mismatch')
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as archive_file:
            entries = archive_file.infolist()
            if (len(entries) != 1 or entries[0].filename != 'one-use-claim.txt'
                    or entries[0].file_size > 32 or entries[0].flag_bits & 1
                    or entries[0].is_dir()
                    or ((entries[0].external_attr >> 16) & 0o170000) not in (0, 0o100000)):
                raise RecoveryBlocked('Unexpected producer claim archive')
            if archive_file.read(entries[0]) != (str(pid) + '\n').encode('ascii'):
                raise RecoveryBlocked('Producer claim contents mismatch')
    except RecoveryBlocked:
        raise
    except Exception:
        raise RecoveryBlocked('Invalid producer claim archive') from None


def observe_producer(pid, sha, token, opener, download, *, expected=None):
    _id(pid)
    if (not isinstance(sha, str) or not re.fullmatch('[a-f0-9]{40}', sha)
            or not isinstance(token, str) or not token or any(c.isspace() for c in token)):
        raise RecoveryBlocked('Invalid readiness lookup context')
    if expected is not None:
        validate_proof(expected, pid, sha)
    _, job = live_producer(pid, sha, token, opener)
    artifact = claim_artifact(pid, sha, token, opener)
    proof = dict(producer_run_id=pid, workflow_sha=sha, run_attempt=1,
                 producer_job_id=job['id'], claim_artifact_id=artifact['id'],
                 claim_digest=artifact['digest'])
    if expected is not None and proof != expected:
        raise RecoveryBlocked('Immutable producer claim changed')
    read_claim(artifact, download(artifact['id']), pid)
    # Re-fetch after download; a stale observation cannot arm recovery. This is
    # still only present liveness evidence, not a guarantee of future survival.
    _, latest_job = live_producer(pid, sha, token, opener)
    latest_artifact = claim_artifact(pid, sha, token, opener)
    if (latest_job['id'] != job['id'] or latest_artifact['id'] != artifact['id']
            or latest_artifact['digest'] != artifact['digest']):
        raise RecoveryBlocked('Producer identity changed during readiness check')
    return proof


def wait_for_producer(pid, sha, token, opener, download, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + WAIT_SECONDS
    while clock() < deadline:
        proof = None
        try:
            proof = observe_producer(pid, sha, token, opener, download)
        except ProducerNotReady:
            pass
        remaining = deadline - clock()
        if remaining <= 0:
            break
        if proof is not None:
            return proof
        sleep(min(POLL_SECONDS, remaining))
    raise RecoveryBlocked('Producer readiness deadline reached; no recovery armed')
