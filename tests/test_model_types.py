"""Mixed directory classification and native audio/image calls, without real keys."""
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import wave
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_catalog
import providers
import server
import storage

def wav_bytes():
    output=io.BytesIO()
    with wave.open(output,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(16000)
        audio.writeframes(b'\0\0'*16000)
    return output.getvalue()

MODELS=['MiniMax-M3','image-01','speech-02-hd','gpt-image-1','sora-2','tts-1',
        'whisper-1','gpt-4o-realtime-preview','grok-imagine-video','private-unclassified']

class MediaFixture(BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*args):pass
    def send(self,value,mime='application/json'):
        raw=value if isinstance(value,bytes) else json.dumps(value).encode()
        self.send_response(200);self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        self.calls.append(('GET',self.path,None))
        if self.path=='/sample.wav':return self.send(wav_bytes(),'audio/wav')
        self.send({'data':[{'id':name} for name in MODELS]})
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(('POST',self.path,body))
        if self.path=='/v1/audio/speech':
            return self.send(b'not audio' if body['input']=='bad-wav' else wav_bytes(),'audio/wav')
        if self.path=='/v1/image_generation':
            return self.send({'base_resp':{'status_code':0},'data':{'image_urls':['https://example.com/fixture.png']}})
        if self.path=='/v1/t2a_v2':
            if body['text']=='business-error':return self.send({'base_resp':{'status_code':1008,'status_msg':'insufficient fixture balance'}})
            return self.send({'base_resp':{'status_code':0},'data':{'audio':f'http://127.0.0.1:{self.server.server_port}/sample.wav'}})
        raise AssertionError('Unexpected generation path: '+self.path)

class ModelTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='guangyu-types-')
        cls.data_patch=patch.object(storage,'DATA',Path(cls.temp.name));cls.data_patch.start();storage.init()
        cls.upstream=ThreadingHTTPServer(('127.0.0.1',0),MediaFixture)
        cls.app=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.origin=f'http://127.0.0.1:{cls.app.server_port}'
        cls.origin_patch=patch.object(server,'ORIGIN',cls.origin);cls.origin_patch.start()
        cls.port_patch=patch.object(server,'PORT',cls.app.server_port);cls.port_patch.start()
        for service in (cls.upstream,cls.app):threading.Thread(target=service.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        for service in (cls.upstream,cls.app):service.shutdown();service.server_close()
        cls.origin_patch.stop();cls.port_patch.stop();cls.data_patch.stop();cls.temp.cleanup()
    def setUp(self):MediaFixture.calls.clear()
    def api(self,path,body=None,status=200):
        req=urllib.request.Request(self.origin+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Origin':self.origin,'X-CSRF-Token':server.CSRF,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=5) as response:code,raw=response.status,response.read()
        except urllib.error.HTTPError as error:code,raw=error.code,error.read()
        self.assertEqual(code,status,raw.decode());return json.loads(raw)
    def config(self,kind='audio',protocol='openai_speech',model='tts-1',**extra):
        return dict(name='Fixture '+model,kind=kind,protocol=protocol,model=model,platform='minimax' if protocol.startswith('minimax') else 'openai',
            base_url=f'http://127.0.0.1:{self.upstream.server_port}/v1',allow_local=True,**extra)
    def job(self,config=None,prompt='本机语音验收',parameters=None):
        p=self.api('/api/providers/save',config or self.config())
        j=self.api('/api/jobs',{'provider_id':p['id'],'prompt':prompt,'parameters':parameters or {}},status=202)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            j=storage.get('jobs',j['id'])
            if j['status'] not in server.STATUS_ACTIVE:return j
            time.sleep(.02)
        self.fail('Fixture job timed out')
    def test_directory_keeps_output_type_separate_from_adapter(self):
        result=self.api('/api/models/discover',self.config(protocol='openai_chat'))
        rows={m['id']:m for m in result['models']}
        for name,kind in [('MiniMax-M3','chat'),('image-01','image'),('sora-2','video'),('grok-imagine-video','video'),('tts-1','audio'),('whisper-1','audio')]:
            self.assertEqual(rows[name]['model_kinds'],[kind])
        self.assertEqual(rows['private-unclassified']['model_kinds'],[])
        self.assertEqual(rows['whisper-1']['audio_task'],'transcription')
        self.assertIsNone(rows['whisper-1']['protocol'])
        self.assertTrue(all(c[0]=='GET' for c in MediaFixture.calls))
    def test_explicit_output_metadata_and_untrusted_endpoint(self):
        p=self.config(protocol='openai_chat')
        rows,_=model_catalog._normalize([{'id':'private','output_modalities':['audio'],'base_url':'https://evil.invalid'}],'openai',p,'')
        self.assertEqual(rows[0]['model_kinds'],['audio']);self.assertEqual(rows[0]['base_url'],p['base_url'])
    def test_native_minimax_directory_protocols(self):
        p=self.config(protocol='minimax_speech',model='speech-02-hd');p['protocol']='openai_chat'
        rows,_=model_catalog._normalize([{'id':'image-01'},{'id':'speech-02-hd'},{'id':'MiniMax-M3'}],'openai',p,'')
        self.assertEqual([m['protocol'] for m in rows],['minimax_image','minimax_speech','openai_chat'])
    def test_wrong_kind_and_transcription_rejected_before_generation(self):
        for c in [self.config(model='MiniMax-M3'),self.config(model='whisper-1'),self.config(model='gpt-4o-realtime-preview')]:
            self.api('/api/providers/save',c,status=400)
        self.assertEqual(MediaFixture.calls,[])
    def test_openai_speech_binary_playback_and_unknown_tokens(self):
        j=self.job(parameters={'voice':'alloy','speed':1.25});self.assertEqual(j['status'],'succeeded',j.get('error'))
        asset=j['result']['assets'][0];self.assertEqual(asset['type'],'audio');self.assertTrue(asset['local'])
        with urllib.request.urlopen(self.origin+asset['url']) as r:
            self.assertIn('audio',r.headers['Content-Type']);self.assertEqual(r.read(),wav_bytes())
        calls=[c for c in MediaFixture.calls if c[0]=='POST'];self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1],'/v1/audio/speech');self.assertEqual(calls[0][2]['speed'],1.25)
        self.assertIsNone(j['result']['usage']['total_tokens'])
    def test_bad_binary_is_failed_and_not_retried(self):
        j=self.job(prompt='bad-wav');self.assertEqual(j['status'],'failed');self.assertIn('WAV',j['error'])
        self.assertEqual(len([c for c in MediaFixture.calls if c[0]=='POST']),1)
    def test_minimax_speech_native_body_and_audio_result(self):
        j=self.job(self.config(protocol='minimax_speech',model='speech-02-hd'),parameters={'voice':'male-qn-qingse','speed':.8})
        self.assertEqual(j['status'],'succeeded',j.get('error'));self.assertEqual(j['result']['assets'][0]['type'],'audio')
        call=MediaFixture.calls[-1];self.assertEqual(call[1],'/v1/t2a_v2');self.assertEqual(call[2]['voice_setting']['speed'],.8)
        self.assertEqual(call[2]['output_format'],'url')
    def test_minimax_image_native_path(self):
        j=self.job(self.config(kind='image',protocol='minimax_image',model='image-01'),parameters={'aspect_ratio':'16:9','n':2})
        self.assertEqual(j['status'],'succeeded',j.get('error'));self.assertEqual(MediaFixture.calls[-1][1],'/v1/image_generation')
        self.assertEqual(j['result']['assets'][0]['type'],'image')
    def test_minimax_business_failure_is_not_success_or_retried(self):
        j=self.job(self.config(protocol='minimax_speech',model='speech-02-hd'),prompt='business-error')
        self.assertEqual(j['status'],'failed');self.assertIn('insufficient',j['error'])
        self.assertEqual(len([c for c in MediaFixture.calls if c[0]=='POST']),1)
    def test_invalid_audio_speed_rejected_before_paid_call(self):
        p=self.api('/api/providers/save',self.config(protocol='minimax_speech',model='speech-02-hd'))
        for speed in (True,.2,2.1):self.api('/api/jobs',{'provider_id':p['id'],'prompt':'fixture','parameters':{'speed':speed}},status=400)
        self.assertEqual(MediaFixture.calls,[])

if __name__=='__main__':unittest.main()
