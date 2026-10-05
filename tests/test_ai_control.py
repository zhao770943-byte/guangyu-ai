"""Role routing and native image payloads in an isolated DB; no paid calls."""
import copy
import unittest
import ai_control as team
import novel_studio as novel
import providers
import storage
import server
import test_novel_studio as fixture


class TeamTests(unittest.TestCase):
    setUp = fixture.NovelTests.setUp
    api = fixture.NovelTests.api
    image = fixture.NovelTests.image
    create = fixture.NovelTests.create
    get = fixture.NovelTests.get
    command = fixture.NovelTests.command
    tick = fixture.NovelTests.tick
    outline = fixture.NovelTests.outline
    script = fixture.NovelTests.script
    finish_text = fixture.NovelTests.finish_text
    finish_image = fixture.NovelTests.finish_image
    finish_current_images = fixture.NovelTests.finish_current_images

    def setup_team(self):
        self.create()
        config = team.config()
        self.connections = {}
        for role in team.ROLES:
            p = {**self.chat, 'id':storage.uid(), 'name':role, 'model':'fixture-'+role}
            storage.put('providers', p)
            self.connections[role] = p
            config['roles'][role] = {'provider_id':p['id'], 'vision':role=='costume', 'note':''}
        self.api('/api/ai-control/save', config)
        ref = self.image()
        self.ref = ref['id']
        self.p = self.api('/api/novels/save', {**self.p, 'team_mode':True, 'references':[{'upload_id':self.ref,'scope':'asset','target':'林青'}]})

    def test_six_role_pipeline_routes_and_visual_review_gate(self):
        self.setup_team();self.command('start');self.tick()
        self.assertEqual(self.p['jobs'][-1]['provider_id'],self.connections['director']['id'])
        self.finish_text('outline',self.outline());self.tick();self.tick()
        self.finish_text('script:e1',self.script());self.tick()
        self.assertEqual(self.p['phase'],'lighting');self.tick()
        self.finish_text('light:e1',self.script());self.tick();self.tick()
        self.finish_text('audit:e1',self.script());self.tick()
        self.assertEqual(self.p['phase'],'script_review')
        self.command('approve_script');self.tick()
        img = storage.get('jobs',self.p['slots']['asset:a1']['job_id'])
        other = storage.get('jobs',self.p['slots']['asset:a2']['job_id'])
        self.assertEqual(img['input_assets']['references'],[self.ref])
        self.assertFalse(other['input_assets']['references'])
        self.finish_current_images();self.tick();self.assertEqual(self.p['phase'],'visual_review');self.tick()
        look = storage.get('jobs',self.p['slots']['look:a1']['job_id'])
        self.assertEqual(look['provider_id'],self.connections['costume']['id'])
        self.assertEqual(look['vision_upload_ids'][0],self.ref)
        self.finish_text('look:a1',{'verdict':'revise','issues':'衣领偏差','suggestion':'保持原稿'})
        self.finish_text('look:a2',{'verdict':'pass','issues':'','suggestion':'人工确认'})
        self.tick();self.assertEqual(self.p['phase'],'asset_review')
        count=self.mock_dispatch.call_count;self.tick();self.assertEqual(count,self.mock_dispatch.call_count)
        self.assertEqual(self.p['visual_reviews']['a1']['verdict'],'revise')
        self.command('approve_assets')
        for _ in range(12):
            self.tick();self.finish_current_images()
            if self.p['phase']=='video_audit':break
        self.tick()
        motion=storage.get('jobs',self.p['slots']['motion:e1']['job_id'])
        self.assertEqual(motion['provider_id'],self.connections['camera']['id'])
        for role in ('director','writer','lighting','supervisor','costume','camera'):
            self.assertTrue(any(j.get('ai_role')==role and j['provider_id']==self.connections[role]['id'] for j in self.p['jobs']))

    def test_native_vision_payloads_preserve_durable_messages(self):
        self.create();a=self.image();job={'prompt':'审图','messages':[{'role':'system','content':'审图要求'},{'role':'user','content':'检查角色'}]}
        for protocol in ('openai_chat','openai_responses','anthropic','gemini'):
            p={**self.chat,'protocol':protocol};j=copy.deepcopy(job)
            team.attach_vision(p,j,[a['id']]);first=providers.build(p,j)[1];second=providers.build(p,j)[1]
            self.assertEqual(first,second);self.assertEqual(j['messages'],job['messages'])
            if protocol=='gemini':self.assertIn('inlineData',first['contents'][-1]['parts'][-1])
            elif protocol=='anthropic':self.assertEqual(first['messages'][-1]['content'][-1]['source']['media_type'],'image/png')
            elif protocol=='openai_responses':self.assertEqual(first['input'][-1]['content'][-1]['type'],'input_image')
            else:self.assertTrue(first['messages'][-1]['content'][-1]['image_url']['url'].startswith('data:image/png;'))
        with self.assertRaises(ValueError):team.attach_vision({**self.chat,'protocol':'custom'},job,[a['id']])

    def test_role_snapshot_and_connection_change_guard(self):
        self.setup_team();p=novel.require(self.p['id']);old=p['ai_team']['writer']['provider_id']
        config=team.config();config['roles']['writer']['provider_id']=self.chat['id'];team.save(config)
        self.assertEqual(team.resolve(p,'writer')['id'],old)
        connection=self.connections['writer'];connection['model']='changed';storage.put('providers',connection)
        with self.assertRaises(ValueError):team.resolve(p,'writer')
        self.assertNotIn('signature',self.get()['ai_team']['writer'])

    def test_references_validation_and_wrong_role_type(self):
        self.create();a=self.image()
        with self.assertRaises(ValueError):team.references([{'upload_id':a['id'],'scope':'asset','target':''}])
        with self.assertRaises(ValueError):team.references([{'upload_id':a['id'],'scope':'style','target':''}]*9)
        config=team.config();config['roles']['writer']['provider_id']=self.provider['id']
        self.api('/api/ai-control/save',config,400)
        self.api('/api/ai-control/save',{'version':99,'roles':team.config()['roles']},400)

    def test_unconfigured_vision_keeps_manual_gate(self):
        self.create();self.p=self.api('/api/novels/save',{**self.p,'team_mode':True})
        p=novel.require(self.p['id']);p['phase']='assets';novel.advance(p)
        self.assertEqual(p['phase'],'asset_review')
        self.assertEqual(p['ai_team']['director']['provider_id'],self.chat['id'])

    def test_lighting_cannot_change_approved_plot_fields(self):
        self.setup_team();p=novel.require(self.p['id']);p['plan']=self.outline();episode=p['plan']['episodes'][0];episode.update(self.script())
        original=copy.deepcopy(episode);bad=self.script();bad['shots'][0]['seconds']=14;bad['shots'][1]['seconds']=16
        import json
        slot={'repairs':2};job={'id':storage.uid(),'result':{'text':json.dumps(bad)}}
        with self.assertRaises(ValueError):novel.consume(p,'light:e1',episode,slot,job)
        self.assertEqual(episode,original)


if __name__=='__main__':unittest.main()
