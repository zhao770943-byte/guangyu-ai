"""Professional desk gates against isolated uploads/storage; no model requests."""
import copy
import unittest
from unittest.mock import Mock
import storage
import server
import novel_studio as novel
import production_book as book
from test_novel_studio import NovelTests


class ProductionBookTests(unittest.TestCase):
    setUp=NovelTests.setUp
    api=NovelTests.api
    image=NovelTests.image
    create=NovelTests.create
    outline=NovelTests.outline
    script=NovelTests.script

    def fixture(self):
        self.create()
        p=novel.require(self.p['id']);p['plan']=self.outline()
        p['plan']['episodes'][0].update(self.script())
        p.update(phase='shot_review', paused=True,production_book={'enabled':True})
        a=self.image()['id']
        p['locked_assets']={a['id']:self.image()['id'] for a in p['plan']['assets']}
        for key,e,s,i in book.pairs(p):
            p['images'][key]=a
            book.apply(p,{'action':'studio_contract','slot':key,'contract':{**{k:'实际画面检查说明 '+k for k in book.CONTRACT_FIELDS},'sound_mode':'dub'}})
        return p

    def approve(self,p,key):
        book.apply(p,{'action':'studio_review_shot','slot':key,'fingerprint':book.fingerprint(p,key),'checks':dict.fromkeys(book.SHOT_CHECKS,True),'inspected':True,'notes':'逐镜查看图像与相邻构图，人物和道具方向一致。'})

    def test_changed_pixels_asset_contract_or_previous_shot_invalidates_review(self):
        p=self.fixture();key='shot:e1:s2';self.approve(p,key)
        self.assertEqual(book.shot_state(p,key)['status'],'approved')
        for update in [lambda q:q['images'].update({'shot:e1:s1':self.image('blue')['id']}),lambda q:q['locked_assets'].update(a1=self.image('green')['id']),lambda q:q['production_book']['contracts'][key].update(end='转身离开'),lambda q:q['plan']['episodes'][0]['shots'][0].update(action='反方向走')]:
            q=copy.deepcopy(p);update(q)
            self.assertEqual(book.shot_state(q,key)['status'],'stale')
        # Ordinary camera wording polish does not invalidate a checked still.
        p['plan']['episodes'][0]['shots'][1]['video_prompt']='专业运镜润色'
        self.assertEqual(book.shot_state(p,key)['status'],'approved')
        p['images']['shot:e1:s3']=self.image('purple')['id']
        self.assertEqual(book.shot_state(p,key)['status'],'stale')

    def test_unapproved_storyboard_blocks_paid_submission(self):
        p=self.fixture();p['phase']='videos';p['paused']=False
        prepare=Mock();e=p['plan']['episodes'][0];s=e['shots'][0]
        with self.assertRaisesRegex(ValueError,'未提交视频'):
            novel.prepare_task(p,'video:e1:s1',{'episode':e,'shot':s},prepare)
        prepare.assert_not_called();self.mock_dispatch.assert_not_called()

    def test_stale_review_rejected_and_no_partial_mutation(self):
        p=self.fixture();before=copy.deepcopy(p)
        with self.assertRaisesRegex(ValueError,'换版'):
            book.apply(p,{'action':'studio_review_shot','slot':'shot:e1:s1','fingerprint':'old'})
        self.assertEqual(p,before)
        with self.assertRaisesRegex(ValueError,'实际查看'):
            book.apply(p,{'action':'studio_review_shot','slot':'shot:e1:s1','fingerprint':book.fingerprint(p,'shot:e1:s1'),'checks':dict.fromkeys(book.SHOT_CHECKS,True),'inspected':False})

    def test_command_idempotency_and_conflicting_revision(self):
        p=self.fixture();novel.persist(p)
        body={'action':'studio_issue','id':p['id'],'version':p['version'],'request_id':storage.uid(),'notes':'石碑掌印不一致','category':'道具'}
        first=self.api('/api/novels/command',body);second=self.api('/api/novels/command',body)
        self.assertEqual(first['version'],second['version'])
        self.assertEqual(len(second['production_book']['issues']),1)
        self.api('/api/novels/command',{**body,'request_id':storage.uid()},400)
        with self.assertRaisesRegex(ValueError,'未关闭'):
            book.require_shots(novel.require(p['id']))
        self.mock_dispatch.assert_not_called()

    def test_delivery_is_versioned_and_invalidated_by_sound_revision(self):
        p=self.fixture();p['phase']='complete'
        (storage.DATA/'media'/'fixture.mp4').write_bytes(b'fixture-not-visual-acceptance')
        j={'id':storage.uid(),'created_at':storage.now(),'kind':'video','status':'succeeded','result':{'assets':[{'type':'video','local':True,'url':'/media/fixture.mp4'}]}}
        storage.put('jobs',j);p['films']={'e1':j['id']}
        body={'action':'studio_delivery','fingerprint':book.film_fingerprint(p),'watched':True,'checks':dict.fromkeys(book.DELIVERY_CHECKS,True),'notes':'完整观看和试听这一版'}
        book.apply(p,body);self.assertTrue(book.summary(p)['delivery_approved'])
        book.apply(p,{'action':'studio_sound','voices':[],'mix_notes':'修复末段背景音'})
        self.assertFalse(book.summary(p)['delivery_approved']);self.assertFalse(p['final_user_approved'])
        self.assertEqual(p['production_book']['delivery']['notes'],body['notes'])
        book.apply(p,{**body,'fingerprint':book.film_fingerprint(p)})
        self.assertEqual(len(p['production_book']['delivery_history']),1)

    def test_cannot_accept_missing_check_or_invent_audio_reference(self):
        p=self.fixture();before=copy.deepcopy(p)
        with self.assertRaises(ValueError):book.apply(p,{'action':'studio_sound','voices':[{'asset_id':'a1','audio_job_id':'not-real'}]})
        self.assertEqual(p,before)
        with self.assertRaises(ValueError):book.apply(p,{'action':'studio_delivery','watched':True,'checks':{'picture':True}})

    def test_offscreen_announcer_and_crowd_have_separate_voice_slots(self):
        p=self.fixture()
        book.apply(p,{'action':'studio_sound','voices':[{'asset_id':'voice:announcer','voice':'执事原样片','direction':'厚重、平常通报'},{'asset_id':'voice:crowd','direction':'惊呼后错时议论'}]})
        self.assertEqual(len(p['production_book']['voices']),2)
        self.mock_dispatch.assert_not_called()

    def test_contract_appends_constraints_and_never_calls_provider(self):
        p=self.fixture();text=book.contract_prompt(p,'shot:e1:s1')
        self.assertIn('不得被语言润色覆盖',text);self.assertIn('后期配音',text)
        self.mock_dispatch.assert_not_called()

    def test_http_public_state_and_enabled_gate_survive_draft_save(self):
        self.create();p=self.api('/api/novels/save',{**self.p,'professional_workflow':True})
        p=self.api('/api/novels/save',{**p,'review_storyboards':False,'review_videos':False})
        self.assertTrue(p['production_state']['enabled']);self.assertTrue(p['review_storyboards']);self.assertTrue(p['review_videos'])


if __name__=='__main__':unittest.main()
