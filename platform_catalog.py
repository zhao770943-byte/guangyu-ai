"""Public connection presets; a preset is not proof of account/model access.

Addresses and listing support were checked against the linked provider docs.
Model names are never used to route a credential to a different platform.
"""
from copy import deepcopy

PRESETS = [
    {'id':'weijin','name':'维今 / ONE API','base_url':'https://www.weijinapi.top/v1',
     'api_key_url':'https://www.weijinapi.top/','api_key_label':'获取 API Key',
     'protocols':{'chat':'openai_chat','image':'openai_image','video':'weijin_video'},
     'discovery_protocol':'openai','note':'视频使用维今 JSON 接口；时长和画幅按所选型号，目录可见不代表生成已验证。',
     'docs_url':'https://www.weijinapi.top/docs/'},
    {'id': 'openai', 'name': 'OpenAI', 'base_url': 'https://api.openai.com/v1',
     'api_key_url': 'https://platform.openai.com/api-keys', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat', 'image': 'openai_image', 'video': 'openai_video'},
     'discovery_protocol': 'openai', 'note': '读取平台返回的模型列表；列表可见不代表已开通所有用途。',
     'docs_url': 'https://developers.openai.com/api/reference/resources/models/methods/list'},
    {'id': 'anthropic', 'name': 'Anthropic / Claude', 'base_url': 'https://api.anthropic.com/v1',
     'api_key_url': 'https://platform.claude.com/settings/keys', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'anthropic'}, 'discovery_protocol': 'anthropic',
     'note': '使用 Anthropic 原生鉴权与模型列表。',
     'docs_url': 'https://platform.claude.com/docs/en/api/models/list'},
    {'id': 'gemini', 'name': 'Google Gemini', 'base_url': 'https://generativelanguage.googleapis.com/v1beta',
     'api_key_url': 'https://aistudio.google.com/api-keys', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'gemini', 'image': 'gemini'}, 'discovery_protocol': 'gemini',
     'note': '读取模型及支持的方法；Veo 专有视频协议需单独适配。',
     'docs_url': 'https://ai.google.dev/api/models'},
    {'id': 'deepseek', 'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com',
     'api_key_url': 'https://platform.deepseek.com/api_keys', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '预设使用兼容 Chat Completions 的答疑接口。',
     'docs_url': 'https://api-docs.deepseek.com/api/list-models/'},
    {'id': 'siliconflow', 'name': '硅基流动 / SiliconFlow', 'base_url': 'https://api.siliconflow.cn/v1',
     'api_key_url': 'https://cloud.siliconflow.cn/account/ak', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '列表包含多种模型。预设用于答疑，专有图像/视频接口需使用自定义 JSON 映射。',
     'docs_url': 'https://api-docs.siliconflow.cn/docs/api/models-get'},
    {'id': 'openrouter', 'name': 'OpenRouter', 'base_url': 'https://openrouter.ai/api/v1',
     'api_key_url': 'https://openrouter.ai/settings/keys', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '返回平台模型目录，不等同于账户已获授权或具备余额。图像等专有响应需配置映射。',
     'docs_url': 'https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties'},
    {'id': 'xai', 'name': 'xAI / Grok', 'base_url': 'https://api.x.ai/v1',
     'api_key_url': 'https://console.x.ai/team/default/api-keys', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '预设用于答疑；图像/视频接口可另建自定义连接。',
     'docs_url': 'https://docs.x.ai/developers/rest-api-reference/inference/models'},
    {'id': 'ollama', 'name': 'Ollama · 本机', 'base_url': 'http://127.0.0.1:11434/v1',
     'api_key_url': 'https://ollama.com/download', 'api_key_label': '下载本机服务',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai', 'allow_local': True,
     'note': '需先启动本机 Ollama 并下载模型；通常可留空密钥。',
     'docs_url': 'https://docs.ollama.com/api/openai-compatibility'},
    {'id': 'lmstudio', 'name': 'LM Studio · 本机', 'base_url': 'http://127.0.0.1:1234/v1',
     'api_key_url': 'https://lmstudio.ai/download', 'api_key_label': '下载本机服务',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai', 'allow_local': True,
     'note': '需先开启 LM Studio 本机服务；若开启鉴权，请填写对应密钥。',
     'docs_url': 'https://lmstudio.ai/docs/developer/openai-compat/models'},
    {'id': 'moonshot', 'name': '月之暗面 / Kimi', 'base_url': 'https://api.moonshot.cn/v1',
     'api_key_url': 'https://platform.kimi.com/console/api-keys', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '读取 Kimi 账户模型列表；使用兼容 Chat Completions 的答疑接口。',
     'docs_url': 'https://platform.kimi.com/docs/api/list-models'},
    {'id': 'dashscope', 'name': '阿里云百炼 / 通义千问', 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
     'api_key_url': 'https://bailian.console.aliyun.com/cn-beijing/model/settings/api-key', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai', 'discovery_status': 'probe',
     'note': '此兼容入口可能不提供模型目录；一键获取将检查当前地址的实际响应。专属工作空间请使用对应基础地址。',
     'docs_url': 'https://help.aliyun.com/en/model-studio/deepseek-harness'},
    {'id': 'zhipu', 'name': '智谱 / GLM', 'base_url': 'https://open.bigmodel.cn/api/paas/v4',
     'api_key_url': 'https://bigmodel.cn/usercenter/proj-mgmt/apikeys', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai', 'discovery_status': 'probe',
     'note': '将尝试读取当前地址的模型目录；能否获取模型以平台实际响应为准。',
     'docs_url': 'https://docs.bigmodel.cn/cn/guide/start/quick-start'},
    {'id': 'minimax', 'name': 'MiniMax', 'base_url': 'https://api.minimax.cn/v1',
     'api_key_url': 'https://platform.minimax.cn/user-center/basic-information/interface-key', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai', 'discovery_status': 'documented',
     'note': '官方提供 /models。MiniMax-M3 用于答疑与视觉理解；生图需 image-01 系列和专有接口，不能使用 OpenAI Images。',
     'docs_url': 'https://platform.minimax.cn/docs/api-reference/models/openai/list-models'},
    {'id': 'ark', 'name': '火山方舟 / 豆包', 'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
     'api_key_url': 'https://console.volcengine.com/ark/apiKey', 'api_key_label': '获取 API Key',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai', 'discovery_status': 'probe',
     'note': '将尝试读取当前地址的模型目录。若平台要求独立签名接口，会显示实际获取错误。',
     'docs_url': 'https://docs.volcengine.com/docs/ark/compatible-with-openai-sdk?lang=zh'},
    {'id': 'custom', 'name': '其他平台 / 自定义地址', 'base_url': '',
     'api_key_url': '', 'api_key_label': '',
     'protocols': {'chat': 'openai_chat', 'image': 'openai_image', 'video': 'openai_video'},
     'discovery_protocol': 'auto', 'note': '默认读取当前地址的 /models；专有 JSON 接口可配置目录协议、鉴权和列表路径。',
     'docs_url': ''},
]

# Catalog types describe the vendor directory, not a claim of native protocol
# compatibility. The actual returned model determines its adapter and subtype.
CATALOG_TYPES={
    "weijin":["chat","image","video"],
    'openai':['chat','audio','image','video'], 'anthropic':['chat'],
    'gemini':['chat','audio','image','video'], 'deepseek':['chat'],
    'siliconflow':['chat','audio','image','video'], 'openrouter':['chat','audio','image','video'],
    'xai':['chat','audio','image','video'], 'ollama':['chat'], 'lmstudio':['chat'],
    'moonshot':['chat'], 'dashscope':['chat','audio','image','video'],
    'zhipu':['chat','audio','image','video'], 'minimax':['chat','audio','image','video'],
    'ark':['chat','audio','image','video'], 'custom':['chat','audio','image','video'],
}
for item in PRESETS:
    item['model_types']=CATALOG_TYPES[item['id']]
    if item['id'] in ('openai','custom'):item['protocols']['audio']='openai_speech'
    if item['id']=='minimax':
        item['protocols'].update(image='minimax_image',audio='minimax_speech')
        item['note']='M 系列用于文本；image-01 用于图像；speech 系列用于语音合成。视频与其他音频子类型需要对应适配。'
        item['official_models']=[{'id':name,'name':name,'model_kinds':[kind],'supported_kinds':[kind],
            'model_constraints':{'kinds':[kind]},'protocol':protocol,'source':'official_catalog',
            'audio_task':'speech' if kind=='audio' else ''}
            for kind,protocol,names in [('image','minimax_image',['image-01','image-01-live']),
            ('audio','minimax_speech',['speech-2.8-hd','speech-2.8-turbo','speech-2.6-hd','speech-2.6-turbo','speech-02-hd','speech-02-turbo','speech-01-hd','speech-01-turbo'])]
            for name in names]


def get_preset(preset_id):
    return deepcopy(next((item for item in PRESETS if item['id'] == preset_id), None))


def list_presets():
    return deepcopy(PRESETS)
