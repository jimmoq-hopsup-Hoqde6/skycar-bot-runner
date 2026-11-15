import hashlib
import io
import json
import unittest
import zipfile
from test_supervised_recovery_handshake import run
import supervised_recovery_handshake as h
import recovery_receipt as r

class ReceiptTests(unittest.TestCase):
    def fixture(self,name='arming.json',raw=None):
        recovery=run(34,h.RECOVERY_PATH)
        receipt=h.arm(run(12,h.PRODUCER_PATH),recovery,1000,lambda m:True,lambda x:True)
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr(name,json.dumps(receipt) if raw is None else raw)
        archive=b.getvalue()
        artifact=dict(id=56,name='pilot-recovery-armed-12',expired=False,workflow_run={'id':34,'head_sha':'a'*40},digest='sha256:'+hashlib.sha256(archive).hexdigest())
        return artifact,archive,recovery,receipt
    def test_exact_round_trip(self):
        a,b,run,expected=self.fixture();self.assertEqual(r.read_receipt(a,b,run,12),expected)
    def test_identity_digest_and_expiration(self):
        for key,value in [('id',True),('name','other'),('expired',True),('digest','sha256:wrong'),('workflow_run',{'id':99,'head_sha':'a'*40})]:
            a,b,run,_=self.fixture();a[key]=value
            with self.subTest(key=key),self.assertRaises(h.RecoveryBlocked):r.read_receipt(a,b,run,12)
    def test_paths_duplicates_and_large_receipts_rejected(self):
        for name,raw in [('../arming.json','{}'),('arming.json','{"producer_run_id":12,"producer_run_id":12}'),('arming.json','x'*8193)]:
            a,b,run,_=self.fixture(name,raw)
            with self.subTest(name=name,rawlen=len(raw)),self.assertRaises(h.RecoveryBlocked):r.read_receipt(a,b,run,12)
    def test_content_binding_mismatch(self):
        a,b,run,_=self.fixture(raw='{"producer_run_id":99,"recovery_run_id":34,"workflow_sha":"'+('a'*40)+'"}')
        with self.assertRaises(h.RecoveryBlocked):r.read_receipt(a,b,run,12)
    def test_truncated_archive_rejected_without_extracting(self):
        a,b,run,_=self.fixture();b=b[:20];a['digest']='sha256:'+hashlib.sha256(b).hexdigest()
        with self.assertRaises(h.RecoveryBlocked):r.read_receipt(a,b,run,12)

if __name__=='__main__':unittest.main()
