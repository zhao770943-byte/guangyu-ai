"""GET-only archiving, durable receipts and local playback without real providers."""
import base64
import io
import json
import socket
import ssl
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import wave
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import media_store, server, storage

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGMwCqgAAAGyAPsem+p5AAAAAElFTkSuQmCC')

class CDN(BaseHTTPRequestHandler):
    calls=[]
    repaired=False
    def log_message(self,*args):pass
    def reply(self,raw,code=200,headers=None):
        self.send_response(code)
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        self.calls.append(('POST',self.path,dict(self.headers)))
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        paths=['/ok','/missing'] if body['prompt']=='batch' else [body['prompt']]
        self.reply(json.dumps({'data':[{'url':f'http://127.0.0.1:{self.server.server_port}{p}'} for p in paths]}).encode())
    def do_GET(self):
        self.calls.append(('GET',self.path,dict(self.headers)))
        if self.path=='/missing' and not self.repaired:return self.reply(b'missing',404)
        if self.path=='/redirect':return self.reply(b'',302,{'Location':'/ok'})
        if self.path=='/private':return self.reply(b'',302,{'Location':'http://169.254.169.254/credentials'})
        if self.path=='/html':return self.reply(b'<html>not an image</html>')
        if self.path=='/truncated':
            self.send_response(200);self.send_header('Content-Length',str(len(PNG)+20));self.end_headers();self.wfile.write(PNG);return
        self.reply(PNG)

class MediaStoreTests(unittest.TestCase):
    def test_known_cdn_proxy_keeps_get_only_and_validates_content(self):
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value=response;response.status=200;response.read.return_value=PNG
        opener=MagicMock();opener.open.return_value=response
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('172.67.138.32',443))]
        with patch.object(socket,'getaddrinfo',return_value=addresses),patch.object(urllib.request,'getproxies',return_value={'https':'http://127.0.0.1:7890'}),patch.object(urllib.request,'build_opener',return_value=opener):
            result=media_store.download({'type':'image','url':'https://media.lensapi.cn/fixture.png'},{'id':'proxy-fixture'},0)
            self.assertTrue(result['local'])
            request=opener.open.call_args.args[0]
            self.assertEqual(request.get_method(),'GET')
            self.assertNotIn('Authorization',request.headers);self.assertNotIn('Cookie',request.headers)
            response.read.return_value=b'<html>not an image</html>'
            with self.assertRaises(media_store.SaveError):media_store.download({'type':'image','url':'https://media.lensapi.cn/fixture.png'},{'id':'proxy-fixture'},0)
            opener.open.side_effect=urllib.error.URLError(ssl.SSLCertVerificationError('invalid'))
            with self.assertRaises(media_store.SaveError):media_store.download({'type':'image','url':'https://media.lensapi.cn/fixture.png'},{'id':'proxy-fixture'},0)
        private=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch.object(socket,'getaddrinfo',return_value=private),patch.object(urllib.request,'getproxies',return_value={'https':'http://127.0.0.1:7890'}),patch.object(urllib.request,'build_opener') as build:
            with self.assertRaises(media_store.SaveError):media_store.download({'type':'image','url':'https://media.lensapi.cn/x'},{'id':'proxy-fixture'},0)
            build.assert_not_called()

    def test_tls_timeout_fallback_keeps_hostname_and_rejects_bad_certificate(self):
        addresses=[(socket.AF_INET6,socket.SOCK_STREAM,6,'',('2606:4700:3037::ac43:8a20',443,0,0)),
                   (socket.AF_INET,socket.SOCK_STREAM,6,'',('172.67.138.32',443))]
        with patch.object(socket,'getaddrinfo',return_value=addresses),patch.object(media_store.http.client.HTTPSConnection,'connect',side_effect=[TimeoutError('TLS timeout'),None]) as connect:
            conn,_=media_store.connection('https://cdn.example/image.png',{})
            conn.connect()
            self.assertEqual(connect.call_count,2)
            self.assertEqual(conn.host,'cdn.example')
        with patch.object(socket,'getaddrinfo',return_value=addresses),patch.object(media_store.http.client.HTTPSConnection,'connect',side_effect=ssl.SSLCertVerificationError('invalid certificate')) as connect:
            conn,_=media_store.connection('https://cdn.example/image.png',{})
            with self.assertRaises(ssl.SSLCertVerificationError):conn.connect()
            self.assertEqual(connect.call_count,1)

    def test_unreachable_ipv6_falls_back_only_to_validated_ipv4(self):
        addresses=[(socket.AF_INET6,socket.SOCK_STREAM,6,'',('2606:4700:3037::ac43:8a20',443,0,0)),
                   (socket.AF_INET,socket.SOCK_STREAM,6,'',('172.67.138.32',443))]
        marker=object()
        with patch.object(socket,'getaddrinfo',return_value=addresses), patch.object(socket,'create_connection',side_effect=[OSError('unreachable'),marker]) as connect:
            conn,parsed=media_store.connection('https://cdn.example/image.png',{})
            self.assertIs(conn._create_connection(('cdn.example',443),15),marker)
            self.assertEqual([call.args[0] for call in connect.call_args_list],[('2606:4700:3037::ac43:8a20',443),('172.67.138.32',443)])
            self.assertEqual(conn.host,'cdn.example')
        private=addresses+[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch.object(socket,'getaddrinfo',return_value=private),patch.object(socket,'create_connection') as connect:
            with self.assertRaises(media_store.SaveError):media_store.connection('https://cdn.example/image.png',{})
            connect.assert_not_called()

    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.data_patch=patch.object(storage,'DATA',Path(cls.temp.name));cls.data_patch.start();storage.init()
        cls.cdn=ThreadingHTTPServer(('127.0.0.1',0),CDN);cls.app=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.origin=f'http://127.0.0.1:{cls.app.server_port}'
        cls.origin_patch=patch.object(server,'ORIGIN',cls.origin);cls.origin_patch.start()
        cls.port_patch=patch.object(server,'PORT',cls.app.server_port);cls.port_patch.start()
        for app in (cls.cdn,cls.app):threading.Thread(target=app.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        for app in (cls.cdn,cls.app):app.shutdown();app.server_close()
        cls.port_patch.stop();cls.origin_patch.stop();cls.data_patch.stop();cls.temp.cleanup()
    def setUp(self):
        CDN.calls.clear();CDN.repaired=False
    def api(self,path,body=None):
        req=urllib.request.Request(self.origin+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','Origin':self.origin,'X-CSRF-Token':server.CSRF})
        with urllib.request.urlopen(req,timeout=5) as r:return json.load(r)
    def wait(self,identity):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            j=storage.get('jobs',identity)
            with server.ACTIVE_LOCK:running=identity in server.ACTIVE
            if not running and j.get('archive_status')!='pending':return j
            time.sleep(.01)
        self.fail('Archive did not finish')
    def generate(self,path):
        p=self.api('/api/providers/save',{'name':'fixture','kind':'image','protocol':'openai_image','model':'fixture','base_url':f'http://127.0.0.1:{self.cdn.server_port}/v1','allow_local':True,'api_key':'fixture-key'})
        return self.wait(self.api('/api/jobs',{'provider_id':p['id'],'prompt':path})['id'])
    def test_remote_image_survives_restart_and_supports_range_download(self):
        j=self.generate('/redirect');a=j['result']['assets'][0]
        self.assertEqual(j['archive_status'],'saved');self.assertTrue(a['local'])
        self.assertEqual((storage.DATA/a['url'].lstrip('/')).read_bytes(),PNG)
        gets=[c for c in CDN.calls if c[0]=='GET'];self.assertEqual(len(gets),2)
        self.assertTrue(all('Authorization' not in c[2] and 'Cookie' not in c[2] for c in gets))
        before=len(CDN.calls);storage.init();server.recover();self.assertEqual(len(CDN.calls),before)
        req=urllib.request.Request(self.origin+a['url']+'?download=1',headers={'Range':'bytes=0-7'})
        with urllib.request.urlopen(req) as r:
            self.assertEqual(r.status,206);self.assertEqual(r.read(),PNG[:8]);self.assertIn('attachment',r.headers['Content-Disposition'])
        self.assertEqual(self.api('/api/jobs/'+j['id'])['result']['assets'][0]['url'],a['url'])
    def test_404_keeps_success_receipt_and_retry_never_generates_again(self):
        j=self.generate('/missing');self.assertEqual(j['status'],'succeeded');self.assertEqual(j['archive_status'],'failed')
        self.assertIn('HTTP 404',j['result']['assets'][0]['save_error'])
        self.assertFalse(list((storage.DATA/'media').glob(j['id']+'*')))
        CDN.repaired=True;self.api('/api/jobs/archive',{'id':j['id']});j=self.wait(j['id'])
        self.assertEqual(j['archive_status'],'saved');self.assertEqual(sum(c[0]=='POST' for c in CDN.calls),1)
    def test_batch_partial_preserves_saved_files_and_retries_only_missing(self):
        j=self.generate('batch');self.assertEqual(j['archive_status'],'partial');first=j['result']['assets'][0]['url']
        CDN.repaired=True;self.api('/api/jobs/archive',{'id':j['id']});j=self.wait(j['id'])
        self.assertEqual(j['archive_status'],'saved');self.assertEqual(j['result']['assets'][0]['url'],first)
        self.assertEqual(sum(c[1]=='/ok' for c in CDN.calls),1)
    def test_html_and_truncated_media_leave_no_partial_files(self):
        for path in ('/html','/truncated'):
            j=self.generate(path);self.assertEqual(j['status'],'succeeded');self.assertEqual(j['archive_status'],'failed')
            self.assertFalse(list((storage.DATA/'media').glob(j['id']+'*')))
    def test_size_limit_does_not_discard_generation(self):
        with patch.object(media_store,'MAX_BYTES',8):j=self.generate('/ok')
        self.assertEqual(j['archive_status'],'failed');self.assertEqual(j['status'],'succeeded')
    def test_redirect_to_private_service_is_blocked(self):
        j=self.generate('/private');self.assertEqual(j['archive_status'],'failed');self.assertIn('内网',j['result']['assets'][0]['save_error'])
        self.assertEqual(sum(c[0]=='GET' for c in CDN.calls),1)
    def test_untrusted_loopback_and_dns_private_addresses_are_blocked(self):
        for url,p in [('http://127.0.0.1/secret',{}),('http://127.0.0.1:1234/secret',{'allow_local':True,'base_url':'http://127.0.0.1:1235'})]:
            with self.assertRaises(media_store.SaveError):media_store.connection(url,p)
        with patch.object(socket,'getaddrinfo',return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',443))]):
            with self.assertRaises(media_store.SaveError):media_store.connection('https://cdn.example/asset',{})
    def test_restart_migrates_old_remote_receipt_without_paid_post(self):
        identity=storage.uid();storage.put('jobs',{'id':identity,'created_at':storage.now(),'status':'succeeded','kind':'image','provider_snapshot':{'allow_local':True,'base_url':f'http://127.0.0.1:{self.cdn.server_port}'},'result':{'assets':[{'type':'image','url':f'http://127.0.0.1:{self.cdn.server_port}/ok','local':False}]}})
        server.recover();self.assertEqual(self.wait(identity)['archive_status'],'saved');self.assertTrue(all(c[0]=='GET' for c in CDN.calls))
    def test_media_format_detection(self):
        for kind,head,ext in [('image',PNG,'png'),('video',b'\0\0\0\x20ftypisom','mp4'),('video',b'\x1aE\xdf\xa3','webm'),('audio',b'RIFFxxxxWAVE','wav'),('audio',b'ID3xxxx','mp3'),('audio',b'OggS','ogg'),('audio',b'fLaC','flac'),('audio',b'\0\0\0\x20ftypM4A ','m4a')]:self.assertEqual(media_store.extension(head,kind),ext)

if __name__=='__main__':unittest.main()
