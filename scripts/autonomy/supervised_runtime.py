"""Bounded workflow adapter. No dispatch/approval/settings changes.

All credentials are read only in the workflow step that needs them. Recovery
receipt staging is not durable arming: producer requires uploaded artifact plus
independently observed live recovery-loop step before creation.
"""
import json
from safe_pilot_diagnostics import phase, DiagnosticBlocked
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from github_recovery_records import _read, NoRedirect, BASE, fetch_records
from supervised_recovery_handshake import (RecoveryBlocked, trusted_run, PRODUCER_PATH, RECOVERY_PATH,
    arm, cleanup_window, MAX_RECEIPT_AGE, PRODUCER_SECONDS)
from recovery_receipt import MAX_ARCHIVE
from verify_supervised_gate import verify
from producer_readiness import observe_producer, wait_for_producer, validate_proof


def records(pid, rid, sha, token, opener, *, allow_terminal_producer=False):
    producer = _read('/actions/runs/'+str(pid),token,opener)
    recovery = _read('/actions/runs/'+str(rid),token,opener)
    validation_record=producer
    if allow_terminal_producer and producer.get('status')=='completed':
        validation_record=dict(producer,status='in_progress',conclusion=None)
    trusted_run(validation_record,PRODUCER_PATH,expected_id=pid,expected_sha=sha)
    trusted_run(recovery,RECOVERY_PATH,expected_id=rid,expected_sha=sha)
    return producer,recovery


def artifact_for(run_id, name, token, opener):
    page=_read('/actions/runs/'+str(run_id)+'/artifacts?per_page=100',token,opener)
    entries=page.get('artifacts')
    if not isinstance(entries,list) or type(page.get('total_count')) is not int or page['total_count']!=len(entries) or len(entries)>100:
        raise RecoveryBlocked('Incomplete artifacts')
    matches=[a for a in entries if isinstance(a,dict) and a.get('name')==name]
    if len(matches)>1:raise RecoveryBlocked('Ambiguous artifacts')
    return matches[0] if matches else None


class CaptureRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_archive(artifact_id, token, opener, anonymous_opener):
    if type(artifact_id) is not int or artifact_id<1:raise RecoveryBlocked('Invalid artifact ID')
    request=urllib.request.Request(BASE+'/actions/artifacts/'+str(artifact_id)+'/zip',headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
    try:
        response=opener.open(request,timeout=15)
        response.close()
        raise RecoveryBlocked('Expected explicit artifact redirect')
    except urllib.error.HTTPError as exc:
        if exc.code!=302:raise RecoveryBlocked('Artifact download unavailable') from None
        location=exc.headers.get('Location','')
    parsed=urllib.parse.urlsplit(location)
    # URL is supplied by authenticated GitHub, but never forward its credential.
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not parsed.hostname or not parsed.hostname.endswith('.blob.core.windows.net'):
        raise RecoveryBlocked('Unrecognized artifact storage destination')
    try:
        with anonymous_opener.open(urllib.request.Request(location),timeout=15) as response:
            if response.status!=200 or response.geturl()!=location:raise RecoveryBlocked('Unexpected storage response')
            raw=response.read(MAX_ARCHIVE+1)
            if not 0<len(raw)<=MAX_ARCHIVE:raise RecoveryBlocked('Artifact too large')
            return raw
    except Exception:
        raise RecoveryBlocked('Artifact download failed') from None


class RecoveryNotReady(RecoveryBlocked):
    """Only a complete trusted listing with no arming artifact is waitable."""

def discover_recovery(pid, sha, token, opener):
    page=_read('/actions/workflows/supervised-recovery.yml/runs?event=workflow_dispatch&status=in_progress&head_sha='+sha+'&per_page=10',token,opener)
    runs=page.get('workflow_runs')
    if not isinstance(runs,list) or type(page.get('total_count')) is not int or page['total_count']!=len(runs) or len(runs)>10:
        raise RecoveryBlocked('Incomplete recovery run listing')
    matches=[]
    for run in runs:
        rid,_=trusted_run(run,RECOVERY_PATH,expected_sha=sha)
        artifact=artifact_for(rid,'pilot-recovery-armed-'+str(pid),token,opener)
        if artifact is not None:matches.append((rid,artifact))
    if not matches:raise RecoveryNotReady('Arming artifact not yet published')
    if len(matches)!=1:raise RecoveryBlocked('No unique armed recovery')
    return matches[0]


WAIT_SECONDS = 300
WAIT_POLL_SECONDS = 5


def wait_for_recovery(pid, sha, token, opener, *, clock=time.monotonic, sleep=time.sleep):
    """Wait only for absence or a positively identified not-yet-started loop.

    No provider calls. Deadline is checked before/after every probe; an in-flight
    bounded GitHub read can finish after it, but cannot authorize a late return.
    All identity, authentication, malformed and ambiguous failures propagate.
    """
    deadline = clock() + WAIT_SECONDS
    while clock() < deadline:
        ready = False
        try:
            rid, artifact = discover_recovery(pid, sha, token, opener)
        except RecoveryNotReady:
            pass
        else:
            _, _, job = fetch_records(pid, rid, sha, token, opener=opener)
            steps = job.get('steps')
            if not isinstance(steps, list) or any(not isinstance(s, dict) for s in steps):
                raise RecoveryBlocked('Invalid recovery step records')
            published = [s for s in steps if s.get('name') == 'Publish arming receipt']
            loops = [s for s in steps if s.get('name') == 'Bounded recovery loop']
            if len(published) != 1 or len(loops) != 1 or loops[0].get('conclusion') is not None:
                raise RecoveryBlocked('Recovery is not safely waitable')
            publication = published[0]
            loop_status = loops[0].get('status')
            if publication.get('status') == 'completed' and publication.get('conclusion') == 'success':
                if loop_status == 'in_progress':
                    ready = True
                elif loop_status not in ('queued', 'pending'):
                    raise RecoveryBlocked('Recovery is not safely waitable')
            elif (publication.get('status') == 'in_progress'
                    and publication.get('conclusion') is None
                    and loop_status in ('queued', 'pending')):
                pass  # Artifact may be visible before its upload step completes.
            else:
                raise RecoveryBlocked('Recovery is not safely waitable')
        remaining = deadline - clock()
        if remaining <= 0:
            break
        if ready:
            return rid, artifact
        sleep(min(WAIT_POLL_SECONDS, remaining))
    raise RecoveryBlocked('Recovery readiness deadline reached')


def write(path, value):
    Path(path).write_text(json.dumps(value,sort_keys=True))
    return True


def stage_recovery(pid, rid, sha, token, opener, expected, output, client_factory):
    """Revalidate after human approval, and again after the provider read.

    The unprotected job's exact immutable claim binding is mandatory. There is
    no readiness wait here: delayed approval or changed state yields no receipt.
    """
    validate_proof(expected, pid, sha)
    def readiness():
        return observe_producer(pid, sha, token, opener,
            lambda aid: download_archive(aid, token,
                urllib.request.build_opener(CaptureRedirect()),
                urllib.request.build_opener(NoRedirect())), expected=expected)
    producer, recovery = records(pid, rid, sha, token, opener)
    readiness()  # Before constructing a provider client or making its read probe.
    with client_factory(api_key=os.environ['OPENAI_API_KEY'], base_url='https://api.openai.com/v1',
                        max_retries=0, timeout=20) as client:
        def probe(metadata):
            page = client.beta.agents.sessions.list(metadata=metadata, limit=2)
            return len(page.data) == 0 and not page.has_next_page()
        def persist(receipt):
            readiness()  # No receipt if producer stopped while probe was in flight.
            return write(output, receipt)
        return arm(producer, recovery, int(time.time()), probe, persist)


def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['wait-producer','stage-recovery','recover','execute']);parser.add_argument('--producer-id',type=int);parser.add_argument('--root',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    token=os.environ.get('GITHUB_TOKEN','');sha=os.environ.get('GITHUB_SHA','')
    rid=int(os.environ['GITHUB_RUN_ID'])
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1' or os.environ.get('GITHUB_REF')!='refs/heads/main' or os.environ.get('GITHUB_REPOSITORY')!='jimmoq-hopsup-Hoqde6/skycar-bot-runner':raise RecoveryBlocked('Untrusted workflow context')
    opener=urllib.request.build_opener(NoRedirect())
    if args.mode=='wait-producer':
        proof=wait_for_producer(args.producer_id,sha,token,opener,
            lambda aid:download_archive(aid,token,urllib.request.build_opener(CaptureRedirect()),urllib.request.build_opener(NoRedirect())))
        write(args.output,proof)
    elif args.mode=='stage-recovery':
        from openai import OpenAI
        expected=dict(producer_run_id=args.producer_id,workflow_sha=sha,run_attempt=1,
            producer_job_id=int(os.environ['READY_PRODUCER_JOB_ID']),
            claim_artifact_id=int(os.environ['READY_CLAIM_ARTIFACT_ID']),
            claim_digest=os.environ['READY_CLAIM_DIGEST'])
        stage_recovery(args.producer_id,rid,sha,token,opener,expected,args.output,OpenAI)
    elif args.mode=='recover':
        from openai import OpenAI
        receipt=json.loads(args.output.read_text())
        records(receipt['producer_run_id'],rid,sha,token,opener,allow_terminal_producer=True)
        # Start is observed as a running step by the producer, before this wait.
        earliest=receipt['armed_at']+MAX_RECEIPT_AGE+PRODUCER_SECONDS+30
        remaining=earliest-time.time()
        if remaining>0:time.sleep(min(remaining,MAX_RECEIPT_AGE+PRODUCER_SECONDS+30))
        with OpenAI(api_key=os.environ['OPENAI_API_KEY'],base_url='https://api.openai.com/v1',max_retries=0,timeout=20) as client:
            result=cleanup_window(client,receipt['metadata'],deadline=receipt['stop_at'],clock=time.time,sleep=time.sleep,persist=lambda result:write(args.output.with_name('cleanup.json'),result))
        write(args.output.with_name('cleanup.json'),result)
        if result.get('status')!='deletion_confirmed':raise RecoveryBlocked('Cleanup unresolved; human reconciliation required')
    else:
        from bounded_coding_pilot import build_request,bind_attempt,fingerprint,source_snapshot,execute
        from reconcile_pilot_attempt import COMMIT
        with phase('DISCOVERY'):
            recovery_id,artifact=wait_for_recovery(rid,sha,token,opener)
        with phase('ARCHIVE_DOWNLOAD'):
            archive=download_archive(artifact['id'],token,urllib.request.build_opener(CaptureRedirect()),urllib.request.build_opener(NoRedirect()))
        claim_id=int(os.environ['CLAIM_ARTIFACT_ID'])
        def claim(metadata):
            item=artifact_for(rid,'pilot-one-use-claim',token,opener)
            return (item is not None and item.get('id')==claim_id and item.get('expired') is False and item.get('workflow_run',{}).get('id')==rid and item.get('workflow_run',{}).get('head_sha')==sha)
        with phase('FINGERPRINT_VALIDATION'):
            request=bind_attempt(build_request(source_snapshot(args.root,COMMIT),COMMIT,100),rid,1,sha)
            if fingerprint(request)!=os.environ['REVIEWED_FINGERPRINT']:raise DiagnosticBlocked('FINGERPRINT_MISMATCH')
        verify(rid,recovery_id,sha,token,archive,lambda:int(time.time()),claim=claim,opener=opener)
        from openai import OpenAI
        with OpenAI(api_key=os.environ['OPENAI_API_KEY'],base_url='https://api.openai.com/v1',max_retries=0,timeout=60) as client:
            with phase('EXECUTION_ENTRY'):
                execute(client,request,args.output,fingerprint(request))

if __name__=='__main__':
    try:main()
    except Exception:
        raise SystemExit('Supervised workflow blocked; inspect safe evidence and reconcile manually') from None
