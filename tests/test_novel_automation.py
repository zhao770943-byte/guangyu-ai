"""Real HTTP/storage/scheduler, deterministic provider fixtures; no paid calls."""
import copy
import json
import unittest
from unittest.mock import patch
import test_novel_studio
import novel_automation as auto
import novel_studio as novel
import ai_control
import production_book
import storage
import server


class AutomationTests(unittest.TestCase):
    setUp = test_novel_studio.NovelTests.setUp
    api = test_novel_studio.NovelTests.api
    image = test_novel_studio.NovelTests.image
    finish_image = test_novel_studio.NovelTests.finish_image
    get = test_novel_studio.NovelTests.get
    command = test_novel_studio.NovelTests.command
    tick = test_novel_studio.NovelTests.tick
    outline = test_novel_studio.NovelTests.outline

    def create(self, **settings):
        test_novel_studio.NovelTests.create(self)
        self.roles={k:{'provider_id':self.chat['id'],'vision':k=='costume','note':''} for k in ai_control.ROLES}
        self.p=self.api('/api/novels/save',{**self.p,'team_mode':True,'ai_team_roles':self.roles,
            'automation':{'enabled':True,'shot_target':24,'script_revisions':2,'image_revisions':1,**settings},'request_limit':240})
        return self.p

    def script(self):
        s=test_novel_studio.NovelTests.script(self)
        s['shots']=[{**s['shots'][0],'id':'s'+str(i),'title':'镜头'+str(i),'seconds':5} for i in range(1,25)]
        return s

    def report(self,kind,failed=False):
        checks=auto.SCRIPT_CHECKS if kind=='script' else ('identity','prop','style') if kind=='asset' else ('identity','prop','space','crowd','eyeline','action') if kind=='frame' else ('space','crowd','eyeline','action','bridge')
        return {'verdict':'revise' if failed else 'pass','checks':{k:not failed for k in checks},
                'evidence':{k:'本次隔离测试的具体检查依据 '+k for k in checks},'issues':'手掌方向错误' if failed else '未发现问题',
                'suggestion':'手掌正面贴合' if failed else '无需修改','video_prompt':'从首帧站位开始，五秒内前进停住，无无关点头'}

    def finish_pending(self,fail=None):
        for key,slot in list(self.get()['slots'].items()):
            j=storage.get('jobs',slot.get('job_id'))
            if not j or j['status']!='queued':continue
            if j['kind']=='video':continue
            if j['kind']=='image':
                self.finish_image(j['id']);continue
            if key=='outline':value=self.outline()
            elif key.startswith(('script:','audit:','light:')):value=self.script()
            else:
                item=next(it for k,it in auto.items(novel.require(self.p['id'])) if k==key)
                kind=item['kind']
                if kind=='detail':
                    value={'shots':[{'id':s['id'],'image_prompt':s['image_prompt'],'video_prompt':s['video_prompt'],
                        'contract':{**{k:'具体拍摄说明 '+k for k in production_book.CONTRACT_FIELDS},'sound_mode':'silent'}} for s in item['episode']['shots']]}
                elif kind=='rewrite':value=self.script()
                else:value=self.report(kind,fail(key,item) if fail else False)
            storage.update_job(j['id'],status='succeeded',result={'text':json.dumps(value,ensure_ascii=False),'assets':[]})

    def run_to(self,phase,fail=None):
        for _ in range(180):
            p=self.tick()
            if p['phase']==phase or p['paused']:return p
            self.finish_pending(fail)
        self.fail('Pipeline stalled at '+self.p['phase'])

    def test_full_pipeline_uses_pixels_then_video_and_never_accepts_delivery(self):
        self.create();self.command('start');p=self.run_to('videos')
        self.assertFalse(p['paused'],p['error']);self.assertEqual(p['phase'],'videos')
        self.assertEqual(p['production_state']['approved'],24)
        self.assertEqual(len(p['locked_assets']),2)
        self.assertTrue(all(r['source']=='ai_visual' for r in p['production_book']['storyboards'].values()))
        p=self.tick();videos=[j for j in p['jobs'] if j['kind']=='video']
        self.assertEqual(len(videos),2)
        self.assertIn('镜尾状态',videos[0]['prompt'])
        for j in novel.all_jobs(novel.require(p['id'])):
            if j.get('novel_slot','').startswith(('auto:asset:','auto:frame:','auto:motion:')):
                self.assertTrue(j['vision_upload_ids']);self.assertTrue(j['automation_image_versions'])
        before=p['requests_used'];self.tick();self.assertEqual(self.p['requests_used'],before)
        self.command('pause');self.tick();self.assertEqual(self.p['requests_used'],before)
        self.assertFalse(self.p.get('final_user_approved'))
        self.command('resume')
        with patch('novel_quality.inspect',return_value={'fixture':True}):
            for _ in range(30):
                for j in novel.all_jobs(novel.require(self.p['id'])):
                    if j['kind']=='video' and j['status']=='queued':
                        storage.update_job(j['id'],status='succeeded',result={'text':'','assets':[]})
                self.tick()
                if self.p['phase']=='video_review':break
            self.assertEqual(self.p['phase'],'video_review')
            self.assertEqual(self.p['films'],{})
            self.assertFalse(self.p.get('final_user_approved'))

    def test_script_revision_and_targeted_image_repair_with_neighbor_recheck(self):
        self.create();self.command('start');failed=set()
        def fail(key,it):
            match=it['kind']=='script' or it['kind']=='frame' and it['shot']['id']=='s2'
            tag=it['kind']
            if match and tag not in failed:failed.add(tag);return True
            return False
        p=self.run_to('videos',fail)
        self.assertFalse(p['paused'],p['error']);self.assertEqual(p['phase'],'videos')
        self.assertEqual(p['automation_state']['repairs'],{'script:e1':1,'shot:e1:s2':1})
        self.assertEqual(len(p['slots']['shot:e1:s2']['attempts']),1)
        self.assertEqual(len(p['slots']['shot:e1:s1']['attempts']),0)
        reviews=[r for r in p['automation_status']['reports'] if r['target']=='shot:e1:s1' and r['kind']=='motion']
        self.assertEqual(len(reviews),2) # only neighbors are invalidated by replacing s2
        self.assertEqual(p['production_state']['approved'],24)

    def test_failed_review_caps_pause_without_video_or_repeat_spend(self):
        self.create(script_revisions=0);self.command('start')
        p=self.run_to('videos',lambda k,it:it['kind']=='script')
        self.assertTrue(p['paused']);self.assertIn('返修已达上限',p['error'])
        used=p['requests_used'];self.command('resume');self.tick()
        self.assertTrue(self.p['paused']);self.assertEqual(self.p['requests_used'],used)
        self.assertFalse(any(j['kind'] in ('image','video') for j in self.p['jobs']))
        self.command('auto_manual');self.assertEqual(self.p['phase'],'script_review')
        self.assertFalse(self.p['automation']['enabled']);self.assertTrue(self.p['needs_audit'])

    def test_no_vision_rejected_without_mutating_existing_draft(self):
        self.create();before=novel.require(self.p['id'])
        roles=copy.deepcopy(self.roles);roles['costume']['provider_id']=''
        self.api('/api/novels/save',{**self.p,'team_mode':True,'ai_team_roles':roles},400)
        self.assertEqual(novel.require(self.p['id']),before)

    def test_budget_and_upstream_failure_do_not_trigger_new_jobs(self):
        self.create();self.command('start');self.tick()
        job=self.p['slots']['outline']['job_id'];storage.update_job(job,status='failed',error='余额不足')
        self.tick();used=self.p['requests_used'];self.command('resume');self.tick()
        self.assertTrue(self.p['paused']);self.assertEqual(self.p['requests_used'],used)
        self.command('retry',slot='outline');self.command('set_limit',request_limit=10)
        p=self.run_to('videos');self.assertTrue(p['paused']);self.assertLessEqual(p['requests_used'],10)
        self.assertFalse(any(j['kind']=='video' for j in p['jobs']))

    def test_incomplete_report_is_repaired_twice_then_pauses(self):
        self.create();self.command('start');self.run_to('auto_script_review')
        for i in range(3):
            self.tick();key=next(k for k in self.p['slots'] if k.startswith('auto:script:'))
            storage.update_job(self.p['slots'][key]['job_id'],status='succeeded',result={'text':'{"verdict":"pass"}','assets':[]})
            self.tick()
        self.assertTrue(self.p['paused']);self.assertIn('结构修复已达2次',self.p['error'])
        self.assertFalse(any(j['kind']=='image' for j in self.p['jobs']))

    def test_stale_pixels_cannot_allow_video(self):
        self.create();self.command('start');self.run_to('videos')
        p=novel.require(self.p['id']);p['images']['shot:e1:s2']=self.image('green')['id'];novel.persist(p)
        self.tick();self.assertTrue(self.p['paused']);self.assertIn('分镜与连续性尚未通过',self.p['error'])
        self.assertFalse(any(j['kind']=='video' for j in self.p['jobs']))

    def test_changed_contract_and_pending_issue_block_all_video_submissions(self):
        self.create();self.command('start');self.run_to('videos')
        p=novel.require(self.p['id']);p['production_book']['contracts']['shot:e1:s24']['end']='改了终点'
        novel.persist(p);self.tick()
        self.assertTrue(self.p['paused']);self.assertIn('独立审查',self.p['error'])
        self.assertFalse(any(j['kind']=='video' for j in self.p['jobs']))

    def test_asset_repair_only_replaces_failed_asset(self):
        self.create();self.command('start');failed=[]
        def fail(k,it):
            if it['kind']=='asset' and it['asset']['id']=='a1' and not failed:
                failed.append(k);return True
            return False
        p=self.run_to('shots',fail)
        self.assertFalse(p['paused'],p['error']);self.assertEqual(p['phase'],'shots')
        self.assertEqual(len(p['slots']['asset:a1']['attempts']),1)
        self.assertFalse(p['slots']['asset:a2']['attempts'])
        self.assertEqual(p['locked_assets']['a1'],p['images']['asset:a1'])


if __name__=='__main__':unittest.main()
