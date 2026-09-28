"""Deletion uses disposable media only; no user files or provider calls."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage, server, work_library, usage


class WorkLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(storage, 'DATA', Path(self.temp.name))
        self.patch.start(); self.addCleanup(self.patch.stop)
        storage.init()

    def job(self, kind='image', url=None):
        identity = storage.uid()
        url = url or '/media/' + identity + ('.png' if kind=='image' else '.mp4')
        job = {'id':identity, 'created_at':storage.now(), 'kind':kind, 'status':'succeeded',
               'archive_status':'saved', 'seconds':4, 'model':'fixture', 'prompt':'fixture',
               'usage':{'input_tokens':10, 'output_tokens':20},
               'result':{'assets':[{'type':kind, 'url':url, 'local':url.startswith('/media/'), 'duration_seconds':3.8}]}}
        storage.put('jobs',job)
        return job

    def test_delete_files_preserve_usage_uploads_and_repeat(self):
        job = self.job('video'); path=work_library.local_path(job['result']['assets'][0]['url'])
        path.write_bytes(b'fixture'); reference=storage.DATA/'uploads'/'fixture.png';reference.write_bytes(b'reference')
        before=usage.build_report(period='all')['summary']
        deleted=work_library.remove(job['id'])
        self.assertFalse(path.exists());self.assertTrue(reference.exists())
        self.assertTrue(deleted['work_deleted_at']);self.assertEqual(deleted['result']['assets'],[])
        self.assertEqual(before,usage.build_report(period='all')['summary'])
        self.assertEqual(deleted,work_library.remove(job['id']))

    def test_shared_file_survives_until_last_owner_deleted(self):
        first=self.job();url=first['result']['assets'][0]['url'];second=self.job(url=url)
        path=work_library.local_path(url);path.write_bytes(b'fixture')
        work_library.remove(first['id']);self.assertTrue(path.exists())
        work_library.remove(second['id']);self.assertFalse(path.exists())

    def test_batch_removes_all_outputs_and_keeps_generated_count(self):
        job=self.job();second_url='/media/'+storage.uid()+'.png'
        job['result']['assets'].append({'type':'image','url':second_url,'local':True})
        storage.put('jobs',job)
        paths=[work_library.local_path(a['url']) for a in job['result']['assets']]
        for path in paths:path.write_bytes(b'fixture')
        work_library.remove(job['id'])
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertEqual(usage.build_report(period='all')['summary']['image_count'],2)

    def test_missing_and_remote_files_need_no_network(self):
        for url in (None,'https://example.invalid/media.png'):
            job=self.job(url=url)
            with patch('urllib.request.urlopen',side_effect=AssertionError('No network permitted')):
                deleted=work_library.remove(job['id'])
            self.assertEqual(deleted['work_cleanup_pending'],[])

    def test_batch_validates_all_paths_before_mutation(self):
        job=self.job();path=work_library.local_path(job['result']['assets'][0]['url']);path.write_bytes(b'fixture')
        job['result']['assets'].append({'type':'image','url':'/media/../uploads/fixture.png','local':True});storage.put('jobs',job)
        with self.assertRaises(ValueError):work_library.remove(job['id'])
        self.assertTrue(path.exists());self.assertFalse(storage.get('jobs',job['id']).get('work_deleted_at'))

    def test_pending_cleanup_survives_restart(self):
        job=self.job();path=work_library.local_path(job['result']['assets'][0]['url']);path.write_bytes(b'fixture')
        with patch.object(Path,'unlink',side_effect=PermissionError('locked')):
            deleted=work_library.remove(job['id'])
        self.assertTrue(deleted['work_cleanup_pending']);self.assertTrue(path.exists())
        server.recover()
        self.assertFalse(path.exists());self.assertEqual(storage.get('jobs',job['id'])['work_cleanup_pending'],[])

    def test_non_media_failed_and_saving_records_rejected(self):
        for fields in ({'kind':'chat'},{'status':'failed'},{'archive_status':'pending'}):
            job=self.job();storage.update_job(job['id'],**fields)
            with self.assertRaises(ValueError):work_library.remove(job['id'])

    def test_local_image_metadata_does_not_rewrite_files_or_database(self):
        job=self.job();path=work_library.local_path(job['result']['assets'][0]['url'])
        Image.new('RGB',(32,48)).save(path)
        original=path.read_bytes();public=storage.public_job(job)
        self.assertEqual((public['result']['assets'][0]['width'],public['result']['assets'][0]['height']),(32,48))
        self.assertEqual(original,path.read_bytes());self.assertEqual(job,storage.get('jobs',job['id']))

    def test_http_csrf_active_guard_and_deletion(self):
        job=self.job();app=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        origin=f'http://127.0.0.1:{app.server_port}'
        with patch.object(server,'PORT',app.server_port),patch.object(server,'ORIGIN',origin):
            thread=threading.Thread(target=app.serve_forever,daemon=True);thread.start()
            def post(token=server.CSRF):
                req=urllib.request.Request(origin+'/api/jobs/delete',data=json.dumps({'id':job['id']}).encode() if token==server.CSRF else b'',headers={'Content-Type':'application/json','Origin':origin,'X-CSRF-Token':token})
                return urllib.request.urlopen(req,timeout=5)
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:post('invalid')
                self.assertEqual(error.exception.code,403)
                server.ACTIVE.add(job['id'])
                with self.assertRaises(urllib.error.HTTPError) as error:post()
                self.assertEqual(error.exception.code,400);server.ACTIVE.discard(job['id'])
                with post() as response:self.assertTrue(json.load(response)['work_deleted_at'])
                with self.assertRaises(ValueError):server.dispatch_archive(job)
            finally:
                server.ACTIVE.discard(job['id']);app.shutdown();app.server_close();thread.join()


if __name__=='__main__':unittest.main()
