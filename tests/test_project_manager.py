import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import storage
import project_manager as manager


class ProjectManagerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.patch = patch.object(storage, 'DATA', Path(temp.name)); self.patch.start(); self.addCleanup(self.patch.stop)
        storage.init()
        self.p = {'id': storage.uid(), 'title': 'Test project', 'updated_at': storage.now(), 'phase': 'assets',
                  'paused': True, 'version': 7, 'slots': {}, 'source': 'Private novel', 'provider_signatures': {'secret': 'hidden'},
                  'plan': {'assets': [{'id': 'a'}], 'episodes': [{'shots': [{}, {}]}]}}
        storage.put('novel_projects', self.p)

    def action(self, action, version=0):
        return manager.organize({'id': self.p['id'], 'kind': 'novel', 'version': version, 'action': action})

    def test_pin_archive_restore_preserve_production(self):
        self.assertTrue(self.action('pin')['pinned'])
        self.assertTrue(self.action('archive', 1)['archived'])
        restored = self.action('restore', 2)
        self.assertFalse(restored['archived']); self.assertTrue(restored['pinned'])
        self.assertEqual(storage.get('novel_projects', self.p['id']), self.p)

    def test_stale_request_cannot_overwrite(self):
        self.action('pin')
        with self.assertRaisesRegex(ValueError, '刷新'): self.action('unpin')

    def test_active_and_between_jobs_block_archive(self):
        self.p['paused'] = False; storage.put('novel_projects', self.p)
        with self.assertRaisesRegex(ValueError, '执行'): self.action('archive')
        self.p['paused'] = True; storage.put('novel_projects', self.p)
        storage.put('jobs', {'id':storage.uid(), 'created_at':storage.now(), 'status':'polling', 'novel_project_id':self.p['id']})
        with self.assertRaisesRegex(ValueError, '执行'): self.action('archive')

    def test_listing_is_summary_only_and_counts_successful_works(self):
        for status in ('failed', 'succeeded'):
            storage.put('jobs', {'id':storage.uid(), 'created_at':storage.now(), 'status':status,
                                'novel_project_id':self.p['id'], 'result': {'assets':[{'type':'image'}]}})
        p = manager.listing()['projects'][0]
        self.assertEqual((p['assets'], p['shots'], p['works'], p['failed']), (1,2,1,1))
        self.assertNotIn('source', p); self.assertNotIn('provider_signatures', p)

    def test_visual_composition_parent_is_guarded(self):
        job = {'id':storage.uid(), 'created_at':storage.now(), 'status':'polling'}; storage.put('jobs', job)
        p = {'id':storage.uid(), 'title':'Board', 'updated_at':storage.now(), 'nodes':[], 'film_job_ids':[job['id']]}
        storage.put('visual_projects', p)
        with self.assertRaisesRegex(ValueError, '执行'):
            manager.organize({'id':p['id'], 'kind':'visual', 'action':'archive', 'version':0})

    def test_cover_prefers_current_film_and_excludes_deleted_and_remote(self):
        self.p['films'] = {'e1': 'film'}
        jobs = [
            {'id':'deleted', 'status':'succeeded', 'created_at':'2099', 'novel_project_id':self.p['id'],
             'work_deleted_at':'today', 'result':{'assets':[{'type':'image','url':'/media/deleted.png'}]}},
            {'id':'remote', 'status':'succeeded', 'created_at':'2098', 'novel_project_id':self.p['id'],
             'result':{'assets':[{'type':'image','url':'https://example.test/private?token=secret'}]}},
            {'id':'image', 'status':'succeeded', 'created_at':'2097', 'novel_project_id':self.p['id'],
             'result':{'assets':[{'type':'image','url':'/media/current.png'}]}},
            {'id':'film', 'status':'succeeded', 'created_at':'2090',
             'result':{'assets':[{'type':'video','poster_url':'/media/film.jpg'}]}},
        ]
        self.assertEqual(manager.summarize('novel', self.p, jobs)['cover_url'], '/media/film.jpg')
        jobs[-1]['work_deleted_at'] = 'today'
        self.assertEqual(manager.summarize('novel', self.p, jobs)['cover_url'], '/media/current.png')
        self.assertEqual(manager.summarize('novel', self.p, jobs[:2])['cover_url'], '')

if __name__ == '__main__': unittest.main()
