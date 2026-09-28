"""Video options and timeout regression checks without real generation calls."""
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import capabilities,providers,server,storage,video_controls


def native(model='sora-2-pro',**fields):
    return {'kind':'video','protocol':'openai_video','model':model,'base_url':'https://example.com/v1','name':'Fixture',**fields}


def job(size='auto',seconds=4,**params):
    return {'prompt':'An origami bird in a studio','size':size,'seconds':seconds,'parameters':params}


class VideoControlsTests(unittest.TestCase):
    def test_native_sizes_durations_and_real_body(self):
        for model in ('sora-2','sora-2-pro'):
            p=native(model)
            for ratio in video_controls.options(p)['ratios']:
                w,h=map(int,ratio['value'].split(':'))
                for size in ratio['sizes'].values():
                    width,height=map(int,size.split('x'))
                    self.assertEqual(width*h,height*w)
                    for seconds in (4,8,12,16,20):
                        path,body,multipart=providers.build(p,job(size,seconds))
                        self.assertEqual(path,'/videos');self.assertTrue(multipart)
                        self.assertEqual(body['seconds'],str(seconds));self.assertEqual(body['size'],size)

    def test_native_model_restrictions(self):
        for model,size,seconds in [('sora-2','1920x1080',4),('sora-2','1024x1792',4),
                                   ('sora-2-pro','1024x1024',4),('sora-2-pro','auto',5)]:
            with self.subTest(model=model,size=size,seconds=seconds),self.assertRaises(ValueError):
                providers.build(native(model),job(size,seconds))
        with self.assertRaises(ValueError):providers.build(native(extra={'size':'3840x2160'}),job())

    def test_unmapped_native_fields_do_not_slip_through(self):
        for key,value in [('fps',24),('guidance_scale',7.5),('audio',False),('camera','orbit')]:
            with self.assertRaises(ValueError):providers.build(native(),job(**{key:value}))

    def test_custom_fields_and_frames_remain_typed(self):
        p={'kind':'video','protocol':'custom','model':'fixture-video','custom':{
            'submit_path':'/render','body':{'prompt':'{{prompt}}','duration':'{{seconds}}','ratio':'{{aspect_ratio}}',
            'fps':'{{fps}}','cfg':'{{guidance_scale}}','audio':'{{audio}}','first':'{{first_frame}}','last':'{{last_frame}}'},
            'capabilities':{k:True for k in ('aspect_ratio','fps','guidance_scale','audio','first_frame','last_frame')}}}
        j=job(seconds=6,aspect_ratio='9:16',fps=24,guidance_scale=7.5,audio=False)
        j['input_assets']={'first_frame':'first','last_frame':'last'}
        with patch('uploads.get',return_value={}),patch('uploads.data_uri',side_effect=lambda x:'data:image/png;base64,'+x):
            _,body,multipart=providers.build(p,j)
        self.assertFalse(multipart);self.assertEqual(body['duration'],6);self.assertEqual(body['fps'],24)
        self.assertEqual(body['cfg'],7.5);self.assertIs(body['audio'],False)
        self.assertTrue(body['first'].endswith('first'));self.assertTrue(body['last'].endswith('last'))
        self.assertEqual(video_controls.options(p)['mode'],'aspect')
        for params in ({'fps':0},{'fps':24.5},{'fps':True},{'guidance_scale':float('nan')}):
            with self.assertRaises(ValueError):providers.build(p,job(**params))

    def test_first_frame_size_check_still_applies(self):
        j=job('1920x1080');j['input_assets']={'first_frame':'frame'}
        with patch('uploads.get',return_value={'width':1280,'height':720}),self.assertRaises(ValueError):
            providers.build(native(),j)

    def test_native_invalid_request_rejected_before_job_creation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(storage,'DATA',Path(tmp)):
            storage.init();p=native('sora-2',id='a'*32);storage.put('providers',p)
            with patch.object(server,'dispatch') as dispatch,self.assertRaises(ValueError):
                server.create_job({'provider_id':p['id'],'prompt':'fixture','size':'1920x1080','seconds':4})
            dispatch.assert_not_called();self.assertEqual(storage.items('jobs'),[])


class RequestTimeoutTests(unittest.TestCase):
    def test_per_kind_defaults_and_override(self):
        for kind,expected in [('image',600),('video',300),('chat',150)]:
            p={'kind':kind,'protocol':'openai_image','base_url':'https://example.com/v1'}
            with patch.object(providers.OPENER,'open',side_effect=TimeoutError()) as opener:
                with self.assertRaises(providers.ProviderError) as caught:providers.request(p,'/generate',{'prompt':'fixture'})
            self.assertEqual(opener.call_args.kwargs['timeout'],expected);self.assertEqual(opener.call_count,1)
            self.assertTrue(caught.exception.uncertain);self.assertFalse(caught.exception.retryable)
            self.assertEqual(caught.exception.code,'response_timeout');self.assertIn(str(expected),str(caught.exception))
        self.assertEqual(providers.request_timeout({'kind':'image','request_timeout_seconds':1200}),1200)
        self.assertEqual(providers.request_timeout({'kind':'image','request_timeout_seconds':1200},False),150)

    def test_wrapped_timeout_and_connection_error_differ(self):
        p=native()
        for error,code in [(urllib.error.URLError(TimeoutError()),'response_timeout'),(ConnectionResetError(),'connection_interrupted')]:
            with patch.object(providers.OPENER,'open',side_effect=error),self.assertRaises(providers.ProviderError) as caught:
                providers.request(p,'/videos',{})
            self.assertEqual(caught.exception.code,code)
        with patch.object(providers.OPENER,'open',side_effect=TimeoutError()),self.assertRaises(providers.ProviderError) as caught:
            providers.request(p,'/videos/task-1')
        self.assertFalse(caught.exception.uncertain);self.assertTrue(caught.exception.retryable)
        self.assertIn('仅查询原任务',str(caught.exception))

    def test_timeout_setting_validation(self):
        for value in (0,59,1801,True,600.5,'600'):
            with self.assertRaises(ValueError):providers.validate(native(request_timeout_seconds=value))
        for value in (None,60,600,1800):providers.validate(native(request_timeout_seconds=value))

    def test_timeout_job_stays_uncertain_without_resubmission(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(storage,'DATA',Path(tmp)):
            storage.init();p=native();j={**job(),'id':'b'*32,'kind':'video','provider_snapshot':p,'created_at':storage.now(),'status':'queued'}
            storage.put('jobs',j)
            error=providers.ProviderError('timeout',uncertain=True,code='response_timeout')
            with patch.object(providers,'execute',side_effect=error) as execute:server.run_job(j['id'])
            saved=storage.get('jobs',j['id']);self.assertEqual(saved['status'],'interrupted')
            self.assertEqual(saved['error_code'],'response_timeout');self.assertEqual(execute.call_count,1)


if __name__=='__main__':unittest.main()
