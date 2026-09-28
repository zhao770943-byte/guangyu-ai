"""Storyboard HTTP acceptance in isolated storage; no provider network calls."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server,storage,storyboards,uploads


class StoryboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.patch=patch.object(storage,'DATA',Path(self.temp.name));self.patch.start();self.addCleanup(self.patch.stop);storage.init()
        self.dispatch=patch.object(server,'dispatch');self.mock_dispatch=self.dispatch.start();self.addCleanup(self.dispatch.stop)
        self.pool=patch.object(server,'ACTIVE',set());self.pool.start();self.addCleanup(self.pool.stop)
        self.app=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.app.daemon_threads=True
        self.addCleanup(self.app.server_close);self.addCleanup(self.app.shutdown)
        self.origin=f'http://127.0.0.1:{self.app.server_port}'
        for name,value in [('PORT',self.app.server_port),('ORIGIN',self.origin)]:
            p=patch.object(server,name,value);p.start();self.addCleanup(p.stop)
        threading.Thread(target=self.app.serve_forever,daemon=True).start()
        self.provider={'id':storage.uid(),'name':'fixture','kind':'image','protocol':'openai_image','model':'gpt-image-1','base_url':'https://example.invalid/v1','secret':'','extra':{},'custom':{}}
        storage.put('providers',self.provider)

    def api(self,path,body=None,status=200):
        req=urllib.request.Request(self.origin+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json','Origin':self.origin,'X-CSRF-Token':server.CSRF})
        try:
            with urllib.request.urlopen(req,timeout=5) as r:code=r.status;data=json.load(r)
        except urllib.error.HTTPError as e:code=e.code;data=json.load(e)
        self.assertEqual(code,status,data)
        return data

    def board(self):
        return self.api('/api/storyboards/save',{'title':'A film','story':'A woman walks on a shopping street.','master_prompt':'Burgundy blazer.','provider_id':self.provider['id'],'ratio':'9:16','shots':[{'title':str(i),'prompt':'One still moment '+str(i)} for i in range(4)]})

    def test_page_scripts_and_styles_are_served(self):
        import re
        with urllib.request.urlopen(self.origin+'/') as r:html=r.read().decode()
        self.assertIn('/storyboards.js',html);self.assertIn('/storyboards.css',html)
        for route in re.findall(r'(?:src|href)="(/[^" ]+\.(?:js|css))"',html):
            with urllib.request.urlopen(self.origin+route) as r:
                self.assertEqual(r.status,200)
                self.assertEqual(r.read(),(server.ROOT/'public'/route[1:]).read_bytes())

    def generate(self,b,stage='master',**extra):
        return self.api('/api/storyboards/generate',{'id':b['id'],'version':b['version'],'request_id':storage.uid(),'stage':stage,**extra},202)

    def finish(self,identity):
        name=storage.uid()+'.png';Image.new('RGB',(64,96),'blue').save(storage.DATA/'media'/name)
        storage.update_job(identity,status='succeeded',archive_status='saved',result={'assets':[{'type':'image','url':'/media/'+name,'local':True}],'text':''})

    def confirmed(self):
        b=self.generate(self.board());self.finish(b['master_job_id'])
        return self.api('/api/storyboards/confirm',{'id':b['id'],'version':b['version']})

    def test_library_selects_exact_asset_and_preserves_copy_when_work_deleted(self):
        b=self.generate(self.board());identity=b['master_job_id'];self.finish(identity)
        j=storage.get('jobs',identity)
        name=storage.uid()+'.png';Image.new('RGB',(120,80),'red').save(storage.DATA/'media'/name)
        j['result']['assets'].append({'type':'image','url':'/media/'+name,'local':True})
        storage.put('jobs',j);calls=self.mock_dispatch.call_count
        a=self.api('/api/library/image',{'job_id':identity,'asset_index':1})
        self.assertEqual((a['width'],a['height']),(120,80))
        self.assertEqual(self.mock_dispatch.call_count,calls)
        self.assertNotIn('filename',a)
        self.api('/api/jobs/delete',{'id':identity})
        self.assertEqual(uploads.get(a['id'])['width'],120)
        self.api('/api/library/image',{'job_id':identity,'asset_index':1},400)

    def test_library_rejects_invalid_or_unavailable_images_without_dispatch(self):
        b=self.generate(self.board());identity=b['master_job_id']
        self.api('/api/library/image',{'job_id':identity,'asset_index':0},400)
        self.finish(identity);calls=self.mock_dispatch.call_count
        for index in (-1,2,True,'0',None):
            self.api('/api/library/image',{'job_id':identity,'asset_index':index},400)
        self.api('/api/library/image',{'job_id':identity},400)
        for asset in ({'type':'image','local':False,'url':'https://example.invalid/a.png'},
                      {'type':'video','local':True,'url':'/media/a.mp4'},
                      {'type':'image','local':True,'url':'/media/../../private.png'}):
            storage.update_job(identity,result={'assets':[asset]})
            self.api('/api/library/image',{'job_id':identity,'asset_index':0},400)
        self.assertEqual(self.mock_dispatch.call_count,calls)

    def test_full_flow_reference_is_shared_batch_atomic_and_video_not_generated(self):
        b=self.confirmed();master=b['master_asset'];b=self.generate(b,'shots')
        shotjobs=[storage.get('jobs',s['job_id']) for s in b['shots']]
        self.assertEqual(len(shotjobs),4)
        self.assertEqual(len({j['id'] for j in shotjobs}),4)
        for j in shotjobs:
            self.assertEqual(j['input_assets']['references'],[master['id']])
            self.assertEqual(j['kind'],'image')
            self.assertEqual(j['parameters']['n'],1)
            self.assertIn('Burgundy blazer',j['prompt'])
            self.assertEqual(j['storyboard_id'],b['id'])
        self.assertEqual(self.mock_dispatch.call_count,5)
        for j in shotjobs:self.finish(j['id'])
        a=self.api('/api/storyboards/transfer',{'id':b['id'],'job_id':shotjobs[0]['id']})
        self.assertEqual(uploads.binary(a['id'])[1],uploads.binary(master['id'])[1])
        self.assertNotIn('provider_snapshot',json.dumps(b))
        storage.init()
        restored=self.api('/api/storyboards?id='+b['id'])
        self.assertEqual(restored['shots'],b['shots'])
        self.assertEqual(restored['master_upload_id'],master['id'])
        self.assertFalse(restored['busy'])
        self.assertEqual(storage.items('conversations'),[])

    def test_idempotent_submission_and_stale_project_are_protected(self):
        b=self.board();request={'id':b['id'],'version':b['version'],'request_id':storage.uid(),'stage':'master'}
        first=self.api('/api/storyboards/generate',request,202);again=self.api('/api/storyboards/generate',request,202)
        self.assertEqual(first['master_job_id'],again['master_job_id']);self.assertEqual(self.mock_dispatch.call_count,1)
        self.api('/api/storyboards/save',b,400)
        self.assertEqual(len(storage.items('jobs')),1)

    def test_reference_support_and_confirmation_required_before_any_batch_jobs(self):
        b=self.board();self.api('/api/storyboards/generate',{'id':b['id'],'version':b['version'],'request_id':storage.uid(),'stage':'shots'},400)
        self.assertFalse(storage.items('jobs'))
        b=self.confirmed();storage.put('providers',{**self.provider,'model':'dall-e-3'})
        before=len(storage.items('jobs'))
        self.api('/api/storyboards/generate',{'id':b['id'],'version':b['version'],'request_id':storage.uid(),'stage':'shots'},400)
        self.assertEqual(len(storage.items('jobs')),before)

    def test_retry_one_failed_shot_keeps_successes(self):
        b=self.generate(self.confirmed(),'shots')
        for s in b['shots']:self.finish(s['job_id'])
        storage.update_job(b['shots'][1]['job_id'],status='failed')
        old=[s['job_id'] for s in b['shots']]
        b=self.generate(b,'shot',shot_id=b['shots'][1]['id'])
        new=[s['job_id'] for s in b['shots']]
        self.assertNotEqual(old[1],new[1]);self.assertEqual(old[:1]+old[2:],new[:1]+new[2:])

    def test_batch_queue_limit_has_no_partial_submission(self):
        b=self.confirmed();server.ACTIVE.update(str(i) for i in range(10))
        before=len(storage.items('jobs'))
        self.api('/api/storyboards/generate',{'id':b['id'],'version':b['version'],'request_id':storage.uid(),'stage':'shots'},400)
        self.assertEqual(len(storage.items('jobs')),before)

    def test_unarchived_unrelated_and_path_traversal_assets_rejected(self):
        b=self.generate(self.board())
        self.api('/api/storyboards/confirm',{'id':b['id'],'version':b['version']},400)
        self.api('/api/storyboards/transfer',{'id':b['id'],'job_id':'other'},400)
        storage.update_job(b['master_job_id'],status='succeeded',result={'assets':[{'type':'image','url':'/media/../private.png','local':True}]})
        self.api('/api/storyboards/confirm',{'id':b['id'],'version':b['version']},400)

    def test_reconfirm_is_idempotent_and_restart_does_not_resubmit(self):
        b=self.confirmed();a=self.api('/api/storyboards/confirm',{'id':b['id'],'version':b['version']})
        self.assertEqual(a['master_upload_id'],b['master_upload_id'])
        b=self.generate(b,'shots');count=self.mock_dispatch.call_count
        server.recover()
        self.assertEqual(self.mock_dispatch.call_count,count)
        self.assertTrue(all(storage.get('jobs',s['job_id'])['status']=='interrupted' for s in b['shots']))

    def test_invalid_later_shot_does_not_leave_partial_jobs(self):
        b=self.confirmed();before=len(storage.items('jobs'));original=server.create_job;calls=[]
        def prepare(body,**kwargs):
            calls.append(body)
            if len(calls)==2:raise ValueError('fixture rejects second shot')
            return original(body,**kwargs)
        with patch.object(server,'create_job',side_effect=prepare):
            self.api('/api/storyboards/generate',{'id':b['id'],'version':b['version'],'request_id':storage.uid(),'stage':'shots'},400)
        self.assertEqual(len(storage.items('jobs')),before)
        self.assertTrue(all(s['job_id'] is None for s in storyboards.require(b['id'])['shots']))

    def test_batch_uses_three_workers_and_queues_fourth(self):
        b=self.confirmed();entered=threading.Event();release=threading.Event();lock=threading.Lock();counter={'running':0,'maximum':0,'calls':0}
        name=storage.uid()+'.png';Image.new('RGB',(32,32)).save(storage.DATA/'media'/name)
        def execute(*args):
            with lock:
                counter['running']+=1;counter['calls']+=1
                counter['maximum']=max(counter['maximum'],counter['running'])
                if counter['running']==3:entered.set()
            release.wait(5)
            with lock:counter['running']-=1
            return {'text':'','assets':[{'type':'image','url':'/media/'+name,'local':True}]}
        def dispatch(job):
            with server.ACTIVE_LOCK:
                server.ACTIVE.add(job['id']);server.POOL.submit(server.run_job,job['id'])
        with ThreadPoolExecutor(max_workers=3) as pool,patch.object(server,'POOL',pool),patch.object(server.providers,'execute',side_effect=execute):
            self.mock_dispatch.side_effect=dispatch
            try:
                b=self.generate(b,'shots')
                self.assertTrue(entered.wait(3),'three images should run together')
                states=[storage.get('jobs',s['job_id'])['status'] for s in b['shots']]
                self.assertEqual(states.count('submitting'),3);self.assertEqual(states.count('queued'),1)
            finally:
                release.set();pool.shutdown(wait=True)
        self.assertEqual(counter['maximum'],3);self.assertEqual(counter['calls'],4)
        self.assertTrue(all(storage.get('jobs',s['job_id'])['status']=='succeeded' for s in b['shots']))

if __name__=='__main__':unittest.main()
