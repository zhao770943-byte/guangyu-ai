"""Paid-request boundaries and separate voice/performance contract."""
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import providers, model_catalog

class CosyVoiceTests(unittest.TestCase):
    def provider(self):
        return {'kind':'audio','protocol':'cosyvoice_speech','model':'cosyvoice-v3.5-plus','platform':'dashscope',
                'base_url':'https://dashscope.aliyuncs.com/compatible-mode/v1','extra':{'voice':'cosyvoice-v3.5-plus-vd-fixture'}}
    def build(self,params=None):
        return providers.build(self.provider(),{'prompt':'我相信你。','parameters':params or {}})
    def test_bound_voice_and_acting_remain_separate(self):
        path,body,_=self.build({'instructions':'轻声安慰，句尾收稳。','speed':1,'seed':42})
        self.assertEqual(body['input']['text'],'我相信你。')
        self.assertEqual(body['input']['instruction'],'轻声安慰，句尾收稳。')
        self.assertNotIn('instructions',body['input']);self.assertNotIn('voice',body)
        self.assertEqual(body['input']['voice'],'cosyvoice-v3.5-plus-vd-fixture')
        self.assertEqual(body['input']['rate'],1);self.assertEqual(body['input']['seed'],42)
        self.assertEqual(providers.endpoint(self.provider(),path),'https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer')
    def test_voice_and_default_acting_not_silently_replaced(self):
        _,body,_=self.build();self.assertNotIn('instruction',body['input'])
        with self.assertRaisesRegex(ValueError,'自定义音色'):self.build({'voice':'Serena'})
        with self.assertRaisesRegex(ValueError,'自定义音色'):self.build({'voice':'cosyvoice-v3.5-flash-vd-fixture'})
        p=self.provider();p['extra']={}
        with self.assertRaisesRegex(ValueError,'自定义音色'):providers.build(p,{'prompt':'fixture'})
    def test_weighted_instruction_and_parameter_limits(self):
        self.build({'instructions':'轻'*50})
        with self.assertRaisesRegex(ValueError,'100 字符'):self.build({'instructions':'轻'*51})
        with self.assertRaisesRegex(ValueError,'语速'):self.build({'speed':.4})
        with self.assertRaisesRegex(ValueError,'随机种子'):self.build({'seed':65536})
    def test_endpoint_restricts_route_and_keeps_destination(self):
        p=self.provider();base=p['base_url']
        with self.assertRaisesRegex(ValueError,'路径'):providers.endpoint(p,'/models')
        p['base_url']='https://unrelated.example/v1'
        with self.assertRaisesRegex(ValueError,'官方接口'):providers.endpoint(p,'/services/audio/tts/SpeechSynthesizer')
        p['base_url']='https://abc123.cn-beijing.maas.aliyuncs.com/api/v1'
        self.assertEqual(providers.endpoint(p,'/services/audio/tts/SpeechSynthesizer'),'https://abc123.cn-beijing.maas.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer')
        self.assertEqual(self.provider()['base_url'],base)
    def test_catalog_uses_output_audio_and_matching_native_protocol(self):
        p=self.provider();p['protocol']='openai_chat'
        rows,_=model_catalog._normalize([{'id':'cosyvoice-v3.5-plus'},{'id':'cosyvoice-v3-plus'}],'openai',p,'')
        self.assertEqual(rows[0]['protocol'],'cosyvoice_speech');self.assertEqual(rows[0]['supported_kinds'],['audio'])
        self.assertIsNone(rows[1]['protocol'])

if __name__=='__main__':unittest.main()
