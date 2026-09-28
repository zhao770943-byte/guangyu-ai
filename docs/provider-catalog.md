# 平台地址与模型发现依据

核对日期：2026-09-28。下表记录官方文档中的 API 前缀与模型列表方式，供预设维护与目录配置使用；不包含任何账号密钥。实际能力、地区与权限可能变化，以链接中的官方文档和你账号的返回结果为准。

“模型发现”只读取所选地址的模型目录，不发起生成。目录中出现一个模型不代表账号一定有额度或权限，也不代表本应用已经支持该模型的所有输入／输出协议。新连接从返回的目录选择模型；没有目录或获取失败时显示实际错误；MiniMax 图像和语音另提供需要主动打开的官方公开型号清单，并标注尚未验证账户权限。

应用现提供 23 个厂商及本机服务预设，另保留“其他平台／自定义地址”。新增平台与类型筛选规则见 [厂商目录与接入步骤](provider-selection.md)。所有预设都允许点击“一键获取模型”，按实际填写的地址请求目录，不因平台名称提前阻断。第一步选择模型类型，第二步核对厂商、API 前缀与 Key 并获取，第三步搜索、选择同类型模型；选中已识别模型后匹配用途与协议，未知模型必须确认用途才能保存。模型发现是有上限的目录读取，不是对全球所有模型 API 的扫描或全面兼容承诺。

## 官方 API Key 与本机服务入口

选择平台后，向导会提供下列官方链接，并在新标签页打开。多数密钥页面需要先登录；应用不代为注册、创建密钥或购买额度。自定义平台没有预设链接，请使用服务商自己的入口。下表按官方文档与页面核对，未登录账户或读取任何真实密钥。

| 平台 | 官方入口 |
| --- | --- |
| OpenAI | [获取 API Key](https://platform.openai.com/api-keys) |
| Anthropic / Claude | [获取 API Key](https://platform.claude.com/settings/keys) |
| Google Gemini | [获取 API Key](https://aistudio.google.com/api-keys) |
| DeepSeek | [获取 API Key](https://platform.deepseek.com/api_keys) |
| 硅基流动 / SiliconFlow | [获取 API Key](https://cloud.siliconflow.cn/account/ak) |
| 月之暗面 / Kimi | [获取 API Key](https://platform.kimi.com/console/api-keys) |
| OpenRouter | [获取 API Key](https://openrouter.ai/settings/keys) |
| xAI / Grok | [获取 API Key](https://console.x.ai/team/default/api-keys) |
| 阿里云百炼 / 通义千问 | [获取 API Key](https://bailian.console.aliyun.com/cn-beijing/model/settings/api-key) |
| 智谱 / GLM | [获取 API Key](https://bigmodel.cn/usercenter/proj-mgmt/apikeys) |
| MiniMax | [获取 API Key](https://platform.minimax.cn/user-center/basic-information/interface-key) |
| 火山方舟 / 豆包 | [获取 API Key](https://console.volcengine.com/ark/apiKey) |
| Ollama | [下载本机服务](https://ollama.com/download) |
| LM Studio | [下载本机服务](https://lmstudio.ai/download) |

## 已核对模型列表端点

下表路径是拼接在 API 前缀后的相对路径；`Bearer` 指请求头 `Authorization: Bearer <API Key>`。

| 平台 | API 前缀 | 模型列表 GET 路径 | 鉴权及说明 | 官方依据 |
| --- | --- | --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `/models` | Bearer；返回 `data` | [Models API](https://developers.openai.com/api/reference/resources/models/methods/list) |
| Anthropic | `https://api.anthropic.com/v1` | `/models` | `x-api-key` 与 `anthropic-version: 2023-06-01`；`has_more`、`last_id` 与 `after_id` 分页 | [List Models](https://platform.claude.com/docs/en/api/models/list) |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta` | `/models` | `x-goog-api-key`；`nextPageToken` 与 `pageToken` 分页，返回名称含 `models/` 前缀 | [Models](https://ai.google.dev/api/models)、[API Key](https://ai.google.dev/gemini-api/docs/api-key) |
| DeepSeek | `https://api.deepseek.com` | `/models` | Bearer；返回模型 ID 与元数据 | [接入](https://api-docs.deepseek.com/guides/harness)、[模型列表](https://api-docs.deepseek.com/api/list-models/) |
| SiliconFlow 硅基流动 | `https://api.siliconflow.cn/v1` | `/models` | Bearer；可按 `type` 和 `sub_type` 筛选 | [获取用户模型列表](https://api-docs.siliconflow.cn/docs/api/models-get) |
| Moonshot / Kimi | `https://api.moonshot.cn/v1` | `/models` | Bearer；返回 `data` | [列出模型](https://platform.kimi.com/docs/api/list-models)、[API 概述](https://platform.kimi.com/docs/api/overview) |
| MiniMax（中国区） | `https://api.minimax.cn/v1` | `/models` | Bearer；返回 `data`，公开模型结构为 `id`、`object`、`created`、`owned_by`，未声明输出模态字段 | [模型列表](https://platform.minimax.cn/docs/api-reference/models/openai/list-models)、[模型详情](https://platform.minimax.cn/docs/api-reference/models/openai/retrieve-model) |
| OpenRouter | `https://openrouter.ai/api/v1` | `/models` | Bearer；目录包含输入／输出模态等属性，不等于账号调用授权 | [模型目录](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties) |
| xAI | `https://api.x.ai/v1` | `/models` | Bearer；还有独立语言／图像／视频模型列表端点 | [Models](https://docs.x.ai/developers/rest-api-reference/inference/models)、[接入](https://docs.x.ai/developers/quickstart) |
| Ollama 本机 | `http://127.0.0.1:11434/v1` | `/models` | 本机默认忽略 API Key；需先运行 Ollama 并准备模型 | [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) |
| LM Studio 本机 | `http://127.0.0.1:1234/v1` | `/models` | 默认不要求鉴权；启用认证后填写 Bearer Token。需先启动本机服务，列表可能包含支持即时加载的已下载模型 | [List Models](https://lmstudio.ai/docs/developer/openai-compat/models)、[Authentication](https://lmstudio.ai/docs/developer/core/authentication) |

本机 HTTP 连接仍需在光屿 AI 中允许回环 HTTP。表中地址与鉴权按所选平台单独使用；自动识别不能仅凭 Key 的外观决定平台，更不能向多个平台轮流发送同一密钥。

## 模型目录需按实际入口确认的平台

下列预设仍会尝试当前地址的 `/models`，也可配置服务商提供的其他目录路径。官方入口可能不提供模型列表，代理或专属地址的行为也可能不同；应以实际响应为准。请求失败时检查配置后重试，不能据此认定其生成接口不可用。

| 平台 | API 前缀示例 | 本版处理及官方依据 |
| --- | --- | --- |
| 阿里云百炼 / Qwen（中国北京，按量） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 官方说明此 OpenAI 兼容入口不提供 `GET /models`；本应用仍对实际填写的地址发起目录请求。[列表限制](https://help.aliyun.com/en/model-studio/deepseek-harness) |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | 已确认聊天入口与 Bearer 鉴权，尚无经核对的通用目录支持承诺；按当前地址实际尝试。[快速开始](https://docs.bigmodel.cn/cn/guide/start/quick-start) |
| 火山方舟 | `https://ark.cn-beijing.volces.com/api/v3` | 聊天使用兼容入口；官方基础模型列表另属管控面 API，本应用未集成其签名流程。兼容入口的目录按实际响应处理。[兼容说明](https://docs.volcengine.com/docs/ark/compatible-with-openai-sdk?lang=zh)、[管控模型列表](https://api.volcengine.com/api-explorer/?action=ListFoundationModels&serviceCode=ark&version=2024-01-01) |

百炼目前推荐工作空间专属域名，例如 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`；传统域名仍可用。地区与计费计划的 Key 和地址不能混用，应按自己的控制台配置。[域名迁移说明](https://help.aliyun.com/en/model-studio/compatibility-with-openai-responses-api)、[计费入口说明](https://help.aliyun.com/en/model-studio/token-plan-team-quickstart)

上述中国区地址不是其他地区或订阅套餐的通用入口。MiniMax 文档当前使用 `api.minimax.cn`；旧品牌域名或代理地址是否可用需独立确认。本应用不会在未告知的情况下跨域更换地址并转发密钥。

MiniMax 的模型列表能确认模型 ID，不能据此推断图像输出能力。官方将 `MiniMax-M3` 列为支持图片／视频输入的 Chat Completions 模型；本应用应将其用于 AI 助手。中国区文生图接口支持 `image-01`、`image-01-live`，使用 `/image_generation`，不是 OpenAI Images 的 `/images/generations`。[M3 输入与聊天接口](https://platform.minimax.cn/docs/api-reference/text-openai-api)、[文生图接口](https://platform.minimax.cn/docs/api-reference/image-generation-t2i)

## 代理、兼容服务与自定义协议

第三方代理可能只支持部分 OpenAI 路径，也可能使用不同认证方式和模型命名。优先填写其文档提供的完整 API 前缀；如果使用模型发现映射，应核对列表路径、数组字段和模型 ID 字段。列表成功只证明该列表请求成功。

“OpenAI 兼容”不自动意味着图片编辑或视频协议兼容。比如图像输出可能经由 Chat Completions，视频可能需要 JSON 异步任务；选择错适配器时，模型虽然能列出也不能正确生成。没有匹配协议时使用自定义 JSON 或新增适配器；新增连接仍从获取到的目录选择模型。
