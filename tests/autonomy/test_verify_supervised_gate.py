import unittest
from unittest.mock import Mock, patch
import test_recovery_receipt as receipt_tests
import test_supervised_recovery_handshake as handshake_tests
import verify_supervised_gate as g

class GateTests(unittest.TestCase):
    def fixture(self):
        artifact,archive,recovery,receipt=receipt_tests.ReceiptTests().fixture()
        _,producer,_,job=handshake_tests.HandshakeTests().setup_records()
        return artifact,archive,(producer,recovery,job)
    def test_integrated_records_archive_and_claim(self):
        artifact,archive,records=self.fixture();claim=Mock(return_value=True)
        with patch.object(g,'fetch_records',return_value=records) as fetch,patch.object(g,'_read',return_value={'total_count':1,'artifacts':[artifact]}):
            out=g.verify(12,34,'a'*40,'offline-token',archive,lambda:1020,claim=claim,opener=Mock())
        self.assertTrue(out['authorized_for_one_creation']);self.assertEqual(fetch.call_count,2);claim.assert_called_once()
    def test_wrong_digest_and_duplicate_block_before_claim(self):
        for duplicate in (True,False):
            artifact,archive,records=self.fixture();claim=Mock(return_value=True)
            if not duplicate:artifact['digest']='wrong'
            entries=[artifact,artifact] if duplicate else [artifact]
            with patch.object(g,'fetch_records',return_value=records),patch.object(g,'_read',return_value={'total_count':len(entries),'artifacts':entries}),self.assertRaises(g.RecoveryBlocked):
                g.verify(12,34,'a'*40,'offline-token',archive,lambda:1020,claim=claim,opener=Mock())
            claim.assert_not_called()
    def test_recovery_dies_during_validation(self):
        artifact,archive,records=self.fixture();claim=Mock(return_value=True)
        with patch.object(g,'fetch_records',side_effect=[records,g.RecoveryBlocked('no longer running')]),patch.object(g,'_read',return_value={'total_count':1,'artifacts':[artifact]}),self.assertRaises(g.RecoveryBlocked):
            g.verify(12,34,'a'*40,'offline-token',archive,lambda:1020,claim=claim,opener=Mock())
        claim.assert_not_called()

if __name__=='__main__':unittest.main()
