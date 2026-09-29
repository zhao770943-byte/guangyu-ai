"""Mixed-vendor routing and native media contracts; never calls a paid API."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import platform_catalog,model_catalog,providers,storage,video_controls,capabilities


class Fixture(BaseHTTPRequestHandler):
    calls=[]
    status='succeeded'
    def log_message(self,*args):pass
    def reply(self,body):
        raw=json.dumps(body).encode();self.send_response(200)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        self.calls.append(('POST',self.path,json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
        self.reply({'id':'task_fixture'} if self.path.endswith('/tasks') else {'data':[{'url':'https://example.com/fixture.png'}]})
    def do_GET(self):
        self.calls.append(('GET',self.path,None))
        self.reply({'id':'task_fixture','status':self.status,'content':{'video_url':'https://example.com/fixture.mp4'},'usage':{'total_tokens':123}})


class VendorCatalogTests(unittest.TestCase):
    def test_modalities_and_originals_are_not_interchangeable(self):
        ps=platform_catalog.list_presets()
        chat=[p for p in ps if 'chat' in p['model_types'] and p['category'] not in ('custom','local')]
        self.assertGreaterEqual(len(chat),25)
        by={p['id']:p for p in ps}
        for identity in ('deepseek','anthropic','moonshot','baidu','tencent','yi','iflytek'):
            self.assertEqual(by[identity]['model_types'],['chat'])
        self.assertEqual(by['elevenlabs']['model_types'],['audio'])
        self.assertEqual(by['bfl']['model_types'],['image'])
        self.assertNotIn('video',by['openai']['model_types'])
        self.assertNotIn('audio',by['ark']['model_types'])
        self.assertNotEqual(by['dashscope']['profiles']['chat']['base_url'],by['dashscope']['profiles']['video']['base_url'])
        self.assertEqual(by['meta']['category'],'hosted')
        self.assertIn('NVIDIA',by['meta']['api_key_label'])
        for p in ps:
            self.assertEqual(set(p['profiles']),set(p['model_types']))

    def test_official_ids_route_to_the_vendor_contract(self):
        for pid in ('openai','gemini','ark','minimax','cohere','xai','zhipu'):
            p=platform_catalog.get_preset(pid)
            for model in p.get('official_models',[]):
                kind=model['model_kinds'][0]
                value={**p,'platform':pid,'kind':kind,'name':'Fixture','model':model['id'],'protocol':model['protocol'],'custom':model.get('custom',{}),'extra':{}}
                providers.validate(value)
                family='gemini' if pid=='gemini' else 'openai'
                entry={'name':'models/'+model['id'],'supportedGenerationMethods':['generateContent']} if family=='gemini' else {'id':model['id']}
                rows,_=model_catalog._normalize([entry],family,{**value,'protocol':p['discovery_protocol']},'')
                self.assertEqual(rows[0]['protocol'],model['protocol'],model['id'])
        banana=platform_catalog.get_preset('gemini')['official_models']
        self.assertTrue(all('image' in m['model_kinds'] and 'video' not in m['model_kinds'] for m in banana))
        self.assertTrue(all('preview' not in m['id'] for m in banana))

    def test_aliases_do_not_invent_compatible_gateway_protocols(self):
        for identity,expected in [('nano-banana-2',['image']),('seedance2.5-9图',['video']),('doubao-seedream-5-0-pro-260628',['image'])]:
            self.assertEqual(providers.model_constraints(identity)['kinds'],expected)
        p={'platform':'custom','protocol':'openai_chat','base_url':'https://proxy.example/v1'}
        rows,_=model_catalog._normalize([{'id':'doubao-seedance-2-5-260628','base_url':'https://bad.example'}],'openai',p,'')
        self.assertIsNone(rows[0]['protocol'])
        self.assertEqual(rows[0]['base_url'],p['base_url'])
        grok={'platform':'xai','protocol':'openai_image','kind':'image','model':'grok-imagine-image-2.0'}
        self.assertFalse(capabilities.mapped_controls(grok)['size'])
        with self.assertRaises(ValueError):capabilities.validate_job(grok,{}, {},'1024x1024')

    def test_hosted_manufacturer_filters_other_model_owners(self):
        p={'platform':'meta','protocol':'openai_chat','base_url':'https://integrate.api.nvidia.com/v1'}
        rows,_=model_catalog._normalize([{'id':'meta/llama-4-fixture'},{'id':'microsoft/phi-4'},{'id':'nvidia/nemotron-fixture'}],'openai',p,'')
        self.assertEqual([r['id'] for r in rows],['meta/llama-4-fixture'])


class ArkContracts(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        data=patch.object(storage,'DATA',Path(temp.name));data.start();self.addCleanup(data.stop);storage.init()
        self.app=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        threading.Thread(target=self.app.serve_forever,daemon=True).start()
        self.addCleanup(self.app.server_close);self.addCleanup(self.app.shutdown)
        Fixture.calls=[];Fixture.status='succeeded'
        self.p={'name':'fixture','platform':'ark','kind':'video','protocol':'ark_video','model':'doubao-seedance-2-5-260628',
                'base_url':f'http://127.0.0.1:{self.app.server_port}/api/v3','allow_local':True,'secret':'','extra':{}}
        self.job={'id':storage.uid(),'created_at':storage.now(),'kind':'video','provider_snapshot':self.p,'prompt':'A mountain landscape',
                  'size':'auto','seconds':30,'parameters':{'aspect_ratio':'16:9','audio':False},'input_assets':{},'status':'queued'}
        storage.put('jobs',self.job)

    def test_video_submission_poll_and_resume_never_repost(self):
        result=providers.execute(self.p,self.job)
        self.assertEqual(result['assets'][0]['url'],'https://example.com/fixture.mp4')
        self.assertEqual(result['usage']['total_tokens'],123)
        self.assertEqual(Fixture.calls[0][1],'/api/v3/contents/generations/tasks')
        body=Fixture.calls[0][2]
        self.assertEqual(body['duration'],30);self.assertEqual(body['ratio'],'16:9');self.assertIs(body['generate_audio'],False)
        self.assertEqual(body['content'],[{'type':'text','text':self.job['prompt']}])
        self.assertEqual(storage.get('jobs',self.job['id'])['upstream_id'],'task_fixture')
        Fixture.calls=[]
        providers.execute(self.p,storage.get('jobs',self.job['id']),resume=True)
        self.assertEqual([c[0] for c in Fixture.calls],['GET'])

    def test_terminal_failure_preserves_task_and_resume_only_queries(self):
        Fixture.status='failed'
        with self.assertRaises(providers.ProviderError):providers.execute(self.p,self.job)
        self.assertEqual(storage.get('jobs',self.job['id'])['upstream_id'],'task_fixture')
        self.assertEqual([c[0] for c in Fixture.calls],['POST','GET'])

    def test_model_limits_and_frame_roles_are_validated_before_post(self):
        p={**self.p,'model':'doubao-seedance-2-0-260128'}
        with self.assertRaises(ValueError):providers.execute(p,self.job)
        self.assertNotIn(30,video_controls.options(p)['durations'])
        self.assertIn(30,video_controls.options(self.p)['durations'])
        self.assertEqual(Fixture.calls,[])
        with patch('uploads.get',return_value={}),patch('uploads.data_uri',side_effect=lambda i:'data:image/png;base64,'+i):
            j={**self.job,'input_assets':{'first_frame':'first','last_frame':'last'}}
            _,body,_=providers.build(self.p,j)
            self.assertEqual([c.get('role') for c in body['content']],[None,'first_frame','last_frame'])
            self.assertNotIn('image_url',body['content'][0])
            with self.assertRaises(ValueError):providers.build(self.p,{**j,'input_assets':{'last_frame':'last'}})
            with self.assertRaises(ValueError):providers.build(self.p,{**j,'input_assets':{'first_frame':'first','references':['ref']}})

    def test_seedream_uses_json_references_and_omits_unselected_parameters(self):
        p={**self.p,'kind':'image','protocol':'ark_image','model':'doubao-seedream-5-0-pro-260628'}
        j={**self.job,'kind':'image','parameters':{},'input_assets':{}}
        path,body,multipart=providers.build(p,j)
        self.assertEqual(path,'/images/generations');self.assertFalse(multipart)
        self.assertNotIn('size',body);self.assertNotIn('image',body)
        result=providers.execute(p,j);self.assertEqual(result['assets'][0]['type'],'image')
        with patch('uploads.get',return_value={}),patch('uploads.data_uri',return_value='data:image/png;base64,fixture'):
            _,body,multipart=providers.build(p,{**j,'input_assets':{'references':['ref']}})
            self.assertEqual(body['image'],['data:image/png;base64,fixture']);self.assertFalse(multipart)
        with self.assertRaises(ValueError):providers.build(p,{**j,'parameters':{'quality':'high'}})

    def test_reviewed_grok_and_photon_mappings_submit_then_extract(self):
        for pid,kind,submission,completed,path in [
            ('xai','video',{'request_id':'fixture-xai'},{'status':'done','video':{'url':'https://example.com/grok.mp4'}},'/videos/generations'),
            ('luma','image',{'id':'fixture-luma'},{'state':'completed','assets':{'image':'https://example.com/photon.png'}},'/generations/image'),
        ]:
            catalog=platform_catalog.get_preset(pid)
            m=next(m for m in catalog['official_models'] if m['model_kinds']==[kind])
            p={**self.p,'platform':pid,'kind':kind,'model':m['id'],'protocol':'custom','custom':m['custom']}
            providers.validate(p)
            job={**self.job,'kind':kind,'seconds':10,'parameters':{}}
            with patch.object(providers,'request',side_effect=[submission,completed]) as request:
                result=providers.execute(p,job)
                self.assertEqual(request.call_args_list[0].args[1],path)
                self.assertEqual(len(request.call_args_list),2)
                self.assertEqual(result['assets'][0]['type'],kind)
                self.assertNotIn('size',request.call_args_list[0].args[2])
            if kind=='video':
                self.assertNotIn(20,video_controls.options(p)['durations'])
                with self.assertRaises(ValueError):providers.build(p,{**job,'seconds':30})


if __name__=='__main__':unittest.main()
