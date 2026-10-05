"""Isolated HTTP + durable scheduler acceptance. No paid generation."""
import copy
import json
import unittest
from unittest.mock import patch
import test_visual_studio
import novel_schema
import novel_studio as novel
import server
import storage
import work_library


class NovelTests(unittest.TestCase):
    setUp = test_visual_studio.VisualStudioTests.setUp
    api = test_visual_studio.VisualStudioTests.api
    image = test_visual_studio.VisualStudioTests.image
    finish_image = test_visual_studio.VisualStudioTests.finish

    def create(self):
        self.chat = {**self.provider, 'id': storage.uid(), 'kind': 'chat', 'protocol': 'openai_chat', 'model': 'fixture-text'}
        self.video = {**self.provider, 'id': storage.uid(), 'kind': 'video', 'protocol': 'ark_video', 'platform': 'ark', 'model': 'doubao-seedance-2-0-260128'}
        storage.put('providers', self.chat)
        storage.put('providers', self.video)
        self.p = self.api('/api/novels/save', {'title': '钟楼来信', 'source': '林青走入古老钟楼，拿起桌上的信。', 'style': '写实',
                       'chat_provider_id': self.chat['id'], 'image_provider_id': self.provider['id'], 'video_provider_id': self.video['id'],
                       'ratio': '9:16', 'concurrency': 2, 'request_limit': 160})
        return self.p

    def get(self):
        self.p = self.api('/api/novels?id='+self.p['id'])
        return self.p

    def command(self, action, **extra):
        self.get()
        self.p = self.api('/api/novels/command', {'id': self.p['id'], 'version': self.p['version'], 'request_id': storage.uid(), 'action': action, **extra})
        return self.p

    def tick(self):
        novel.tick(server.create_job, server.dispatch, server.ACTIVE, server.ACTIVE_LOCK)
        return self.get()

    def outline(self):
        return {'summary': '林青在钟楼发现来信', 'style': '写实', 'assets': [
            {'id': 'a1', 'kind': 'character', 'name': '林青', 'aliases': '', 'evidence': '林青', 'description': '青衣女子', 'prompt': '青衣女子设定'},
            {'id': 'a2', 'kind': 'scene', 'name': '钟楼', 'evidence': '古老钟楼', 'description': '木制钟楼', 'prompt': '钟楼内部'}],
            'episodes': [{'id': 'e1', 'title': '来信', 'synopsis': '进入钟楼并发现来信', 'source_excerpt': '林青走入古老钟楼'}]}

    def script(self):
        return {'shots': [{'id': 's'+str(i), 'title': '镜头'+str(i), 'seconds': 15, 'asset_ids': ['a1', 'a2'],
                          'action': '缓缓走近', 'dialogue': '', 'camera': '中景平移', 'image_prompt': '林青在钟楼内',
                          'video_prompt': '林青缓缓走近，镜头平稳'} for i in range(1, 9)], 'changes': '已核对身份与服装'}

    def finish_text(self, key, value):
        identity = self.get()['slots'][key]['job_id']
        storage.update_job(identity, status='succeeded', result={'text': value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), 'assets': []})

    def reviewed(self):
        self.create();self.command('start');self.tick()
        self.finish_text('outline', self.outline());self.tick();self.tick()
        self.finish_text('script:e1', self.script());self.tick();self.tick()
        self.finish_text('audit:e1', self.script());self.tick()
        self.assertEqual(self.p['phase'], 'script_review')
        return self.p

    def finish_current_images(self):
        for slot in self.get()['slots'].values():
            j = storage.get('jobs', slot.get('job_id'))
            if j and j['kind'] == 'image' and j['status'] == 'queued':
                self.finish_image(j['id'])

    def test_named_character_in_first_frame_cannot_lose_reference(self):
        plan={'assets':[{'id':'a1','kind':'character','name':'萧炎','aliases':''},{'id':'a2','kind':'character','name':'萧薰儿','aliases':'薰儿、熏儿'},{'id':'a4','kind':'scene','name':'广场'}]}
        shot={'asset_ids':['a1','a4'],'image_prompt':'萧炎背向出口，薰儿站在身后。'}
        self.assertEqual(novel.referenced_characters(plan,shot),['a1','a4','a2'])
        self.assertEqual(shot['asset_ids'],['a1','a4'])
        shot['image_prompt']='萧炎独自离场。'
        self.assertEqual(novel.referenced_characters(plan,shot),['a1','a4'])

    def test_visual_list_output_preserves_revise_without_extra_request(self):
        p={'images':{'asset:a1':'fixture-upload'},'history':[]}
        item={'id':'a1'};slot={'invalid':True,'repairs':2}
        job={'id':'fixture-job','result':{'text':json.dumps({'verdict':'revise','issues':['Face mismatch','Wrong reference'],'suggestion':['Review manually']})}}
        novel.consume(p,'look:a1',item,slot,job)
        self.assertTrue(slot['done']);self.assertFalse(slot['invalid'])
        self.assertEqual(p['visual_reviews']['a1']['verdict'],'revise')
        self.assertEqual(p['visual_reviews']['a1']['issues'],'Face mismatch\nWrong reference')
        job['result']['text']=json.dumps({'verdict':'pass','issues':[{'unsupported':'object'}],'suggestion':''})
        with self.assertRaises(ValueError):novel.consume(p,'look:a1',item,{'repairs':2},job)

    def test_candidate_reuse_counts_once_and_rejects_cross_project(self):
        self.reviewed()
        job = {'id':storage.uid(), 'created_at':storage.now(), 'kind':'image', 'status':'succeeded', 'collection_id':'novel:'+self.p['id']}
        storage.put('jobs',job)
        body = {'id':self.p['id'], 'version':self.p['version'], 'asset_id':'a1', 'job_id':job['id']}
        before = self.p['requests_used']
        with patch.object(novel.storyboards,'image_from_job',return_value={'id':'fixture-upload'}) as image:
            result = novel.replace_asset(body)
            self.assertEqual(result['requests_used'],before+1)
            self.assertTrue(result['slots']['asset:a1']['done'])
            body['version']=result['version']
            again=novel.replace_asset(body)
            self.assertEqual(again['requests_used'],before+1)
            self.assertEqual(image.call_count,1)
            body['asset_id']='a2'
            with self.assertRaises(ValueError):novel.replace_asset(body)
            job['collection_id']='novel:'+storage.uid();storage.put('jobs',job)
            with self.assertRaises(ValueError):novel.replace_asset(body)

    def test_storyboard_review_blocks_video_and_is_idempotent(self):
        self.reviewed()
        p = novel.require(self.p['id'])
        p['review_storyboards'] = True
        novel.persist(p)
        self.command('approve_script'); self.tick(); self.finish_current_images(); self.tick()
        self.command('approve_assets')
        for _ in range(12):
            self.tick(); self.finish_current_images()
            if self.p['phase'] == 'shot_review': break
        self.assertEqual(self.p['phase'], 'shot_review')
        count = self.mock_dispatch.call_count
        for _ in range(3): self.tick()
        self.assertEqual(self.mock_dispatch.call_count, count)
        self.assertFalse(any(j['kind'] == 'video' for j in storage.items('jobs', -1)))
        original = self.p['slots']['shot:e1:s1']['job_id']
        self.command('retry', slot='shot:e1:s1')
        self.assertEqual(self.p['phase'], 'shots')
        self.tick(); self.finish_current_images(); self.tick()
        self.assertEqual(self.p['phase'], 'shot_review')
        self.assertIn(original, self.p['slots']['shot:e1:s1']['attempts'])
        body = {'id':self.p['id'], 'version':self.p['version'], 'request_id':storage.uid(), 'action':'approve_shots'}
        first = self.api('/api/novels/command', body)
        second = self.api('/api/novels/command', body)
        self.assertEqual(first['version'], second['version'])
        self.assertEqual(first['phase'], 'video_audit')

    def test_full_pipeline_two_gates_and_exact_120_second_films(self):
        self.reviewed()
        count = self.mock_dispatch.call_count
        for _ in range(3):self.tick()
        self.assertEqual(self.mock_dispatch.call_count, count)
        self.assertTrue(all(j['kind'] == 'chat' for j in storage.items('jobs', -1)))
        self.command('approve_script');self.tick();self.finish_current_images();self.tick()
        self.assertEqual(self.p['phase'], 'asset_review')
        self.assertEqual(len(self.p['images']), 2)
        original = self.p['images']['asset:a1'];replacement = self.image('green')
        self.p = self.api('/api/novels/asset', {'id': self.p['id'], 'version': self.p['version'], 'asset_id': 'a1', 'upload_id': replacement['id']})
        self.command('approve_assets')
        self.assertNotEqual(original, self.p['locked_assets']['a1'])
        for _ in range(12):
            self.tick();self.finish_current_images()
            if self.p['phase'] == 'video_audit':break
        self.assertEqual(self.p['phase'], 'video_audit')
        image_jobs = [j for j in storage.items('jobs', -1) if j.get('novel_slot', '').startswith('shot:')]
        self.assertEqual(len(image_jobs), 8)
        self.assertTrue(all(j['input_assets']['references'][0] == replacement['id'] for j in image_jobs))
        self.tick();self.finish_text('motion:e1', self.script());self.tick()
        for _ in range(12):
            self.tick()
            for j in storage.items('jobs', -1):
                if j['kind'] == 'video' and j['status'] == 'queued':
                    self.assertEqual(j['input_assets']['first_frame'], self.p['images']['shot:'+j['novel_slot'][6:]])
                    storage.update_job(j['id'], status='succeeded', archive_status='saved', result={'text': '', 'assets': [{'type': 'video', 'local': True, 'url': '/media/'+j['id']+'.mp4'}]})
            if self.p['phase'] == 'compose':break
        self.tick()
        film = storage.get('jobs', self.p['films']['e1'])
        self.assertEqual(film['seconds'], 120)
        self.assertEqual(film['film_segments'][-1]['end'], 120)
        self.assertEqual([s['start'] for s in film['film_segments']], list(range(0, 120, 15)))
        storage.update_job(film['id'], status='succeeded', archive_status='saved')
        self.tick();self.assertEqual(self.p['phase'], 'complete')
        self.assertEqual(self.p['requests_used'], 22)
        self.assertFalse(storage.items('conversations'))
        self.assertNotIn('provider_signatures', self.p)
        self.assertTrue(all('provider_snapshot' not in j and 'messages' not in j for j in self.p['jobs']))

    def test_invalid_json_auto_repair_bounded_and_no_media(self):
        self.create();self.command('start');self.tick()
        for _ in range(3):
            self.finish_text('outline', 'broken output');self.tick()
        self.assertTrue(self.p['paused']);self.assertEqual(self.p['requests_used'], 3)
        self.assertIn('自动修复已达2次', self.p['error'])
        self.assertEqual(len(self.p['slots']['outline']['attempts']), 2)
        self.command('retry', slot='outline');self.tick()
        self.assertEqual(self.p['requests_used'], 4)

    def test_time_and_id_validation(self):
        for change in ('seconds', 'refs', 'duplicate'):
            v = self.script()
            if change == 'seconds':v['shots'][0]['seconds'] = 14
            if change == 'refs':v['shots'][0]['asset_ids'] = ['invented']
            if change == 'duplicate':v['shots'][1]['id'] = v['shots'][0]['id']
            with self.assertRaises(ValueError):novel_schema.script(v, self.outline()['assets'], 15)

    def test_idempotent_command_pause_restart_does_not_repost(self):
        self.create()
        body = {'id': self.p['id'], 'version': self.p['version'], 'request_id': storage.uid(), 'action': 'start'}
        self.api('/api/novels/command', body);self.api('/api/novels/command', body);self.tick()
        self.assertEqual(self.mock_dispatch.call_count, 1)
        self.command('pause');self.tick();self.assertEqual(self.mock_dispatch.call_count, 1)
        server.recover();self.command('resume');self.tick()
        self.assertTrue(self.p['paused']);self.assertEqual(self.mock_dispatch.call_count, 1)
        self.assertEqual(self.p['jobs'][0]['status'], 'interrupted')

    def test_manual_edit_requires_new_audit(self):
        p = self.reviewed();plan = copy.deepcopy(p['plan']);plan['episodes'][0]['shots'][0]['video_prompt'] = '从左向右缓慢移动'
        self.p = self.api('/api/novels/edit', {'id': p['id'], 'version': p['version'], 'plan': plan})
        self.api('/api/novels/command', {'id': p['id'], 'version': self.p['version'], 'request_id': storage.uid(), 'action': 'approve_script'}, 400)
        self.command('reaudit');self.tick()
        j = storage.get('jobs', self.p['slots']['audit:e1']['job_id'])
        self.assertIn('从左向右缓慢移动', j['messages'][1]['content'])
        self.finish_text('audit:e1', self.script());self.tick()
        self.assertFalse(self.p['needs_audit'])
        self.command('approve_script');self.assertEqual(self.p['phase'], 'assets')

    def test_failure_pauses_before_other_dispatch_and_retry_is_explicit(self):
        self.reviewed();self.command('approve_script');self.tick()
        keys = list(k for k in self.p['slots'] if k.startswith('asset:'))
        job = storage.get('jobs', self.p['slots'][keys[0]]['job_id'])
        storage.update_job(job['id'], status='failed', error='test provider failure')
        count = self.mock_dispatch.call_count
        self.tick();self.assertTrue(self.p['paused']);self.assertEqual(self.mock_dispatch.call_count, count)
        self.command('retry', slot=keys[0]);self.tick()
        self.assertEqual(self.mock_dispatch.call_count, count+1)
        self.assertEqual(self.p['slots'][keys[0]]['attempts'], [job['id']])

    def test_budget_and_concurrency(self):
        self.reviewed();self.command('approve_script')
        p = novel.require(self.p['id']);p['requests_used'] = 159;storage.put('novel_projects', p)
        self.tick();self.assertEqual(self.p['requests_used'], 160);self.assertTrue(self.p['paused'])
        self.assertEqual(sum(j['kind'] == 'image' for j in self.p['jobs']), 1)
        self.command('resume', request_limit=162);self.tick()
        self.assertEqual(sum(j['kind'] == 'image' for j in self.p['jobs']), 2)
        for _ in range(3):self.tick()
        self.assertEqual(self.p['requests_used'], 161)

    def test_dispatch_exception_has_durable_uncertain_receipt(self):
        self.create();self.command('start')
        with patch.object(server, 'dispatch', side_effect=RuntimeError('fixture')):self.tick()
        self.assertTrue(self.p['paused']);self.assertEqual(self.p['requests_used'], 1)
        self.assertEqual(self.p['jobs'][0]['status'], 'interrupted')
        self.command('resume');self.tick();self.assertEqual(self.p['requests_used'], 1)

    def test_model_changed_blocked_and_deletion_protected(self):
        self.reviewed();self.command('approve_script');self.tick();self.finish_current_images()
        j = next(j for j in self.p['jobs'] if j['kind'] == 'image')
        with self.assertRaises(ValueError):work_library.remove(j['id'])
        self.tick();self.command('approve_assets')
        provider = storage.get('providers', self.provider['id']);provider['model'] = 'different-image';storage.put('providers', provider)
        self.tick();self.assertTrue(self.p['paused']);self.assertIn('接口或参数已变化', self.p['error'])

    def test_admission_rejects_text_only_images_and_unknown_video_duration(self):
        self.create();body = copy.deepcopy(self.p)
        self.provider['model'] = 'dall-e-3';storage.put('providers', self.provider)
        self.api('/api/novels/save', body, 400)
        self.assertEqual(storage.items('jobs'), [])

    def test_two_episodes_have_independent_shot_ids(self):
        self.create()
        p = novel.require(self.p['id']);p['source'] *= 80;storage.put('novel_projects', p)
        self.command('start');self.tick()
        outline = self.outline();outline['episodes'].append({**outline['episodes'][0], 'id': 'e2'})
        self.finish_text('outline', outline);self.tick();self.tick()
        self.assertIn('script:e1', self.p['slots']);self.assertIn('script:e2', self.p['slots'])
        self.assertEqual(len([j for j in self.p['jobs'] if j['status']=='queued']), 2)

    def test_reasoning_wrapper_and_invalid_tail(self):
        answer = json.dumps(self.outline(), ensure_ascii=False)
        self.assertEqual(novel_schema.parse('<think>planning {}</think>\n```json\n'+answer+'\n```'), self.outline())
        for invalid in ('<think>'+answer, '<think>x</think>'+answer+' garbage', '<think>x</think>{"a":NaN}'):
            with self.assertRaises(ValueError):novel_schema.parse(invalid)

    def test_manual_motion_review_requires_current_image_and_preserves_ai_verdict(self):
        self.create()
        image = self.image()
        p = novel.require(self.p['id'])
        p.update(phase='video_audit', paused=True, plan={'assets':[], 'episodes':[{'id':'e1','shots':[{'id':'s1','seconds':5,'video_prompt':'old'}]}]}, images={'shot:e1:s1':image['id']})
        key='visionmotion:e1:s1'
        p['motion_reviews']={key:{'risk':'revise','issues':'model contradiction'}}
        novel.persist(p)
        body={'id':p['id'],'version':p['version'],'request_id':storage.uid(),'action':'review_motion','inspected':True,'slot':key,'image_id':'stale','notes':'actual image inspected','video_prompt':'gentle camera motion'}
        with self.assertRaises(ValueError):novel.command(body, server.ACTIVE, server.ACTIVE_LOCK)
        body['image_id']=image['id']
        result=novel.command(body,server.ACTIVE,server.ACTIVE_LOCK)
        self.assertEqual(result['motion_reviews'][key]['source'],'manual')
        self.assertEqual(result['motion_reviews'][key]['previous_review']['risk'],'revise')
        self.assertTrue(result['slots'][key]['done'])
        self.assertEqual(result['requests_used'],0)

    def test_brief_synopsis_does_not_expand_into_multiple_episodes(self):
        self.create();self.command('start');self.tick()
        value = self.outline();value['episodes'].append({**value['episodes'][0], 'id':'e2'})
        self.finish_text('outline', value);self.tick()
        self.assertEqual(self.p['slots']['outline']['repairs'], 1)
        self.assertFalse(self.p.get('plan'))

    def test_outline_repair_does_not_repeat_invalid_reasoning(self):
        self.create();self.command('start');self.tick()
        self.finish_text('outline', '<think>OLD_PRIVATE_REASONING</think>{bad}');self.tick()
        job = storage.get('jobs', self.p['slots']['outline']['job_id'])
        prompt = job['messages'][1]['content']
        self.assertNotIn('OLD_PRIVATE_REASONING', prompt)
        self.assertIn('episodes数组必须恰好只有1项', prompt)
        self.assertIn('程序校验未通过', prompt)

    def test_local_gpu_video_submission_is_serial(self):
        self.reviewed()
        p=novel.require(self.p['id']);p.update(phase='videos', concurrency=3)
        storage.put('novel_projects', p)
        def prepared(project, key, item, prepare):
            return {'id':storage.uid(), 'kind':'video', 'status':'queued', 'created_at':storage.now(),
                    'novel_slot':key, 'novel_project_id':project['id']}
        with patch.object(novel, 'provider', return_value={'protocol':'comfy_h3'}), patch.object(novel, 'prepare_task', side_effect=prepared):
            self.tick();self.tick()
        self.assertEqual(len([j for j in self.p['jobs'] if j['kind']=='video']), 1)

    def test_pause_reconciles_completed_asset_without_dispatching_more(self):
        self.reviewed();self.command('approve_script')
        p=novel.require(self.p['id']);p['concurrency']=1;storage.put('novel_projects',p)
        self.tick();self.command('pause')
        count=self.mock_dispatch.call_count
        self.finish_current_images();self.tick()
        self.assertTrue(self.p['paused'])
        self.assertEqual(self.p['phase'],'assets')
        self.assertEqual(len(self.p['images']),1)
        self.assertEqual(self.mock_dispatch.call_count,count)

    def test_video_audit_cannot_rewrite_approved_shot(self):
        self.reviewed()
        p = novel.require(self.p['id']);p['phase'] = 'video_audit';storage.put('novel_projects', p)
        self.tick()
        changed = self.script();changed['shots'][0]['image_prompt'] = 'Changed identity'
        self.finish_text('motion:e1', changed);self.tick()
        self.assertEqual(self.p['slots']['motion:e1']['repairs'], 1)
        self.assertNotEqual(self.p['plan']['episodes'][0]['shots'][0]['image_prompt'], 'Changed identity')
        fixed = self.script();fixed['shots'][0]['video_prompt'] = '保持身份，向右行走'
        self.finish_text('motion:e1', fixed);self.tick()
        self.assertEqual(self.p['phase'], 'videos')
        self.assertEqual(self.p['plan']['episodes'][0]['shots'][0]['video_prompt'], '保持身份，向右行走')

    def test_real_local_composition_is_120_seconds(self):
        import av
        import film_compose
        from test_film_batch import clip
        self.create()
        source = storage.DATA/'media'/(storage.uid()+'.mp4')
        clip(source, 'navy', seconds=15, rate=12, sound=True)
        segments = []
        for i in range(8):
            j = {'id': storage.uid(), 'created_at': storage.now(), 'status': 'succeeded', 'kind': 'video',
                 'result': {'assets': [{'type': 'video', 'local': True, 'url': '/media/'+source.name}]}}
            storage.put('jobs', j)
            segments.append({'job_id': j['id'], 'start': i*15, 'end': (i+1)*15})
        parent = {'id': storage.uid(), 'seconds': 120, 'film_segments': segments}
        result = film_compose.compose(parent)
        with av.open(str(work_library.local_path(result['assets'][0]['url']))) as container:
            self.assertAlmostEqual(container.duration/1000000, 120, places=1)
            self.assertEqual(container.streams.video[0].frames, 3600)
            self.assertTrue(container.streams.audio)


if __name__ == '__main__':unittest.main()
