"""Dialogue loss, continuity snapshots and model-aware quality without paid APIs."""
import copy
import unittest
from unittest.mock import patch
import novel_fidelity as f
import novel_schema
import novel_studio
import novel_automation
import storage
import test_novel_studio
import test_novel_automation


class FidelityTests(unittest.TestCase):
    def setUp(self):
        self.p = {'production_preferences': {'version': 1}, 'source': '林青说：“你终于来了。”对方答：“我一直在等你。”',
                  'plan': {'episodes': [{'id': 'e1'}], 'assets': []}, 'ratio': '16:9'}
        f.bind_outline(self.p, self.p['plan'], {'dialogue_assignments': [
            {'id': 'd1', 'speaker': '林青', 'episode_id': 'e1'}, {'id': 'd2', 'speaker': '沈舟', 'episode_id': 'e1'}]})
        self.shots = [{'id': 's1', 'seconds': 5, 'dialogue_ids': ['d1'], 'dialogue': '林青：你终于来了。'},
                      {'id': 's2', 'seconds': 5, 'dialogue_ids': ['d2'], 'dialogue': '沈舟：我一直在等你。'}]

    def test_missing_assignment_and_unexplained_omission_rejected(self):
        with self.assertRaisesRegex(ValueError, '缺少'):
            f.bind_outline(self.p, self.p['plan'], {'dialogue_assignments': []})
        with self.assertRaises(ValueError):
            f.bind_outline(self.p, self.p['plan'], {'dialogue_omissions': [{'id': 'd1'}, {'id': 'd2'}]})

    def test_shortening_cannot_pass_by_retaining_only_ids(self):
        self.shots[0]['dialogue'] = '林青：来了。'
        with self.assertRaisesRegex(ValueError, '删改或截断'):
            f.validate_script(self.p, {'id': 'e1'}, {'shots': self.shots})

    def test_split_dialogue_and_punctuation_variation_allowed(self):
        self.shots[0]['dialogue'] = '林青：你终于'
        self.shots.insert(1, {'id': 's1b', 'seconds': 2, 'dialogue_ids': ['d1'], 'dialogue': '林青：来了！'})
        f.validate_script(self.p, {'id': 'e1'}, {'shots': self.shots})

    def test_order_and_excessive_speech_rate_blocked(self):
        with self.assertRaisesRegex(ValueError, '次序'):
            f.validate_script(self.p, {'id': 'e1'}, {'shots': list(reversed(self.shots))})
        self.shots[0].update(seconds=2, dialogue='林青：'+ '这段对话不能被快速念完' * 3)
        with self.assertRaisesRegex(ValueError, '自然说完'):
            f.validate_script(self.p, {'id': 'e1'}, {'shots': self.shots})

    def test_native_video_prompt_cannot_drop_spoken_lines(self):
        with self.assertRaisesRegex(ValueError, '实际台词'):
            f.validate_video_dialogue(self.p, self.shots[0], '她很激动地说话', 'native')
        f.validate_video_dialogue(self.p, self.shots[0], '她自然地说：你终于来了！镜头切勿移动。', 'native')
        f.validate_video_dialogue(self.p, self.shots[0], '保留表情，后期配音', 'dub')

    def test_exclusions_have_public_evidence_and_legacy_has_no_gate(self):
        p={**self.p, 'source':'他望着“钟楼”说：“我回来了。”', 'plan':{'episodes':[{'id':'e1'}]}}
        f.bind_outline(p, p['plan'], {'dialogue_assignments':[{'id':'d2','speaker':'林青','episode_id':'e1'}],
            'dialogue_omissions':[{'id':'d1','reason':'建筑名称引语，不是人物说出的台词'}]})
        r=f.report(p)
        self.assertEqual(r['retained'],1);self.assertIn('建筑',r['omissions'][0]['reason'])
        f.validate_script({}, {'id':'e1'}, {'shots':[]})

    def test_high_quality_respects_alias_default_and_known_sizes(self):
        v={'kind':'image','protocol':'openai_image','model':'gpt-image-2'}
        size, params=f.image_settings(self.p,v,'1536x864',{})
        self.assertEqual(size,'2048x1152');self.assertEqual(params['quality'],'high')
        v.update(model='gpt-image-2.5-sunburst新',base_url='https://www.weijinapi.top/v1')
        self.assertEqual(f.image_settings(self.p,v,'auto',{}),('auto',{}))
        self.assertEqual(f.checks(self.p,'asset',('identity',)),('identity','clarity'))
        self.assertEqual(f.checks({},'asset',('identity',)),('identity',))

    def test_inheritance_uses_locked_pixels_no_fake_approval_and_invalidates_edits(self):
        asset={'id':'a1','kind':'character','name':'林青','description':'青衣','prompt':'清楚的人物设定'}
        old=copy.deepcopy(asset);old['id']='old1'
        p={'continuity_snapshot':{'project_id':'prior','version':3,'assets':[{'asset':old,'upload_id':'original'}],
             'voices':[{'asset_id':'old1','voice':'accepted','audio_job_id':'audio'}]},
           'plan':{'assets':[asset]},'slots':{},'images':{},'locked_assets':{}}
        with patch.object(f.uploads,'get',return_value={}):f.inherit_assets(p)
        self.assertEqual(p['images']['asset:a1'],'original');self.assertTrue(p['slots']['asset:a1']['done'])
        self.assertFalse(p['locked_assets']);self.assertNotIn('storyboards',p['production_book'])
        self.assertEqual(p['production_book']['voices'][0]['asset_id'],'a1')
        self.assertEqual(old['id'],'old1')
        plan=copy.deepcopy(p['plan']);plan['assets'][0]['description']='红衣'
        f.invalidate_changed_reuse(p,plan)
        self.assertFalse(p['slots']);self.assertFalse(p['images'])


class FidelityIntegrationTests(unittest.TestCase):
    setUp=test_novel_studio.NovelTests.setUp
    api=test_novel_studio.NovelTests.api

    def test_saved_rule_reaches_director_writer_and_local_script_gate(self):
        p=test_novel_studio.NovelTests.create(self)
        p=self.api('/api/novels/save',{**p,'source':'林青说：“你终于来了。”','production_preferences':{'version':1}})
        raw=novel_studio.require(p['id'])
        instruction,data=novel_studio.llm_input(raw,'outline',None)
        self.assertIn('dialogue_assignments',instruction)
        self.assertEqual(data['source_dialogue'][0]['text'],'你终于来了。')
        plan=test_novel_studio.NovelTests.outline(self)
        plan['dialogue_assignments']=[{'id':'d1','speaker':'林青','episode_id':'e1'}]
        out=novel_schema.outline(plan);f.bind_outline(raw,out,plan);raw['plan']=out
        instruction,data=novel_studio.llm_input(raw,'script:e1',out['episodes'][0])
        self.assertEqual(data['shot_target'],30);self.assertIn('逐句保留',instruction)
        self.assertEqual(data['required_dialogue'][0]['id'],'d1')
        value=test_novel_studio.NovelTests.script(self)
        slot={'repairs':2};job={'id':'fixture','result':{'text':__import__('json').dumps(value)}}
        with self.assertRaisesRegex(ValueError,'缺少原文对白'):
            novel_studio.consume(raw,'script:e1',out['episodes'][0],slot,job)
        self.assertNotIn('shots',out['episodes'][0])

    def test_changed_source_version_rejected_without_writing_draft(self):
        original=test_novel_studio.NovelTests.create(self)
        before=copy.deepcopy(storage.get('novel_projects',original['id']))
        body={**original,'id':None,'production_preferences':{'version':1},'continuity_project_id':original['id'],
              'continuity_source_version':original['version']-1}
        with self.assertRaisesRegex(ValueError,'版本已更新'):novel_studio.save(body)
        self.assertEqual(storage.get('novel_projects',original['id']),before)
        self.assertEqual(len(storage.items('novel_projects',-1)),1)

    def test_inherited_asset_is_free_to_adopt_and_can_be_redrawn(self):
        import json
        import threading
        p=test_novel_studio.NovelTests.create(self)
        old=novel_studio.require(p['id']);old['plan']=test_novel_studio.NovelTests.outline(self)
        image=test_novel_studio.NovelTests.image(self)
        old.update(locked_assets={'a1':image['id']},phase='complete')
        novel_studio.persist(old)
        child=novel_studio.save({**p,'id':None,'title':'续作','production_preferences':{'version':1},
            'continuity_project_id':old['id'],'continuity_source_version':old['version']})
        raw=novel_studio.require(child['id']);raw['slots']['outline']={'repairs':0,'attempts':[]};slot=raw['slots']['outline']
        novel_studio.consume(raw,'outline',None,slot,{'id':'fixture','result':{'text':json.dumps(test_novel_studio.NovelTests.outline(self))}})
        self.assertTrue(raw['slots']['outline']['done'])
        self.assertEqual(raw['images']['asset:a1'],image['id']);self.assertEqual(raw['requests_used'],0)
        raw.update(phase='asset_review');novel_studio.persist(raw)
        result=novel_studio.command({'id':raw['id'],'version':raw['version'],'request_id':storage.uid(),'action':'retry','slot':'asset:a1'},set(),threading.RLock())
        self.assertEqual(result['phase'],'assets');self.assertFalse(result['slots']['asset:a1']['done'])
        self.assertEqual(result['images']['asset:a1'],image['id'])
        self.assertEqual(storage.get('novel_projects',old['id']),old)


class FidelityAutomationTests(unittest.TestCase):
    setUp = test_novel_automation.AutomationTests.setUp
    api = test_novel_automation.AutomationTests.api
    image = test_novel_automation.AutomationTests.image
    finish_image = test_novel_automation.AutomationTests.finish_image
    get = test_novel_automation.AutomationTests.get
    command = test_novel_automation.AutomationTests.command
    tick = test_novel_automation.AutomationTests.tick
    run_to = test_novel_automation.AutomationTests.run_to
    finish_pending = test_novel_automation.AutomationTests.finish_pending

    def outline(self):
        value = test_novel_studio.NovelTests.outline(self)
        value['dialogue_assignments'] = [{'id':'d1','speaker':'林青','episode_id':'e1'}]
        return value

    def script(self):
        value = test_novel_automation.AutomationTests.script(self)
        for shot in value['shots']:
            shot['dialogue_ids'] = []
        value['shots'][0].update(dialogue_ids=['d1'], dialogue='林青：你终于来了。', video_prompt='林青自然地说：你终于来了。')
        return value

    def report(self, kind, failed=False):
        value = test_novel_automation.AutomationTests.report(self, kind, failed)
        if kind in ('asset', 'frame'):
            value['checks']['clarity'] = not failed
            value['evidence']['clarity'] = '测试图片边缘与主体可辨，隔离模拟报告'
        return value

    def test_new_policy_pipeline_preserves_dialogue_and_requires_clarity(self):
        test_novel_automation.AutomationTests.create(self)
        self.p = self.api('/api/novels/save', {**self.p,'source':'林青说：“你终于来了。”','production_preferences':{'version':1}})
        self.command('start');p=self.run_to('videos')
        self.assertFalse(p['paused'],p['error'])
        self.assertEqual(p['plan']['episodes'][0]['shots'][0]['dialogue'],'林青：你终于来了。')
        reports = p['automation_status']['reports']
        self.assertTrue(all(r['checks']['clarity'] for r in reports if r['kind'] in ('asset','frame')))
        self.assertFalse(any(j['kind']=='video' for j in p['jobs']))
        self.tick()
        self.assertTrue(any(j['kind']=='video' for j in self.p['jobs']))


if __name__ == '__main__':unittest.main()
