import json
import unittest
import storage
import server
import novel_studio as novel
import novel_quality
import ai_control
from test_novel_studio import NovelTests
from test_film_batch import clip


class QualityTests(unittest.TestCase):
    setUp = NovelTests.setUp
    api = NovelTests.api
    image = NovelTests.image
    create = NovelTests.create
    outline = NovelTests.outline
    script = NovelTests.script
    get = NovelTests.get
    command = NovelTests.command

    def fixture(self):
        self.create()
        p = novel.require(self.p['id'])
        p['plan'] = self.outline()
        p['plan']['episodes'][0].update(self.script())
        return p

    def test_budget_counts_future_and_rejects_insufficient_ceiling(self):
        p = self.fixture()
        p.update(phase='script_review',review_videos=True,request_limit=10)
        novel.persist(p)
        self.assertEqual(novel_quality.budget(p)['minimum'],19)
        with self.assertRaises(ValueError):novel_quality.require_budget(p)
        p['request_limit']=30
        novel_quality.require_budget(p)

    def test_visual_motion_contains_actual_images_and_neighbor(self):
        p = self.fixture()
        a,b=self.image(),self.image('blue')
        p.update(phase='video_audit',motion_vision={'provider_id':self.chat['id'],'model':self.chat['model'],'signature':ai_control.fingerprint(self.chat)})
        p['images'].update({'shot:e1:s1':a['id'],'shot:e1:s2':b['id']})
        key,item=novel.stage_items(p)[1]
        job=novel.prepare_task(p,key,item,server.create_job)
        self.assertEqual(job['vision_upload_ids'],[a['id'],b['id']])
        self.assertEqual(job['ai_role'],'camera')
        self.assertEqual(key,'visionmotion:e1:s2')
        slot={'job_id':job['id'],'done':False,'invalid':False}
        job['result']={'text':json.dumps({'risk':'revise','issues':'首帧坐姿与文字站立冲突','video_prompt':'从坐姿起身'})}
        with self.assertRaises(ValueError):novel.consume(p,key,item,slot,job)
        self.assertTrue(slot['invalid'])
        self.assertTrue(slot['done'])

    def test_project_team_does_not_change_global_default(self):
        self.create()
        before=ai_control.config()
        roles=json.loads(json.dumps(before['roles']))
        roles['director']['provider_id']=self.chat['id']
        p=self.api('/api/novels/save',{**self.p,'ai_team_roles':roles,'team_mode':True})
        self.assertEqual(p['ai_team']['director']['provider_id'],self.chat['id'])
        self.assertEqual(ai_control.config(),before)

    def test_video_gate_requires_all_current_versions_and_local_duration(self):
        p=self.fixture()
        path=storage.DATA/'media'/(storage.uid()+'.mp4')
        clip(path,'navy',seconds=15,rate=8,sound=False)
        p.update(phase='video_review',review_videos=True)
        for s in p['plan']['episodes'][0]['shots']:
            key='video:e1:'+s['id'];job={'id':storage.uid(),'created_at':storage.now(),'kind':'video','status':'succeeded','model':'fixture','novel_slot':key,'novel_project_id':p['id'],'result':{'assets':[{'type':'video','local':True,'url':'/media/'+path.name}]}}
            storage.put('jobs',job);p['slots'][key]={'job_id':job['id'],'attempts':[],'done':True}
        novel.persist(p)
        with self.assertRaises(ValueError):novel.command({'id':p['id'],'version':p['version'],'request_id':storage.uid(),'action':'approve_videos'},set(),server.ACTIVE_LOCK)
        self.get()
        for key,slot in self.p['slots'].items():
            self.command('review_video',slot=key,job_id=slot['job_id'],watched=True,assessment={**{k:True for k in novel_quality.REVIEW_DIMENSIONS},'notes':'已检查完整片段，动作与剧本衔接，剪辑时长合理'})
        self.assertFalse(self.p['video_checks']['video:e1:s1']['has_audio'])
        original=self.p['slots']['video:e1:s1']['job_id']
        self.command('retry',slot='video:e1:s1')
        self.assertEqual(self.p['phase'],'videos')
        self.assertNotIn('video:e1:s1',self.p['video_reviews'])
        p=novel.require(self.p['id'])
        p['slots']['video:e1:s1'].update(job_id=original,done=True)
        p['phase']='video_review';novel.persist(p);self.get()
        self.command('review_video',slot='video:e1:s1',job_id=original,watched=True,assessment={**{k:True for k in novel_quality.REVIEW_DIMENSIONS},'notes':'已检查完整片段，动作与剧本衔接，剪辑时长合理'})
        self.command('approve_videos')
        self.assertEqual(self.p['phase'],'compose')

    def test_five_dimensions_reject_missing_failed_and_empty_evidence(self):
        valid={**{k:True for k in novel_quality.REVIEW_DIMENSIONS},'notes':'实际画面动作与情节衔接明确'}
        for field in novel_quality.REVIEW_DIMENSIONS:
            with self.assertRaises(ValueError):novel_quality.assessment({**valid,field:False})
            with self.assertRaises(ValueError):novel_quality.assessment({k:v for k,v in valid.items() if k!=field})
        with self.assertRaises(ValueError):novel_quality.assessment({**valid,'notes':' '})
        self.assertEqual(novel_quality.assessment(valid),valid)

    def test_enable_standard_requires_pause_and_never_dispatches(self):
        p=self.fixture();p.update(phase='videos',paused=False);novel.persist(p)
        body={'id':p['id'],'version':p['version'],'request_id':storage.uid(),'action':'set_review_standard','standard':'five_dimensions'}
        with self.assertRaises(ValueError):novel.command(body,set(),server.ACTIVE_LOCK)
        p['paused']=True;novel.persist(p);body['version']=p['version']
        count=self.mock_dispatch.call_count
        result=novel.command(body,set(),server.ACTIVE_LOCK)
        self.assertTrue(result['paused']);self.assertTrue(result['review_videos'])
        self.assertEqual(result['review_standard'],'five_dimensions')
        self.assertEqual(self.mock_dispatch.call_count,count)

    def test_gate_transition_is_opt_in_for_legacy(self):
        p=self.fixture();p['phase']='videos';novel.advance(p)
        self.assertEqual(p['phase'],'compose')
        p.update(phase='videos',review_videos=True);novel.advance(p)
        self.assertEqual(p['phase'],'video_review')

    def test_short_video_is_not_approved(self):
        self.create();path=storage.DATA/'media'/(storage.uid()+'.mp4');clip(path,'navy',seconds=2,rate=8,sound=False)
        job={'id':storage.uid(),'status':'succeeded','result':{'assets':[{'type':'video','local':True,'url':'/media/'+path.name}]}}
        with self.assertRaises(ValueError):novel_quality.inspect(job,15)
        with self.assertRaises(ValueError):novel_quality.inspect(job,2,'16:9')
