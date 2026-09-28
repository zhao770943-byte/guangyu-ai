"""Documented WeiJin JSON and media authorization fixtures, no paid generation."""
import json,io,base64
from PIL import Image
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import providers,storage,model_catalog,media_store,weijin_video,video_controls,uploads

MODEL={'id':'seedance2.5-9图','durations_seconds':[30],'ratios':['16:9','9:16'],'max_images':9,'resolution':'720p'}
MP4=b'\x00\x00\x00\x18ftypisom'+b'fixture-video-content'*8

class Fixture(BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*args):pass
    def reply(self,body,code=200,headers=None):
        raw=json.dumps(body).encode() if isinstance(body,dict) else body
        self.send_response(code)
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        self.calls.append(('GET',self.path,self.headers.get('Authorization'),None))
        if self.path=='/v1/models':return self.reply({'data':[MODEL]})
        if self.path.endswith('/content'):return self.reply(b'',307,{'Location':f'http://127.0.0.1:{self.server.server_port}/cdn.mp4'})
        if self.path=='/cdn.mp4':return self.reply(MP4)
        return self.reply({'id':'task_fixture','status':'completed'})
    def do_POST(self):
        raw=self.rfile.read(int(self.headers['Content-Length']))
        body=json.loads(raw) if 'application/json' in self.headers['Content-Type'] else None
        self.calls.append(('POST',self.path,self.headers.get('Authorization'),body))
        if self.path=='/api/upload/video':return self.reply({'data':{'url':'https://example.com/reference.png'}})
        self.reply({'id':'task_fixture','status':'queued'})

class WeijinTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.data=patch.object(storage,'DATA',Path(self.temp.name));self.data.start();self.addCleanup(self.data.stop);storage.init()
        self.app=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=self.app.serve_forever,daemon=True).start()
        self.addCleanup(self.app.server_close);self.addCleanup(self.app.shutdown);Fixture.calls=[]
        self.p={'name':'fixture','kind':'video','protocol':'weijin_video','model':MODEL['id'],
                'base_url':f'http://127.0.0.1:{self.app.server_port}/v1','allow_local':True,
                'secret':storage.crypt('fixture-key'),'extra':{},'video_model_metadata':MODEL}
        self.job={'id':storage.uid(),'created_at':storage.now(),'kind':'video','provider_snapshot':self.p,
                  'prompt':'A mountain landscape','size':'auto','seconds':30,'parameters':{'aspect_ratio':'16:9'},'input_assets':{},'status':'queued'}
        storage.put('jobs',self.job)

    def test_json_poll_archive_redirect_drops_credentials(self):
        with patch.object(providers.time,'sleep'):
            result=providers.execute(self.p,self.job)
        job=storage.update_job(self.job['id'],result=result,status='succeeded',archive_status='pending')
        media_store.archive(job['id'])
        final=storage.get('jobs',job['id'])
        self.assertEqual(final['archive_status'],'saved')
        self.assertEqual((storage.DATA/final['result']['assets'][0]['url'].lstrip('/')).read_bytes(),MP4)
        submits=[c for c in Fixture.calls if c[0]=='POST']
        self.assertEqual(len(submits),1);self.assertEqual(submits[0][1],'/v1/videos')
        self.assertEqual(submits[0][3],{'model':MODEL['id'],'prompt':self.job['prompt'],'seconds':30,'aspect_ratio':'16:9'})
        self.assertEqual(next(c[2] for c in Fixture.calls if c[1].endswith('/content')),'Bearer fixture-key')
        self.assertIsNone(next(c[2] for c in Fixture.calls if c[1]=='/cdn.mp4'))

    def test_invalid_duration_is_rejected_before_generation(self):
        self.job['seconds']=4
        with self.assertRaisesRegex(ValueError,'30'):providers.build(self.p,self.job)
        self.assertEqual(Fixture.calls,[])

    def test_live_capability_mismatch_stops_before_post(self):
        with patch.object(weijin_video,'metadata',return_value={'durations_seconds':[15],'ratios':['16:9'],'max_images':0,'resolution':'720p'}):
            with self.assertRaises(ValueError):weijin_video.execute(self.p,self.job)
        self.assertFalse(any(c[0]=='POST' for c in Fixture.calls))

    def test_discovery_is_host_scoped_and_preserves_constraints(self):
        p={**self.p,'base_url':'https://www.weijinapi.top/v1','platform':'custom','protocol':'openai_chat'}
        models,_=model_catalog._normalize([MODEL],'openai',p,'')
        self.assertEqual(models[0]['protocol'],'weijin_video');self.assertEqual(models[0]['video_model_metadata']['durations_seconds'],[30])
        models,_=model_catalog._normalize([MODEL],'openai',{**p,'base_url':'https://example.com/v1'},'')
        self.assertIsNone(models[0]['protocol'])
        options=video_controls.options(self.p)
        self.assertEqual(options['durations'],[30]);self.assertEqual(options['fixed_resolution'],'720p')
        self.assertEqual([r['value'] for r in options['ratios'] if r['enabled']],['9:16','16:9'])

    def test_upload_then_submit_urls_only(self):
        raw=io.BytesIO();Image.new('RGB',(32,32)).save(raw,format='PNG')
        image=uploads.save({'name':'fixture.png','data_base64':base64.b64encode(raw.getvalue()).decode()})
        self.job['input_assets']={'references':[image['id']]}
        with patch.object(providers.time,'sleep'):
            providers.execute(self.p,self.job)
        posts=[c for c in Fixture.calls if c[0]=='POST']
        self.assertEqual([c[1] for c in posts],['/api/upload/video','/v1/videos'])
        self.assertEqual(posts[-1][3]['images'],['https://example.com/reference.png'])

    def test_missing_mapping_has_actionable_field_error(self):
        p={**self.p,'protocol':'custom','custom':{},'base_url':'https://example.com/v1'}
        with self.assertRaisesRegex(ValueError,'尚未配置提交路径'):providers.validate(p)
        p['custom']['submit_path']='https://example.com/generate'
        with self.assertRaisesRegex(ValueError,'提交路径：'):providers.validate(p)


if __name__=='__main__':unittest.main()
