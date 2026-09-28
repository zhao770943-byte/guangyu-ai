import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import storage,video_posters,work_library
from test_comfy_h3 import MP4

class PosterTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        p=patch.object(storage,'DATA',Path(tmp.name));p.start();self.addCleanup(p.stop);storage.init()
        self.id=storage.uid();self.url='/media/'+self.id+'-0.mp4'
        work_library.local_path(self.url).write_bytes(MP4)
        self.job={'id':self.id,'created_at':storage.now(),'status':'succeeded','kind':'video','result':{'assets':[{'type':'video','local':True,'url':self.url}]}}
        storage.put('jobs',self.job)
    def test_legacy_video_gets_real_cached_cover_without_record_mutation(self):
        before=storage.get('jobs',self.id)
        asset=storage.public_job(before)['result']['assets'][0]
        self.assertIn('/api/video-poster?',asset['poster_url'])
        path=video_posters.get(self.id,0);mtime=path.stat().st_mtime_ns
        with Image.open(path) as im:
            self.assertEqual(im.format,'JPEG');self.assertEqual(im.size,(64,64));self.assertGreater(im.getpixel((30,30))[0],180)
        self.assertEqual(video_posters.get(self.id,0).stat().st_mtime_ns,mtime)
        self.assertEqual(storage.get('jobs',self.id),before)
        work_library.remove(self.id)
        self.assertFalse(path.exists());self.assertFalse(work_library.local_path(self.url).exists())
        with self.assertRaises(ValueError):video_posters.get(self.id,0)
    def test_remote_invalid_index_and_path_are_never_opened(self):
        for index in (-1,1):
            with self.assertRaises(ValueError):video_posters.get(self.id,index)
        for a in ({'type':'video','url':'https://example.com/a.mp4'}, {'type':'video','local':True,'url':'/media/../secret.mp4'}):
            storage.update_job(self.id,result={'assets':[a]})
            with self.assertRaises(ValueError):video_posters.get(self.id,0)
    def test_disguised_playlist_does_not_become_a_poster(self):
        raw=b'#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXTINF:5,\nhttps://invalid.example/segment.ts\n#EXT-X-ENDLIST\n'
        work_library.local_path(self.url).write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'封面'):video_posters.get(self.id,0)
        self.assertEqual(work_library.local_path(self.url).read_bytes(),raw)
        self.assertFalse(work_library.local_path(video_posters.cache_url(self.url)).exists())

if __name__=='__main__':unittest.main()
