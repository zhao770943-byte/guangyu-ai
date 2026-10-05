"""Production facts and audio validation in isolated storage. No paid requests."""
import copy
import unittest
import storage
import novel_studio as novel
import production_book as book
import production_readiness as flow
import novel_fidelity as fidelity
import test_production_book


class ProductionFlowTests(unittest.TestCase):
    setUp = test_production_book.ProductionBookTests.setUp
    api = test_production_book.ProductionBookTests.api
    image = test_production_book.ProductionBookTests.image
    create = test_production_book.ProductionBookTests.create
    outline = test_production_book.ProductionBookTests.outline
    script = test_production_book.ProductionBookTests.script
    fixture = test_production_book.ProductionBookTests.fixture

    def audio(self, **extra):
        identity=storage.uid();url='/media/'+identity+'.mp3'
        (storage.DATA/url.lstrip('/')).write_bytes(b'isolated-audio-reference')
        job={'id':identity,'created_at':storage.now(),'kind':'audio','status':'succeeded','result':{'assets':[{'type':'audio','local':True,'url':url}]},**extra}
        storage.put('jobs',job);return job

    def test_readiness_is_read_only_and_does_not_count_failed_old_attempts(self):
        p=self.fixture();old={'id':storage.uid(),'kind':'image','status':'failed','created_at':storage.now()};new={**old,'id':storage.uid(),'status':'succeeded'}
        storage.put('jobs',old);storage.put('jobs',new)
        p['slots']['shot:e1:s1']={'job_id':new['id'],'attempts':[old['id'],new['id']],'done':True}
        before=copy.deepcopy(p);r=novel.public(p)['readiness']
        self.assertEqual(r['current_failed'],0);self.assertEqual(r['totals']['images'],8)
        self.assertEqual(p,before);self.mock_dispatch.assert_not_called()

    def test_episode_time_resets_and_insufficient_pixels_are_not_approval(self):
        p=self.fixture();second=copy.deepcopy(p['plan']['episodes'][0]);second['id']='e2';p['plan']['episodes'].append(second)
        r=novel.public(p)['readiness'];self.assertEqual(r['shots'][8]['start'],0);self.assertEqual(r['planned_seconds'],240)
        self.assertTrue(any('720' in n for n in r['shots'][0]['notes']))
        self.assertEqual(r['stages'][2]['done'],0)
        self.assertIn('缺少分镜图',r['shots'][8]['notes'])

    def test_legacy_film_is_not_called_missing_or_automatically_reapproved(self):
        p=self.fixture();p['production_book']['enabled']=False;p['phase']='complete'
        (storage.DATA/'media'/'missing.mp4').write_bytes(b'file-presence-only')
        job={'id':storage.uid(),'created_at':storage.now(),'kind':'video','status':'succeeded','seconds':141,'result':{'assets':[{'type':'video','url':'/media/missing.mp4','duration_seconds':141}]}}
        storage.put('jobs',job);p['films']={'e1':job['id']}
        r=novel.public(p)['readiness'];self.assertTrue(r['legacy']);self.assertEqual(r['planned_seconds'],120);self.assertEqual(r['film_seconds'],141)
        self.assertEqual(r['tasks'][0]['tab'],'delivery');self.assertFalse(any(t['title']=='检查当前分镜' for t in r['tasks']))
        self.assertEqual(r['stages'][2]['status'],'legacy')

    def test_saved_missing_audio_is_visible_but_cannot_be_saved_as_valid(self):
        p=self.fixture();j=self.audio();body={'action':'studio_sound','voices':[{'asset_id':'a1','voice':'自然声线','audio_job_id':j['id']}],'mix_notes':'连续环境底声'}
        book.apply(p,body);self.assertTrue(novel.public(p)['readiness']['voices'][0]['available'])
        storage.update_job(j['id'],work_deleted_at=storage.now());before=copy.deepcopy(p)
        self.assertFalse(novel.public(p)['readiness']['voices'][0]['available'])
        with self.assertRaisesRegex(ValueError,'未删除'):book.apply(p,body)
        self.assertEqual(p,before);self.mock_dispatch.assert_not_called()

    def test_remote_missing_and_path_escape_audio_are_rejected(self):
        for url in ['https://example.test/clip.mp3','/media/../secret.mp3','/media/missing.mp3']:
            j=self.audio(result={'assets':[{'type':'audio','url':url}]})
            self.assertIsNone(flow.audio_reference(j['id']))

    def test_successful_video_is_not_five_dimension_acceptance(self):
        p=self.fixture();p['review_standard']='five_dimensions';j={'id':storage.uid(),'created_at':storage.now(),'kind':'video','status':'succeeded','result':{'assets':[{'type':'video','url':'/media/fixture.mp4'}]}}
        (storage.DATA/'media'/'fixture.mp4').write_bytes(b'file-presence-only')
        storage.put('jobs',j);p['slots']['video:e1:s1']={'job_id':j['id']};p['video_reviews']={'video:e1:s1':{'job_id':j['id']}}
        r=novel.public(p)['readiness'];self.assertEqual(r['totals']['videos'],1);self.assertEqual(r['totals']['reviewed'],0)
        self.assertTrue(any(t['tab']=='tasks' for t in r['tasks']))

    def test_missing_film_file_is_reported_and_not_counted(self):
        p=self.fixture();j={'id':storage.uid(),'created_at':storage.now(),'kind':'video','status':'succeeded','result':{'assets':[{'type':'video','url':'/media/absent.mp4','duration_seconds':120}]}}
        storage.put('jobs',j);p['films']={'e1':j['id']}
        r=novel.public(p)['readiness'];self.assertEqual(r['film_seconds'],0)
        self.assertTrue(any(t['title']=='检查成片文件' for t in r['tasks']))

    def test_public_api_and_static_resources(self):
        p=self.fixture();novel.persist(p);r=self.api('/api/novels?id='+p['id'])
        self.assertEqual(len(r['readiness']['shots']),8)
        import urllib.request
        for path in ('production-flow.js','production-flow.css'):
            with urllib.request.urlopen(self.origin+'/'+path) as response:self.assertEqual(response.status,200)

    def test_generated_script_still_needs_review(self):
        p=self.fixture();p['phase']='script_review'
        r=novel.public(p)['readiness'];self.assertEqual(r['stages'][0]['status'],'recorded')
        self.assertTrue(any(t['title']=='审核详细剧本' for t in r['tasks']))


class DialogueOccurrencesTests(unittest.TestCase):
    def test_two_source_replies_need_two_actual_occurrences(self):
        p={'production_preferences':{'version':1},'plan':{'dialogue_ledger':[{'id':i,'episode_id':'e1','speaker':'林青','text':'我知道了。'} for i in ['d1','d2']]}}
        shot={'id':'s1','seconds':10,'dialogue_ids':['d1','d2'],'dialogue':'林青：我知道了。'}
        with self.assertRaisesRegex(ValueError,'删改或截断'):fidelity.validate_script(p,{'id':'e1'},{'shots':[shot]})
        shot['dialogue']='林青：我知道了。\n林青：我知道了。';fidelity.validate_script(p,{'id':'e1'},{'shots':[shot]})

    def test_order_inside_same_shot_is_checked(self):
        p={'production_preferences':{'version':1},'plan':{'dialogue_ledger':[{'id':'d1','episode_id':'e1','speaker':'林青','text':'你来了吗？'},{'id':'d2','episode_id':'e1','speaker':'沈舟','text':'已经来了。'}]}}
        shot={'id':'s1','seconds':10,'dialogue_ids':['d1','d2'],'dialogue':'沈舟：已经来了。\n林青：你来了吗？'}
        with self.assertRaisesRegex(ValueError,'次序'):fidelity.validate_script(p,{'id':'e1'},{'shots':[shot]})


if __name__=='__main__':unittest.main()
