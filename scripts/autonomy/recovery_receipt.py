"""Validate a tiny recovery receipt archive against trusted GitHub metadata.

No extraction, writes, credentials or network. Adapter must obtain artifact
metadata from authenticated GitHub API for the exact independently verified run.
"""
import hashlib
import io
import json
import zipfile
from supervised_recovery_handshake import RecoveryBlocked, trusted_run, RECOVERY_PATH
MAX_ARCHIVE = 65536
MAX_RECEIPT = 8192


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryBlocked('Duplicate receipt field')
        result[key] = value
    return result


def read_receipt(artifact, archive, recovery_run, producer_id):
    rid, sha = trusted_run(recovery_run, RECOVERY_PATH)
    if (type(producer_id) is not int or producer_id < 1 or not isinstance(artifact, dict)
            or artifact.get('name') != 'pilot-recovery-armed-' + str(producer_id)
            or artifact.get('expired') is not False
            or artifact.get('workflow_run', {}).get('id') != rid
            or artifact.get('workflow_run', {}).get('head_sha') != sha
            or type(artifact.get('id')) is not int or artifact['id'] < 1):
        raise RecoveryBlocked('Artifact identity is outside exact recovery run')
    if not isinstance(archive, bytes) or not 0 < len(archive) <= MAX_ARCHIVE:
        raise RecoveryBlocked('Invalid receipt archive size')
    if artifact.get('digest') != 'sha256:' + hashlib.sha256(archive).hexdigest():
        raise RecoveryBlocked('Receipt archive digest mismatch')
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            entries = z.infolist()
            if (len(entries) != 1 or entries[0].filename != 'arming.json'
                    or entries[0].file_size > MAX_RECEIPT or entries[0].flag_bits & 1
                    or entries[0].is_dir()):
                raise RecoveryBlocked('Unexpected receipt archive entry')
            raw = z.read(entries[0])
            if len(raw) > MAX_RECEIPT:
                raise RecoveryBlocked('Oversize receipt')
            receipt = json.loads(raw, object_pairs_hook=unique_object)
    except RecoveryBlocked:
        raise
    except Exception:
        raise RecoveryBlocked('Invalid receipt archive') from None
    if (not isinstance(receipt, dict) or receipt.get('producer_run_id') != producer_id
            or receipt.get('recovery_run_id') != rid or receipt.get('workflow_sha') != sha):
        raise RecoveryBlocked('Receipt content identity mismatch')
    return receipt
