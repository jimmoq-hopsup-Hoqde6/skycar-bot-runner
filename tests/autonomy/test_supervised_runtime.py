import io
from email.message import Message
import unittest
import urllib.error
from unittest.mock import Mock,MagicMock,patch
import supervised_runtime as r
from test_supervised_recovery_handshake import run

class RuntimeTests(unittest.TestCase):
    def redirect(self,url):
        headers=Message();headers['Location']=url
        return urllib.error.HTTPError(r.BASE+'/actions/artifacts/56/zip',302,'Found',headers,None)
    def test_download_strips_credential_and_bounds_body(self):
        auth=Mock();anon=MagicMock();url='https://sample.blob.core.windows.net/artifact?sig=example'
        auth.open.side_effect=self.redirect(url)
        response=Mock(status=200);response.geturl.return_value=url;response.read.return_value=b'zip'
        anon.open.return_value.__enter__.return_value=response
        self.assertEqual(r.download_archive(56,'offline-token',auth,anon),b'zip')
        self.assertEqual(auth.open.call_args.args[0].get_header('Authorization'),'Bearer offline-token')
        self.assertIsNone(anon.open.call_args.args[0].get_header('Authorization'))
        response.read.assert_called_once_with(r.MAX_ARCHIVE+1)
    def test_untrusted_redirect_and_oversize_fail(self):
        for url in ['http://sample.blob.core.windows.net/a','https://example.com/a','https://u:p@sample.blob.core.windows.net/a']:
            auth=Mock();auth.open.side_effect=self.redirect(url);anon=MagicMock()
            with self.assertRaises(r.RecoveryBlocked):r.download_archive(56,'offline-token',auth,anon)
            anon.open.assert_not_called()
        auth=Mock();url='https://sample.blob.core.windows.net/a';auth.open.side_effect=self.redirect(url);anon=MagicMock();response=Mock(status=200);response.geturl.return_value=url;response.read.return_value=b'x'*(r.MAX_ARCHIVE+1);anon.open.return_value.__enter__.return_value=response
        with self.assertRaises(r.RecoveryBlocked):r.download_archive(56,'offline-token',auth,anon)
    def test_cleanup_accepts_failed_producer_but_arming_rejects_it(self):
        producer=run(12,r.PRODUCER_PATH);producer.update(status='completed',conclusion='failure');recovery=run(34,r.RECOVERY_PATH)
        with patch.object(r,'_read',side_effect=[producer,recovery]):
            r.records(12,34,'a'*40,'offline',Mock(),allow_terminal_producer=True)
        with patch.object(r,'_read',side_effect=[producer,recovery]),self.assertRaises(r.RecoveryBlocked):
            r.records(12,34,'a'*40,'offline',Mock())
    def test_capture_redirect_never_follows(self):
        self.assertIsNone(r.CaptureRedirect().redirect_request(None,None,302,'Found',{},'https://example.com'))
    def test_unique_recovery_discovery(self):
        recovery=run(34,r.RECOVERY_PATH);artifact={'id':56}
        with patch.object(r,'_read',return_value={'total_count':1,'workflow_runs':[recovery]}),patch.object(r,'artifact_for',return_value=artifact):
            self.assertEqual(r.discover_recovery(12,'a'*40,'offline',Mock()),(34,artifact))
    def test_discovery_unknown_and_ambiguity_fail_closed(self):
        for entries in [[],[run(34,r.RECOVERY_PATH),run(35,r.RECOVERY_PATH)]]:
            with patch.object(r,'_read',return_value={'total_count':len(entries),'workflow_runs':entries}),patch.object(r,'artifact_for',return_value={'id':56}),self.assertRaises(r.RecoveryBlocked):r.discover_recovery(12,'a'*40,'offline',Mock())
    def test_artifact_listing_incomplete_and_duplicate_rejected(self):
        for page in [{'total_count':2,'artifacts':[]},{'total_count':2,'artifacts':[{'name':'x'},{'name':'x'}]}]:
            with patch.object(r,'_read',return_value=page),self.assertRaises(r.RecoveryBlocked):r.artifact_for(12,'x','offline',Mock())

if __name__=='__main__':unittest.main()
