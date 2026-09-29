"""Curated provider identities and output catalogs, checked 2026-09-29.

Families are display/search metadata, never invented callable model IDs.
Official entries are selectable but do not establish account access.
"""
from copy import deepcopy


def extend(presets):
    new = [
        ('tencent','腾讯混元','https://api.hunyuan.cloud.tencent.com/v1','https://console.cloud.tencent.com/hunyuan/','https://cloud.tencent.com/document/product/1729/111007',{'chat':'Hunyuan / 混元'}),
        ('baidu','百度千帆 / 文心','https://qianfan.baidubce.com/v2','https://console.bce.baidu.com/iam/','https://cloud.baidu.com/doc/qianfan-docs/s/Fm9l6ocai',{'chat':'ERNIE / 文心'}),
        ('iflytek','科大讯飞 / 星火','https://spark-api-open.xf-yun.com/agent/v1','https://console.xfyun.cn/','https://www.xfyun.cn/doc/spark/X2-Flash.html',{'chat':'Spark X2 Flash / 星火'}),
        ('stepfun','阶跃星辰 / StepFun','https://api.stepfun.com/v1','https://platform.stepfun.com/','https://platform.stepfun.com/docs',{'chat':'Step 5 / Step 3.7 / Step 3.5','image':'Step Image','audio':'StepAudio / TTS / Music / ASR'}),
        ('baichuan','百川智能','https://api.baichuan-ai.com/v1','https://platform.baichuan-ai.com/','https://platform.baichuan-ai.com/docs/api',{'chat':'Baichuan / 百川'}),
        ('yi','零一万物 / Yi','https://api.lingyiwanwu.com/v1','https://platform.lingyiwanwu.com/','https://platform.lingyiwanwu.com/docs',{'chat':'Yi Lightning / Yi Large'}),
        ('cohere','Cohere','https://api.cohere.ai/compatibility/v1','https://dashboard.cohere.com/api-keys','https://docs.cohere.com/docs/compatibility-api',{'chat':'Command / Aya','audio':'Cohere Transcribe'}),
        ('bfl','Black Forest Labs / FLUX','https://api.bfl.ai/v1','https://dashboard.bfl.ai/','https://docs.bfl.ai/quick_start/generating_images',{'image':'FLUX.2 / FLUX.1 Kontext'}),
        ('stability','Stability AI','https://api.stability.ai','https://platform.stability.ai/account/keys','https://platform.stability.ai/docs/api-reference',{'image':'Stable Image / Stable Diffusion','audio':'Stable Audio'}),
        ('runway','Runway','https://api.dev.runwayml.com/v1','https://dev.runwayml.com/','https://docs.dev.runwayml.com/guides/models/',{'image':'Gen Image','video':'Gen / Aleph / Act'}),
        ('luma','Luma AI','https://api.lumalabs.ai/dream-machine/v1','https://lumalabs.ai/api/','https://docs.lumalabs.ai/docs/video-generation',{'image':'Photon','video':'Ray'}),
        ('kling','快手 / 可灵','https://api-beijing.klingai.com','https://app.klingai.com/cn/dev/document-api','https://app.klingai.com/cn/dev/document-api',{'image':'Kolors / 可图','video':'Kling / 可灵'}),
        ('elevenlabs','ElevenLabs','https://api.elevenlabs.io/v1','https://elevenlabs.io/app/settings/api-keys','https://elevenlabs.io/docs/overview/models',{'audio':'Eleven / Scribe / Music'}),
        ('recraft','Recraft','https://external.api.recraft.ai/v1','https://www.recraft.ai/','https://www.recraft.ai/docs',{'image':'Recraft'}),
        ('ideogram','Ideogram','https://api.ideogram.ai','https://ideogram.ai/manage-api','https://developer.ideogram.ai/',{'image':'Ideogram'}),
    ]
    for identity,name,base,key,docs,families in new:
        protocols={'chat':'openai_chat'} if 'chat' in families else {}
        presets.insert(-1,dict(id=identity,name=name,base_url=base,api_key_url=key,api_key_label='获取 API Key',
            docs_url=docs,protocols=protocols,discovery_protocol='openai',model_types=list(families),
            families=families,note='型号以账户目录为准；未提供目录的平台可选官方公开型号。专用协议的接入状态会单独标注。'))
    by_id={p['id']:p for p in presets}
    # Open-weight manufacturers from AI Atlas, with an explicitly named host.
    # No manufacturer API key is sent to an unrelated hosting platform.
    for identity,name,family in [('meta','Meta','Llama'),('microsoft','Microsoft','Phi'),('ibm','IBM','Granite')]:
        p=dict(id=identity,name=name+' · NVIDIA 托管',base_url='https://integrate.api.nvidia.com/v1',
            api_key_url='https://build.nvidia.com/',api_key_label='获取 NVIDIA API Key',
            docs_url='https://docs.api.nvidia.com/nim/reference/models-1',
            protocols={'chat':'openai_chat'},discovery_protocol='openai',model_types=['chat'],
            families={'chat':family+' · 开源模型托管入口'},model_prefix=identity+'/',
            note='模型原厂为 '+name+'；此预设通过 NVIDIA NIM 托管调用，需 NVIDIA API Key。目录仅显示该原厂型号，也可改用本地 Ollama / LM Studio。')
        presets.insert(-1,p);by_id[identity]=p
    # Sora was removed from OpenAI's official API on 2026-09-24. Retain the
    # existing adapter for old snapshots/compatible gateways, not new presets.
    by_id['openai']['model_types']=['chat','audio','image']
    by_id['openai']['protocols'].pop('video',None)
    families={
        'openai':{'chat':'GPT / o 系列','image':'GPT Image 2.5 Sunburst / Flare · GPT Image 2','audio':'GPT TTS / Whisper / Realtime','video':'Sora'},
        'anthropic':{'chat':'Claude Fable / Opus / Sonnet / Haiku'},
        'gemini':{'chat':'Gemini Pro / Flash','image':'Nano Banana 香蕉 / Nano Banana 2 / Pro','audio':'Gemini TTS / Live','video':'Veo / Omni'},
        'deepseek':{'chat':'DeepSeek Chat / Reasoner'},
        'minimax':{'chat':'MiniMax M3 / M 系列','image':'Image-01','audio':'Speech / Music','video':'Hailuo / MiniMax H3'},
        'moonshot':{'chat':'Kimi / Moonshot'},
        'dashscope':{'chat':'Qwen / 通义千问','image':'Qwen Image / Wan 万相','audio':'Qwen TTS / ASR / Omni','video':'Wan / 万相 / HappyHorse'},
        'ark':{'chat':'Doubao Seed / 豆包','image':'Seedream 5 / 4.5 / 4','video':'Seedance 2.5 / 2.0'},
        'zhipu':{'chat':'GLM / 智谱','image':'CogView / GLM Image','video':'CogVideoX','audio':'GLM TTS / ASR / Voice'},
        'xai':{'chat':'Grok','image':'Grok Imagine Image','video':'Grok Imagine Video','audio':'Grok Voice'},
        'mistral':{'chat':'Mistral / Codestral / Devstral','audio':'Voxtral'},
        'nvidia':{'chat':'Nemotron / Meta Llama / Microsoft Phi / IBM Granite（托管）'},
        'cerebras':{'chat':'Cerebras 托管文本模型'},'sambanova':{'chat':'SambaNova 托管文本模型'},
        'weijin':{'chat':'账户文本目录','image':'GPT Image / Nano Banana 等（以账户为准）','video':'Seedance 2.5 / 2.0 等（以账户为准）'},
        'comfy_h3':{'video':'MiniMax H3 · 本地 8GB'},
    }
    domestic={'deepseek','minimax','moonshot','dashscope','ark','zhipu','tencent','baidu','iflytek','stepfun','baichuan','yi','kling'}
    gateways={'weijin','siliconflow','openrouter','groq','cerebras','together','fireworks','sambanova','deepinfra'}
    for p in presets:
        p['families']=families.get(p['id'],p.get('families',{}))
        # Only expose outputs on this API entry; open weights/research demos do
        # not imply that the same key/base URL offers that output API.
        if p['id']=='ark':p['model_types']=['chat','image','video']
        p['category']='custom' if p['id']=='custom' else 'local' if p.get('allow_local') else 'hosted' if p.get('model_prefix') else 'gateway' if p['id'] in gateways else 'domestic' if p['id'] in domestic else 'international'
        p['catalog_checked_at']='2026-09-29'
    by_id['tencent']['note']='此入口为混元文本 API；新购服务请按控制台提示迁移 TokenHub。开源 Hunyuan Image / Video 不等于此入口支持生图或视频。'
    by_id['iflytek']['note']='使用星火 X2 Flash HTTP 的 APIpassword；不要填写 WebSocket APPID。'
    by_id['kling']['note']='可灵使用 Access Key / Secret Key 签发 JWT，不能把原始 Secret Key 当成 Bearer API Key。当前专用鉴权待适配。'
    by_id['runway']['note']='Runway 专有接口还需要版本请求头；当前为厂商目录入口，专用适配待完成。'
    by_id['elevenlabs']['note']='语音、识别、音乐属于不同接口；当前 ElevenLabs 二进制响应及声音选择待适配。'

    def add(pid,kind,ids,protocol=None,names=None,custom=None):
        p=by_id[pid]
        for i,identity in enumerate(ids):
            entry=dict(id=identity,name=(names or ids)[i],model_kinds=[kind],supported_kinds=[kind] if protocol else [],
                       model_constraints={'kinds':[kind]},protocol=protocol,source='official_catalog',
                       audio_task='speech' if kind=='audio' else '')
            if custom:entry['custom']=deepcopy(custom)
            p.setdefault('official_models',[]).append(entry)

    add('openai','image',['gpt-image-2.5-sunburst','gpt-image-2.5-flare','gpt-image-2','gpt-image-1.5','gpt-image-1'],'openai_image',
        ['GPT Image 2.5 · Sunburst','GPT Image 2.5 · Flare','GPT Image 2.0','GPT Image 1.5','GPT Image 1'])
    add('gemini','image',['gemini-3.1-flash-image','gemini-3-pro-image','gemini-2.5-flash-image'],'gemini',
        ['Nano Banana 2 · 香蕉 2','Nano Banana Pro · 香蕉 Pro','Nano Banana · 香蕉'])
    for pid,ids in {
        'deepseek':['deepseek-chat','deepseek-reasoner'],'tencent':['hunyuan-turbos-latest'],
        'iflytek':['spark-x'],'baichuan':['Baichuan2-Turbo','Baichuan2-Turbo-192k'],
        'cohere':['command-a-plus-05-2026'],
    }.items():add(pid,'chat',ids,'openai_chat')
    # Native image contracts that actually use /images/generations + data[].url.
    by_id['xai']['protocols']['image']='openai_image'
    by_id['zhipu']['protocols']['image']='openai_image'
    add('xai','image',['grok-imagine-image-2.0'],'openai_image')
    add('zhipu','image',['cogview-4'],'openai_image')
    # Complete, reviewed JSON mappings are selectable without editing paths.
    # Keep these defaults minimal: optional fields omitted by the user are not
    # replaced with aggressive quality/size defaults.
    by_id['xai']['protocols']['video']='custom'
    add('xai','video',['grok-imagine-video-1.5'],'custom',custom={
        'submit_path':'/videos/generations','body':{'model':'{{model}}','prompt':'{{prompt}}','duration':'{{seconds}}'},
        'poll_path':'/videos/{id}','id_path':'request_id','status_path':'status',
        'success_values':['done'],'failure_values':['failed','expired'],
        'media_path':'video.url','capabilities':{}})
    by_id['xai']['note']='文本、图像已有适配；Grok Imagine Video 1.5 已预置文生视频提交和查询映射，支持 1–15 秒。声音等专用协议仍待适配。'
    by_id['luma']['protocols']['image']='custom'
    add('luma','image',['photon-1','photon-flash-1'],'custom',custom={
        'submit_path':'/generations/image','body':{'model':'{{model}}','prompt':'{{prompt}}'},
        'poll_path':'/generations/{id}','id_path':'id','status_path':'state',
        'success_values':['completed'],'failure_values':['failed'],
        'media_path':'assets.image','capabilities':{}})
    by_id['luma']['note']='Photon 文生图已预置提交和异步查询映射；Ray 视频及 CDN 参考图输入需要专用适配。'
    by_id['ark']['protocols'].update(image='ark_image',video='ark_video')
    add('ark','image',['doubao-seedream-5-0-pro-260628','doubao-seedream-5-0-flash-260915','doubao-seedream-4-5-251128','doubao-seedream-4-0-250828'],'ark_image',
        ['Seedream 5.0 Pro','Seedream 5.0 Flash','Seedream 4.5','Seedream 4.0'])
    add('ark','video',['doubao-seedance-2-5-260628','doubao-seedance-2-0-260128','doubao-seedance-2-0-fast-260128'],'ark_video',
        ['Seedance 2.5','Seedance 2.0','Seedance 2.0 Fast'])
    by_id['ark']['note']='方舟文本、Seedream 生图、Seedance 生视频使用各自的请求格式。可直接选择官方型号；开通权限以方舟账户为准。Seedance 支持首帧、首尾帧和参考图。'
    by_id['ark']['docs_url']='https://docs.volcengine.com/docs/ark/model-release-announcement?lang=zh'
    # Profile URLs apply when selecting a provider/type, never from remote model data.
    by_id['dashscope']['profiles']={k:{'base_url':'https://dashscope.aliyuncs.com/api/v1',
        'note':'万相 / Qwen 媒体使用 DashScope 原生入口。此专用媒体协议待适配，请查看官方文档或使用提供相应模型的兼容平台。'} for k in ('image','video','audio')}
    by_id['cohere']['profiles']={'audio':{'note':'此目录为 Cohere Transcribe 语音识别；当前语音合成工作台不支持识别任务。'}}
    # Keep unimplemented vendor APIs explicit; no blank custom form disguised
    # as a ready native adapter.
    for p in presets:
        p['profiles']=p.get('profiles',{})
        for kind in p['model_types']:
            profile=p['profiles'].setdefault(kind,{})
            profile.setdefault('base_url',p['base_url'])
            profile.setdefault('protocol',p['protocols'].get(kind))
            profile.setdefault('note',p.get('note',''))
            profile['family']=p['families'].get(kind,'按账户返回目录选择')
            profile['status']='ready' if profile['protocol'] else 'pending'
    presets.sort(key=lambda p:({'domestic':0,'international':1,'hosted':2,'gateway':3,'local':4,'custom':5}[p['category']],p['id']))
