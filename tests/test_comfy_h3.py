"""Local ComfyUI contract fixtures; no GPU or cloud generation."""
import base64,io,json,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import comfy_h3,storage,uploads,providers,model_catalog,capabilities,video_controls,work_library
import av

ID='12345678-1234-1234-1234-123456789abc'
def sample_video():
    out=io.BytesIO()
    with av.open(out,'w',format='mp4') as container:
        stream=container.add_stream('libx264',rate=24);stream.width=64;stream.height=64;stream.pix_fmt='yuv420p'
        for _ in range(12):
            for packet in stream.encode(av.VideoFrame.from_image(Image.new('RGB',(64,64),'red'))):container.mux(packet)
        for packet in stream.encode():container.mux(packet)
    return out.getvalue()
MP4=sample_video()
def info():
    data={node:{'input':{}} for node in comfy_h3.NODES}
    for node,(field,weight) in comfy_h3.WEIGHTS.items():data[node]['input']={'required':{field:[[weight]]}}
    data['MiniMaxH3ImageToVideo']['input']['optional']={'first_frame':['IMAGE'],'last_frame':['IMAGE']}
    return data
class Fixture(BaseHTTPRequestHandler):
    calls=[];busy=False;failed=False;missing=False
    def log_message(self,*args):pass
    def reply(self,value):
        raw=json.dumps(value).encode() if isinstance(value,dict) else value
        self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        self.calls.append(('GET',self.path,None,self.headers.get('Authorization')))
        if self.path=='/object_info':return self.reply(info())
        if self.path=='/queue':return self.reply({'queue_running':[[1,ID]] if self.busy else [],'queue_pending':[]})
        if self.path.startswith('/view?'):return self.reply(MP4)
        if self.missing:return self.reply({})
        status={'status_str':'error' if self.failed else 'success','completed':True,'messages':[['execution_error',{'exception_message':'Out of memory'}]]}
        self.reply({ID:{'status':status,'outputs':{'16':{'images':[{'filename':'a.mp4','subfolder':'video\\Guangyu','type':'output'}]}}}})
    def do_POST(self):
        raw=self.rfile.read(int(self.headers['Content-Length']))
        body=json.loads(raw) if 'application/json' in self.headers.get('Content-Type','') else None
        self.calls.append(('POST',self.path,body,self.headers.get('Authorization')))
        self.reply({'name':'input.png','subfolder':'','type':'input'} if self.path=='/upload/image' else {'prompt_id':ID})
class H3Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        p=patch.object(storage,'DATA',Path(tmp.name));p.start();self.addCleanup(p.stop);storage.init()
        Fixture.calls=[];Fixture.busy=False;Fixture.failed=False;Fixture.missing=False
        self.app=ThreadingHTTPServer(('127.0.0.1',0),Fixture);threading.Thread(target=self.app.serve_forever,daemon=True).start()
        self.addCleanup(self.app.server_close);self.addCleanup(self.app.shutdown)
        self.p={'id':storage.uid(),'name':'Fixture local H3','kind':'video','protocol':'comfy_h3','model':comfy_h3.MODEL,'platform':'comfy_h3','base_url':f'http://127.0.0.1:{self.app.server_port}','allow_local':True,'extra':{},'custom':{},'secret':storage.crypt('do-not-send')}
        raw=io.BytesIO();Image.new('RGB',(64,64),'red').save(raw,format='PNG')
        self.asset=uploads.save({'name':'fixture.png','data_base64':base64.b64encode(raw.getvalue()).decode()})
        self.job={'id':storage.uid(),'created_at':storage.now(),'provider_snapshot':self.p,'kind':'video','prompt':'Steam rises slowly','seconds':5,'size':'auto','parameters':{'aspect_ratio':'9:16','seed':12},'input_assets':{'first_frame':self.asset['id'],'last_frame':self.asset['id'],'references':[]},'status':'queued'}
        storage.put('jobs',self.job)
    def test_discovery_checks_local_nodes_and_advertises_only_video(self):
        report=model_catalog.discover_saved(self.p)
        self.assertEqual(report['models'][0]['supported_kinds'],['video'])
        self.assertEqual([c[0] for c in Fixture.calls],['GET'])
        caps=capabilities.effective(self.p)
        self.assertTrue(caps['first_frame'] and caps['last_frame']);self.assertFalse(caps['reference_images'] or caps['audio'])
        self.assertEqual(video_controls.options(self.p)['durations'],[5,7,10,15])
    def test_submit_uploads_frames_maps_graph_saves_mp4_and_resume_never_posts(self):
        providers.validate(self.p)
        result=providers.execute(self.p,self.job)
        posts=[c for c in Fixture.calls if c[0]=='POST']
        self.assertEqual([c[1] for c in posts],['/upload/image','/upload/image','/prompt'])
        graph=posts[-1][2]['prompt'];self.assertEqual(graph['8']['inputs']['width'],480)
        self.assertEqual(graph['8']['inputs']['length'],124);self.assertEqual(graph['8']['inputs']['last_frame'],['20',0])
        self.assertEqual(graph['8']['inputs']['first_frame'],['19',0]);self.assertEqual(graph['19']['inputs']['crop'],'center')
        self.assertEqual(graph['12']['inputs']['noise_seed'],12)
        self.assertTrue(all(c[3] is None for c in Fixture.calls))
        asset=result['assets'][0];self.assertTrue(asset['local']);self.assertEqual((storage.DATA/asset['url'].lstrip('/')).read_bytes(),MP4)
        self.assertEqual(work_library.local_path(asset['url']),(storage.DATA/asset['url'].lstrip('/')))
        self.assertEqual((asset['width'],asset['height'],asset['duration_seconds']),(64,64,.5),'Read actual file metadata, including resumed legacy jobs')
        Fixture.calls=[];providers.execute(self.p,storage.get('jobs',self.job['id']),resume=True)
        self.assertFalse(any(c[0]=='POST' for c in Fixture.calls))
    def test_busy_queue_rejects_without_upload_or_submission(self):
        Fixture.busy=True
        with self.assertRaisesRegex(ValueError,'其他任务'):providers.execute(self.p,self.job)
        self.assertFalse(any(c[0]=='POST' for c in Fixture.calls))
    def test_missing_weights_and_nonlocal_connections_rejected(self):
        with patch.object(comfy_h3,'local_request',return_value={}):
            with self.assertRaisesRegex(ValueError,'缺少'):comfy_h3.discover(self.p)
        for base in ('https://example.com','http://192.168.0.2:8188','http://127.0.0.1:8188/v1'):
            with self.assertRaises(ValueError):providers.validate({**self.p,'base_url':base})
    def test_invalid_inputs_rejected_before_network(self):
        for changes in ({'seconds':30},{'size':'1920x1080'},{'input_assets':{}},{'parameters':{'aspect_ratio':'21:9'}},{'parameters':{'audio':True}}):
            with self.assertRaises(ValueError):providers.build(self.p,{**self.job,**changes})
        self.assertEqual(Fixture.calls,[])
    def test_follow_portrait_geometry_and_long_duration_profiles(self):
        raw=io.BytesIO();Image.new('RGB',(940,1672),'blue').save(raw,format='PNG')
        asset=uploads.save({'data_base64':base64.b64encode(raw.getvalue()).decode()})
        j={**self.job,'input_assets':{'first_frame':asset['id']},'parameters':{}}
        self.assertEqual(comfy_h3.output_settings(j),(480,864,124))
        for seconds,frames in ((5,124),(7,175),(10,243),(15,362)):
            job={**j,'seconds':seconds,'parameters':{'resolution':'preview'}}
            providers.build(self.p,job)
            g=comfy_h3.graph(job,{'first_frame':'portrait.png'})
            self.assertEqual((g['8']['inputs']['width'],g['8']['inputs']['height'],g['8']['inputs']['length']),(352,608,frames))
        with self.assertRaisesRegex(ValueError,'细节'):providers.build(self.p,{**j,'seconds':15})
        self.assertEqual(Fixture.calls,[])
    def test_runtime_error_and_missing_history_never_repost(self):
        j=storage.update_job(self.job['id'],upstream_id=ID)
        Fixture.failed=True
        with self.assertRaisesRegex(providers.ProviderError,'Out of memory'):providers.execute(self.p,j,resume=True)
        self.assertEqual(storage.get('jobs',j['id'])['upstream_status'],'failed')
        Fixture.failed=False;Fixture.missing=True
        with patch.object(comfy_h3.time,'sleep'):
            with self.assertRaises(providers.ProviderError) as caught:providers.execute(self.p,j,resume=True)
        self.assertTrue(caught.exception.uncertain)
        self.assertFalse(any(c[0]=='POST' for c in Fixture.calls))
    def test_media_path_rejects_traversal(self):
        for value in ('../private.mp4','C:/private.mp4','/private.mp4','a\\..\\private.mp4'):
            with self.assertRaises(ValueError):comfy_h3.safe_component(value,True)

if __name__=='__main__':unittest.main()
