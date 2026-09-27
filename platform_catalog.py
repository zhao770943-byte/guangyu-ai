"""Public connection presets; a preset is not proof of account/model access.

Addresses and listing support were checked against the linked provider docs.
Model names are never used to route a credential to a different platform.
"""
from copy import deepcopy

PRESETS = [
    {'id': 'openai', 'name': 'OpenAI', 'base_url': 'https://api.openai.com/v1',
     'protocols': {'chat': 'openai_chat', 'image': 'openai_image', 'video': 'openai_video'},
     'discovery_protocol': 'openai', 'note': '读取平台返回的模型列表；列表可见不代表已开通所有用途。',
     'docs_url': 'https://developers.openai.com/api/reference/resources/models/methods/list'},
    {'id': 'anthropic', 'name': 'Anthropic / Claude', 'base_url': 'https://api.anthropic.com/v1',
     'protocols': {'chat': 'anthropic'}, 'discovery_protocol': 'anthropic',
     'note': '使用 Anthropic 原生鉴权与模型列表。',
     'docs_url': 'https://platform.claude.com/docs/en/api/models/list'},
    {'id': 'gemini', 'name': 'Google Gemini', 'base_url': 'https://generativelanguage.googleapis.com/v1beta',
     'protocols': {'chat': 'gemini', 'image': 'gemini'}, 'discovery_protocol': 'gemini',
     'note': '读取模型及支持的方法；Veo 专有视频协议需单独适配。',
     'docs_url': 'https://ai.google.dev/api/models'},
    {'id': 'deepseek', 'name': 'DeepSeek', 'base_url': 'https://api.deepseek.com',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '预设使用兼容 Chat Completions 的答疑接口。',
     'docs_url': 'https://api-docs.deepseek.com/api/list-models/'},
    {'id': 'siliconflow', 'name': '硅基流动 / SiliconFlow', 'base_url': 'https://api.siliconflow.cn/v1',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '列表包含多种模型。预设用于答疑，专有图像/视频接口需使用自定义 JSON 映射。',
     'docs_url': 'https://api-docs.siliconflow.cn/docs/api/models-get'},
    {'id': 'openrouter', 'name': 'OpenRouter', 'base_url': 'https://openrouter.ai/api/v1',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '返回平台模型目录，不等同于账户已获授权或具备余额。图像等专有响应需配置映射。',
     'docs_url': 'https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties'},
    {'id': 'xai', 'name': 'xAI / Grok', 'base_url': 'https://api.x.ai/v1',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '预设用于答疑；图像/视频接口可另建自定义连接。',
     'docs_url': 'https://docs.x.ai/developers/rest-api-reference/inference/models'},
    {'id': 'ollama', 'name': 'Ollama · 本机', 'base_url': 'http://127.0.0.1:11434/v1',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai', 'allow_local': True,
     'note': '需先启动本机 Ollama 并下载模型；通常可留空密钥。',
     'docs_url': 'https://docs.ollama.com/api/openai-compatibility'},
    {'id': 'lmstudio', 'name': 'LM Studio · 本机', 'base_url': 'http://127.0.0.1:1234/v1',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai', 'allow_local': True,
     'note': '需先开启 LM Studio 本机服务；若开启鉴权，请填写对应密钥。',
     'docs_url': 'https://lmstudio.ai/docs/developer/openai-compat/models'},
    {'id': 'moonshot', 'name': '月之暗面 / Kimi', 'base_url': 'https://api.moonshot.cn/v1',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'openai',
     'note': '读取 Kimi 账户模型列表；使用兼容 Chat Completions 的答疑接口。',
     'docs_url': 'https://platform.kimi.com/docs/api/list-models'},
    {'id': 'dashscope', 'name': '阿里云百炼 / 通义千问', 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'unsupported',
     'note': '此兼容入口不提供 GET /models，请从控制台复制模型 ID。新工作空间请使用控制台专属基础地址。',
     'docs_url': 'https://help.aliyun.com/en/model-studio/deepseek-harness'},
    {'id': 'zhipu', 'name': '智谱 / GLM', 'base_url': 'https://open.bigmodel.cn/api/paas/v4',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'unsupported',
     'note': '已填写答疑接口地址；通用模型列表接口尚未核验，请从平台复制模型 ID。',
     'docs_url': 'https://docs.bigmodel.cn/cn/guide/start/quick-start'},
    {'id': 'minimax', 'name': 'MiniMax', 'base_url': 'https://api.minimax.cn/v1',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'unsupported',
     'note': '预设用于答疑；通用模型列表接口尚未核验，请从平台复制模型 ID。视频等接口需单独配置。',
     'docs_url': 'https://platform.minimax.cn/docs/api-reference/text-openai-api'},
    {'id': 'ark', 'name': '火山方舟 / 豆包', 'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
     'protocols': {'chat': 'openai_chat'}, 'discovery_protocol': 'unsupported',
     'note': '模型管理列表使用独立签名接口。请填写控制台模型 ID 或推理接入点 ID。',
     'docs_url': 'https://docs.volcengine.com/docs/ark/compatible-with-openai-sdk?lang=zh'},
    {'id': 'custom', 'name': '其他平台 / 自定义地址', 'base_url': '',
     'protocols': {'chat': 'openai_chat', 'image': 'openai_image', 'video': 'openai_video'},
     'discovery_protocol': 'auto', 'note': '兼容接口可读取 /models；专有 JSON 接口可设置列表路径或手动填写模型。',
     'docs_url': ''},
]


def get_preset(preset_id):
    return deepcopy(next((item for item in PRESETS if item['id'] == preset_id), None))


def list_presets():
    return deepcopy(PRESETS)
