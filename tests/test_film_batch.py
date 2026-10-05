"""Split scheduling and real local A/V assembly; no provider requests."""
import math
import struct
import unittest
from fractions import Fraction
from unittest.mock import Mock, patch
import test_visual_film
import film_plan
import film_queue
import film_compose
import server
import storage
import usage
import work_library


def clip(path, color, seconds=2, sound=True, rate=24, frequency=440):
    import av
    from PIL import Image
    with av.open(str(path), 'w', format='mp4') as out:
        video = out.add_stream('libx264', rate=rate)
        video.width, video.height, video.pix_fmt = 90, 160, 'yuv420p'
        video.codec_context.thread_count = 1
        audio = out.add_stream('aac', rate=44100) if sound else None
        if audio:
            audio.layout = 'mono'
        for i in range(round(seconds * rate)):
            frame = av.VideoFrame.from_image(Image.new('RGB', (90, 160), color))
            frame.pts, frame.time_base = i, Fraction(1, rate)
            for packet in video.encode(frame):
                out.mux(packet)
        for packet in video.encode(None):
            out.mux(packet)
        if audio:
            count = round(seconds * 44100)
            for i in range(0, count, 1024):
                length = min(count - i, 1024)
                frame = av.AudioFrame(format='fltp', layout='mono', samples=length)
                frame.sample_rate, frame.pts, frame.time_base = 44100, i, Fraction(1, 44100)
                frame.planes[0].update(struct.pack('<' + 'f' * length, *(.2 * math.sin(2 * math.pi * frequency * (i+j) / 44100) for j in range(length))))
                for packet in audio.encode(frame):
                    out.mux(packet)
            for packet in audio.encode(None):
                out.mux(packet)


class FilmBatchTests(unittest.TestCase):
    setUp = test_visual_film.VisualFilmTests.setUp
    api = test_visual_film.VisualFilmTests.api
    image = test_visual_film.VisualFilmTests.image
    fixture = test_visual_film.VisualFilmTests.fixture

    def batch(self, mode='serial', durations=(10, 10, 15)):
        project, provider, body = self.fixture()
        body.update(seconds=sum(durations), durations=list(durations), execution_mode=mode)
        return self.api('/api/visual-projects/film-generate', body, 202), body

    def tick(self, compose=None):
        film_queue.tick(server.dispatch, compose, server.ACTIVE, server.ACTIVE_LOCK)

    def finish(self, job_id):
        storage.update_job(job_id, status='succeeded', archive_status='saved', result={'text': '', 'assets': [{'type': 'video', 'local': True, 'url': '/media/'+job_id+'.mp4'}]})

    def test_plan_uses_duration_sum_and_fixed_duration_tail(self):
        p, provider, body = self.fixture()
        for durations, requests, total in [([10,10,10],[15,15],30),([10,10,15],[15,15,15],35),([10,10,25],[15,15,15],45)]:
            plan = self.api('/api/visual-projects/film-plan', {**body, 'durations': durations})
            self.assertEqual([s['request_seconds'] for s in plan['segments']], requests)
            self.assertEqual(plan['seconds'], total)
            self.assertAlmostEqual(sum(s['used_seconds'] for s in plan['segments']), total)
        self.assertEqual(storage.items('jobs'), [])
        for durations in ([0, 20], [301, 301], [True, 20]):
            self.api('/api/visual-projects/film-plan', {**body, 'durations':durations}, 400)

    def test_split_references_and_continuation(self):
        response, body = self.batch()
        parent = response['job'];segments = parent['film_segments']
        self.assertEqual([s['used_seconds'] for s in segments], [15,15,5])
        children = [storage.get('jobs', s['job_id']) for s in segments]
        timeline = parent['visual_film_timeline']
        self.assertEqual([c['input_assets']['references'] for c in children], [[timeline[0]['upload_id'],timeline[1]['upload_id']],[timeline[1]['upload_id'],timeline[2]['upload_id']],[timeline[2]['upload_id']]])
        self.assertIn('上一段进行 5 秒',children[1]['prompt'])
        self.assertIn('只使用前 5 秒',children[2]['prompt'])
        again = self.api('/api/visual-projects/film-generate',body,202)
        self.assertEqual(again['job']['id'], parent['id']);self.assertEqual(len(storage.items('jobs')),4)
        self.assertEqual(self.mock_dispatch.call_count,1)

    def test_serial_waits_for_download_then_composes_once(self):
        response, _ = self.batch();parent = response['job'];ids = [s['job_id'] for s in parent['film_segments']]
        compose = Mock(side_effect=lambda j:server.ACTIVE.add(j['id']))
        self.tick(compose);self.assertEqual(self.mock_dispatch.call_count,1)
        storage.update_job(ids[0],status='succeeded',archive_status='pending')
        self.tick(compose);self.assertEqual(self.mock_dispatch.call_count,1)
        for index, identity in enumerate(ids):
            self.finish(identity);self.tick(compose)
            self.assertEqual(self.mock_dispatch.call_count,min(index+2,3))
        self.tick(compose);compose.assert_called_once()
        self.assertEqual(storage.get('jobs',parent['id'])['film_completed'],3)

    def test_parallel_is_bounded_and_preserves_order(self):
        response, _ = self.batch('parallel',(25,25,25));ids = [s['job_id'] for s in response['job']['film_segments']]
        self.assertEqual(self.mock_dispatch.call_count,3);self.tick();self.assertEqual(self.mock_dispatch.call_count,3)
        self.finish(ids[1]);self.tick();self.assertEqual(self.mock_dispatch.call_count,4)
        self.finish(ids[0]);self.tick();self.assertEqual(self.mock_dispatch.call_count,5)
        self.assertEqual([c.args[0]['film_segment_index'] for c in self.mock_dispatch.call_args_list], [1,2,3,4,5])

    def test_global_capacity_delays_waiting_segments(self):
        response, _ = self.batch('parallel',(20,20,20));ids = [s['job_id'] for s in response['job']['film_segments']]
        self.finish(ids[0]);server.ACTIVE.update(str(i) for i in range(12));self.tick()
        self.assertEqual(self.mock_dispatch.call_count,3)
        server.ACTIVE.clear();self.tick();self.assertEqual(self.mock_dispatch.call_count,4)

    def test_failure_keeps_successful_segments_and_retry_is_idempotent(self):
        response, _ = self.batch();parent = response['job'];ids = [s['job_id'] for s in parent['film_segments']]
        self.finish(ids[0]);self.tick();storage.update_job(ids[1],status='failed',error='fixture')
        self.tick();self.assertEqual(self.mock_dispatch.call_count,2)
        self.assertEqual(storage.get('jobs',parent['id'])['film_phase'],'paused')
        retry = {'id':parent['id'],'retry_job_id':ids[1]}
        new = self.api('/api/visual-projects/film-retry',retry)
        self.api('/api/visual-projects/film-retry',retry)
        self.assertEqual(len(storage.items('jobs')),5)
        self.tick();self.assertEqual(self.mock_dispatch.call_count,3)
        replacement = new['film_segments'][1]['job_id']
        self.assertNotEqual(replacement,ids[1]);self.assertEqual(storage.get('jobs',ids[0])['status'],'succeeded')
        self.finish(replacement);self.tick();self.assertEqual(self.mock_dispatch.call_count,4)
        self.assertEqual(storage.get('jobs',ids[1])['status'],'failed')
        with self.assertRaises(ValueError):work_library.remove(ids[0])

    def test_restart_never_reposts_claimed_but_unconfirmed_submission(self):
        response, _ = self.batch();parent = response['job'];ids = [s['job_id'] for s in parent['film_segments']]
        self.mock_dispatch.reset_mock();server.recover();self.tick()
        self.mock_dispatch.assert_not_called()
        self.assertEqual(storage.get('jobs',ids[0])['status'],'interrupted')
        self.assertEqual(storage.get('jobs',ids[1])['film_dispatch_state'],'waiting')
        self.api('/api/visual-projects/film-retry',{'id':parent['id'],'retry_job_id':ids[0]},400)
        storage.update_job(ids[0],status='polling',upstream_id='existing-task')
        server.recover();self.mock_dispatch.assert_called_once()
        self.assertTrue(self.mock_dispatch.call_args.kwargs['resume'])

    def test_waiting_never_submitted_segments_resume_after_restart(self):
        response, _ = self.batch();ids=[s['job_id'] for s in response['job']['film_segments']]
        self.finish(ids[0]);self.mock_dispatch.reset_mock();server.recover();self.tick()
        self.mock_dispatch.assert_called_once();self.assertEqual(self.mock_dispatch.call_args.args[0]['id'],ids[1])

    def test_local_assembly_not_counted_as_provider_request(self):
        response, _ = self.batch('parallel')
        for segment in response['job']['film_segments']:self.finish(segment['job_id'])
        report = usage.build_report(period='all')
        self.assertEqual(report['summary']['requests'],3)
        self.assertEqual(report['summary']['requested_video_seconds'],45)

    def composition_fixture(self, sound=True):
        segments=[]
        for index, color in enumerate(('red','blue')):
            identity=storage.uid();url='/media/'+identity+'.mp4';path=work_library.local_path(url)
            clip(path,color,2,sound=sound if index else True,rate=24 if index else 30,frequency=880 if index else 440)
            storage.put('jobs',{'id':identity,'created_at':storage.now(),'status':'succeeded','result':{'assets':[{'type':'video','local':True,'url':url}]}})
            segments.append({'job_id':identity,'start':index*2,'end':2 if index==0 else 3.5})
        return {'id':storage.uid(),'seconds':3.5,'film_segments':segments}

    def test_real_mp4_order_trim_frame_rates_and_audio(self):
        import av
        parent=self.composition_fixture();result=film_compose.compose(parent)
        path=work_library.local_path(result['assets'][0]['url'])
        with av.open(str(path)) as container:
            self.assertAlmostEqual(container.duration/av.time_base,3.5,delta=.05)
            images=[f.to_image().getpixel((45,80)) for f in container.decode(video=0)]
            self.assertEqual(len(images),105)
            self.assertGreater(images[59][0],220);self.assertGreater(images[60][2],220)
        with av.open(str(path)) as container:
            frames=list(container.decode(audio=0))
            samples=[]
            for f in frames:
                samples.extend(struct.unpack('<'+'f'*f.samples,bytes(f.planes[0])[:f.samples*4]))
            def crossings(start,end):
                a=samples[int(start*48000):int(end*48000)]
                return sum(a[i-1]<0<=a[i] for i in range(1,len(a)))/(end-start)
            self.assertAlmostEqual(crossings(.4,1.4),440,delta=3)
            self.assertAlmostEqual(crossings(2.2,3.2),880,delta=3)

    def test_silent_segment_gets_silence_and_too_short_video_is_not_padded(self):
        import av
        parent=self.composition_fixture(sound=False);result=film_compose.compose(parent)
        with av.open(str(work_library.local_path(result['assets'][0]['url']))) as container:
            for f in container.decode(audio=0):
                if float(f.time)>2.2:
                    values=struct.unpack('<'+'f'*f.samples,bytes(f.planes[0])[:f.samples*4])
                    self.assertLess(max(map(abs,values)),.001)
        parent['film_segments'][1]['end']=5;parent['seconds']=5
        with self.assertRaisesRegex(ValueError,'短于'):film_compose.compose(parent)
        self.assertTrue(work_library.local_path(result['assets'][0]['url']).is_file())
        self.assertFalse(work_library.local_path(result['assets'][0]['url']).with_suffix('.partial').exists())


if __name__=='__main__':unittest.main()
