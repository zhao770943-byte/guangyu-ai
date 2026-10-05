"""Ordered multi-shot films, atomic review and durable submission receipts."""
import copy
import json
import unittest
import test_visual_studio
import storage


class VisualFilmTests(unittest.TestCase):
    setUp = test_visual_studio.VisualStudioTests.setUp
    api = test_visual_studio.VisualStudioTests.api
    image = test_visual_studio.VisualStudioTests.image

    def fixture(self):
        provider={'id':storage.uid(),'name':'fixture video','kind':'video','protocol':'weijin_video','model':'sd-2.0-720-900','base_url':'https://www.weijinapi.top/v1','secret':'','extra':{},'custom':{},'video_model_metadata':{'durations_seconds':[15],'ratios':['16:9','9:16'],'max_images':9,'resolution':'720p'}}
        storage.put('providers',provider)
        nodes=[{'id':storage.uid(),'kind':'shot','title':f'Shot {i}','prompt':f'Image {i}','video_prompt':f'Action {i}','ratio':'9:16','upload_id':self.image(color)['id']} for i,color in enumerate(('red','blue','green'),1)]
        p=self.api('/api/visual-projects/save',{'title':'Film','story':'An arrival','nodes':nodes})
        body={'id':p['id'],'version':p['version'],'request_id':storage.uid(),'provider_id':provider['id'],'seconds':15,'node_ids':[n['id'] for n in reversed(p['nodes'])],'durations':[4,5,6]}
        return p,provider,body

    def test_one_job_exact_order_prompt_timeline_and_retry_after_reload(self):
        p,provider,body=self.fixture();r=self.api('/api/visual-projects/film-generate',body,202)
        self.assertEqual(self.mock_dispatch.call_count,1);self.assertEqual(len(storage.items('jobs')),1)
        job=r['job'];self.assertEqual(job['kind'],'video');self.assertEqual(job['seconds'],15)
        self.assertEqual(job['input_assets']['references'],[n['versions'][0]['upload_id'] for n in reversed(p['nodes'])])
        self.assertEqual([t['node_id'] for t in job['visual_film_timeline']],body['node_ids'])
        self.assertEqual([(t['start'],t['end']) for t in job['visual_film_timeline']],[(0,4),(4,9),(9,15)])
        self.assertLess(job['prompt'].index('Action 3'),job['prompt'].index('Action 1'))
        self.assertEqual(job['parameters']['aspect_ratio'],'9:16');self.assertEqual(job['collection_id'],'visual:'+p['id'])
        self.assertNotIn('provider_snapshot',job);self.assertNotIn('film_requests',r['project'])
        storage.init();again=self.api('/api/visual-projects/film-generate',body,202)
        self.assertEqual(again['job']['id'],job['id']);self.assertEqual(self.mock_dispatch.call_count,1)
        self.assertEqual(self.api('/api/visual-projects?id='+p['id'])['jobs'][0]['id'],job['id'])
        self.api('/api/visual-projects/film-generate',{**body,'version':r['project']['version'],'request_id':storage.uid()},400)
        self.assertEqual(self.mock_dispatch.call_count,1)

    def test_missing_prompt_stale_mismatch_duration_fail_without_side_effects(self):
        p,provider,body=self.fixture();p['nodes'][0]['prompt']='Edited image description';p['nodes'][2]['video_prompt']=''
        p=self.api('/api/visual-projects/save',p);body['version']=p['version']
        before=json.dumps(storage.get('visual_projects',p['id']),sort_keys=True)
        for extra in ({},{'durations':[1,1,1]},{'node_ids':[p['nodes'][0]['id']]*3},{'review_versions':{p['nodes'][0]['id']:p['nodes'][0]['active_version_id']}}):
            self.api('/api/visual-projects/film-generate',{**body,**extra},400)
            self.assertEqual(json.dumps(storage.get('visual_projects',p['id']),sort_keys=True),before)
            self.assertEqual(storage.items('jobs'),[])
        self.assertEqual(self.mock_dispatch.call_count,0)

    def test_explicit_review_keeps_old_version_and_uses_latest_config(self):
        p,provider,body=self.fixture();p['nodes'][0]['prompt']='Reviewed image description';p['nodes'][0]['video_prompt']='Latest movement'
        p['film_options']={k:body[k] for k in ('node_ids','provider_id','seconds','durations')}
        p=self.api('/api/visual-projects/save',p);body['version']=p['version'];node=p['nodes'][0]
        self.assertTrue(node['stale']);self.assertEqual(self.api('/api/visual-projects?id='+p['id'])['film_options']['node_ids'],body['node_ids'])
        self.api('/api/visual-projects/film-generate',body,400)
        r=self.api('/api/visual-projects/film-generate',{**body,'review_versions':{node['id']:node['active_version_id']}},202)
        current=r['project']['nodes'][0];self.assertFalse(current['stale']);self.assertEqual(len(current['versions']),2)
        self.assertEqual(current['versions'][0]['id'],node['active_version_id']);self.assertIn('Latest movement',r['job']['prompt'])

    def test_review_rollback_when_provider_validation_fails(self):
        p,provider,body=self.fixture();p['nodes'][0]['prompt']='Edited';p=self.api('/api/visual-projects/save',p)
        before=copy.deepcopy(storage.get('visual_projects',p['id']))
        provider['extra']={'resolution':'4K'};storage.put('providers',provider)
        body.update(version=p['version'],seconds=30,durations=[10,10,10],review_versions={p['nodes'][0]['id']:p['nodes'][0]['active_version_id']})
        self.api('/api/visual-projects/film-generate',body,400)
        self.assertEqual(storage.get('visual_projects',p['id']),before);self.assertEqual(storage.items('jobs'),[])

    def test_upstream_review_cannot_be_bypassed_and_ratios_must_match(self):
        p,provider,body=self.fixture();p['nodes'][1]['refs']=[p['nodes'][0]['id']];p=self.api('/api/visual-projects/save',p)
        p=self.api('/api/visual-projects/review',{'id':p['id'],'version':p['version'],'node_id':p['nodes'][1]['id']})
        p['nodes'][0]['prompt']='Changed upstream';p=self.api('/api/visual-projects/save',p)
        body.update(version=p['version'],node_ids=[n['id'] for n in p['nodes'][1:]],durations=[7,8],review_versions={p['nodes'][1]['id']:p['nodes'][1]['active_version_id']})
        self.api('/api/visual-projects/film-generate',body,400);self.assertEqual(self.mock_dispatch.call_count,0)
        p['nodes'][2]['ratio']='16:9';p=self.api('/api/visual-projects/save',p);body['version']=p['version']
        self.api('/api/visual-projects/film-generate',body,400)

    def test_first_frame_only_model_is_not_a_multi_image_film_model(self):
        p,provider,body=self.fixture();provider.update(protocol='comfy_h3',model='MiniMax-H3',base_url='http://127.0.0.1:8188')
        storage.put('providers',provider);self.api('/api/visual-projects/film-generate',body,400);self.assertEqual(self.mock_dispatch.call_count,0)

if __name__=='__main__':unittest.main()
