# 平台地址与模型发现依据

核对日期：2026-09-28。下表记录官方文档中的 API 前缀与模型列表方式，供预设维护与手动接入使用；不包含任何账号密钥。实际能力、地区与权限可能变化，以链接中的官方文档和你账号的返回结果为准。

“模型发现”只读取所选地址的模型目录，不发起生成。目录中出现一个模型不代表账号一定有额度或权限，也不代表本应用已经支持该模型的所有输入／输出协议。无通用列表或未验证列表时，应手动填写模型 ID，不把手填候选伪装成实时发现结果。

应用现提供下列 14 个平台预设：其中 10 个支持列表读取，4 个给出手填指引，另保留“其他平台／自定义地址”。在接入向导第一步选择平台并核对 API 前缀、Key，点击“读取模型”后进入第二步；选中已识别模型后匹配用途与协议，未知模型必须确认用途才能保存。模型发现是有上限的目录读取，不是对全球所有模型 API 的扫描或全面兼容承诺。

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
| OpenRouter | `https://openrouter.ai/api/v1` | `/models` | Bearer；目录包含输入／输出模态等属性，不等于账号调用授权 | [模型目录](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties) |
| xAI | `https://api.x.ai/v1` | `/models` | Bearer；还有独立语言／图像／视频模型列表端点 | [Models](https://docs.x.ai/developers/rest-api-reference/inference/models)、[接入](https://docs.x.ai/developers/quickstart) |
| Ollama 本机 | `http://127.0.0.1:11434/v1` | `/models` | 本机默认忽略 API Key；需先运行 Ollama 并准备模型 | [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility) |
| LM Studio 本机 | `http://127.0.0.1:1234/v1` | `/models` | 默认不要求鉴权；启用认证后填写 Bearer Token。需先启动本机服务，列表可能包含支持即时加载的已下载模型 | [List Models](https://lmstudio.ai/docs/developer/openai-compat/models)、[Authentication](https://lmstudio.ai/docs/developer/core/authentication) |

本机 HTTP 连接仍需在光屿 AI 中允许回环 HTTP。表中地址与鉴权按所选平台单独使用；自动识别不能仅凭 Key 的外观决定平台，更不能向多个平台轮流发送同一密钥。

## 提供地址，但需要手动模型 ID 的场景

| 平台 | API 前缀示例 | 本版处理及官方依据 |
| --- | --- | --- |
| 阿里云百炼 / Qwen（中国北京，按量） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 官方说明 OpenAI 兼容入口不提供 `GET /models`，需要手填模型。[列表限制](https://help.aliyun.com/en/model-studio/deepseek-harness) |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | 已确认聊天入口与 Bearer 鉴权；未采用经核对的通用模型列表适配，手填平台模型 ID。[快速开始](https://docs.bigmodel.cn/cn/guide/start/quick-start) |
| MiniMax（中国区） | `https://api.minimax.cn/v1` | 官方 OpenAI 兼容页提供此地址；未采用经核对的模型列表适配，手填模型 ID。[OpenAI SDK](https://platform.minimax.cn/docs/api-reference/text-openai-api) |
| 火山方舟 | `https://ark.cn-beijing.volces.com/api/v3` | 聊天使用兼容入口；基础模型列表另属管控面 API，本应用未集成该签名流程，手填 Model ID 或适用的 Endpoint ID。[兼容说明](https://docs.volcengine.com/docs/ark/compatible-with-openai-sdk?lang=zh)、[管控模型列表](https://api.volcengine.com/api-explorer/?action=ListFoundationModels&serviceCode=ark&version=2024-01-01) |

百炼目前推荐工作空间专属域名，例如 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`；传统域名仍可用。地区与计费计划的 Key 和地址不能混用，应按自己的控制台配置。[域名迁移说明](https://help.aliyun.com/en/model-studio/compatibility-with-openai-responses-api)、[计费入口说明](https://help.aliyun.com/en/model-studio/token-plan-team-quickstart)

上述中国区地址不是其他地区或订阅套餐的通用入口。MiniMax 文档当前使用 `api.minimax.cn`；旧品牌域名或代理地址是否可用需独立确认。本应用不会在未告知的情况下跨域更换地址并转发密钥。

## 代理、兼容服务与自定义协议

第三方代理可能只支持部分 OpenAI 路径，也可能使用不同认证方式和模型命名。优先填写其文档提供的完整 API 前缀；如果使用模型发现映射，应核对列表路径、数组字段和模型 ID 字段。列表成功只证明该列表请求成功。

“OpenAI 兼容”不自动意味着图片编辑或视频协议兼容。比如图像输出可能经由 Chat Completions，视频可能需要 JSON 异步任务；选择错适配器时，模型虽然能列出也不能正确生成。没有匹配协议时使用自定义 JSON 或新增适配器，保留手动模型 ID 入口。
