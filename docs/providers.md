# 接口接入指南

在“模型接入”页面点击“接入模型”添加连接。一个连接对应一个用途、一种协议和一个模型；同一平台的图像、视频与语言模型可以分别保存。

常用服务的 API 前缀、模型列表路径和认证差异见 [平台地址与模型发现依据](provider-catalog.md)。目录列出了经官方文档核对的端点；列表可见不等于账号有额度，也不等于本应用支持模型的全部生成协议。

## 类型、厂商、型号

1. **选择类型**：文本、音频、图像、视频。以输出用途分类，多模态输入不等于能够生成图像或视频。
2. **连接厂商**：按类型列出厂商，自动填入 API 基础地址，提供官方密钥页面直达链接。填写 Key 后点击“一键获取模型”。自定义地址、目录协议、认证与回环 HTTP 在连接选项中配置。
3. **选择型号**：只显示已识别为当前类型的目录条目。选择型号保持类型不变，并匹配已适配协议及请求路径。未知类型默认隐藏，可主动展开并确认类型；缺少原生适配器时使用自定义 JSON 映射。

目录读取是显式 GET 操作，不提交生成、不自动保存新密钥。真实目录为空或错误时显示实际结果。OpenAI、Google、火山方舟、MiniMax 等另提供按官方文档维护的公开型号清单，需主动点击“选择官方公开型号”；界面明确提示未验证当前密钥权限，不会冒充账户返回结果。

模型分类与协议支持分开记录。语音合成、语音识别、实时语音、音频对话不会混用；目前原生音频适配器只支持语音合成。其他音频子类型标记“待适配”，不允许通过语音合成界面提交。

切换类型会重新选择型号。切换厂商或修改基础地址会清空输入密钥；保存的密钥只有同地址编辑时允许留空复用。模型返回的域名不会覆盖用户选择的基础地址。

目录上限为 10 页、1000 个模型，单页最多 4 MiB、累计最多 12 MiB；单次 GET 超时 15 秒，整次逻辑预算 45 秒。达到上限时会提示部分结果。平台是否提供目录和模型权限以账户的实际响应为准。

## 基础信息

| 字段 | 填写方式 |
| --- | --- |
| 名称 | 方便自己识别的平台与模型名称 |
| 用途 | 文本、音频、图像或视频 |
| 协议 | 预设与已识别模型会匹配协议；仍需核对平台实际支持的接口，未知模型需主动确认 |
| API 基础地址 | 平台 API 前缀，例如 `https://api.example.com/v1`；不要重复填写 `/chat/completions` 等路径 |
| 模型 ID | 从目录所选条目自动带入，不一定等于网页展示名称，无需手填 |
| API Key | 自己的密钥；编辑已保存连接且地址未变时，留空可复用原密钥 |

保存配置不会自动生成。“一键获取模型”或管理表格中的“获取模型”只验证列表端点请求，不能证明具体模型具有生成权限或可用额度。自定义 JSON 接口可指定模型列表相对路径；未填写时尝试 `/models`。“已接入”表示配置已保存。

## 管理已有模型

“模型接入”使用表格显示连接名称、模型 ID、基础地址、用途与协议，可按文本、音频、图像、视频筛选，并搜索名称、ID 或地址。每行提供“获取模型”、编辑和移除操作；点击“获取模型”会直接打开向导并读取该连接的目录。

点击“编辑”会直接打开第三步，保留当前模型与连接名称，即使原模型暂未出现在目录中也可继续编辑；需要修改平台、Key 或地址时返回第二步。修改地址后需重新填写对应密钥并重新获取模型。管理页底部可前往“模型与用量”查看保存的调用记录。

## 内置协议与高级能力

| 适配器 | 用途 | 本实现的高级输入 |
| --- | --- | --- |
| OpenAI Images | 图像 | 已识别 GPT Image 系列参考图、质量、张数、背景；DALL·E 2 单张编辑；DALL·E 3 质量 |
| MiniMax 图像 | 图像 | `/image_generation`，画幅比例与张数；返回图片链接 |
| OpenAI Speech | 音频 | `/audio/speech`，音色与语速，WAV 本机保存 |
| MiniMax 语音 | 音频 | `/t2a_v2`，音色与语速，返回音频链接 |
| OpenAI Videos | 视频 | 首帧；没有原生尾帧控制 |
| OpenAI Chat Completions / Responses | 助手 | 多轮文本、应用说明与用户选择的草稿上下文 |
| Anthropic Messages | 助手 | 多轮文本与系统说明 |
| Gemini generateContent | 图像／助手 | 图像参考输入；已识别图像型号的宽高比、Gemini 3 图像型号的分辨率 |
| 自定义 JSON | 四种用途 | 根据实际请求模板声明和映射能力 |

上表描述应用的适配行为，不保证供应商当前向你的账号开放该功能。兼容平台若使用不同字段，请选择自定义映射或增加适配器。未识别的 OpenAI Images 兼容模型仅开放基础控制。

输入图片支持静态 PNG、JPEG、WebP，每张最多 10 MiB、4000 万像素，最多 8 张参考图。OpenAI 视频首帧须匹配目标尺寸；DALL·E 2 编辑须单张、小于 4 MiB 的正方形 PNG。工作台不会暗中裁剪或拉伸图片。

## MiniMax 模型用途与接口

`MiniMax-M3` 在本应用中应配置为 **AI 助手 → OpenAI Chat Completions**，API 基础地址为 `https://api.minimax.cn/v1`。官方文档描述的图片、视频能力是多模态输入，用于理解内容；聊天结果从 `choices[].message.content` 读取，不应把该模型配置为 OpenAI Images。当前助手界面提供多轮文本输入，供应商支持的其他输入能力需要应用另外适配。[MiniMax OpenAI SDK 文档](https://platform.minimax.cn/docs/api-reference/text-openai-api)

MiniMax 中国区文生图接口列出的模型为 `image-01` 和 `image-01-live`，使用 Bearer 鉴权与 `POST /image_generation` JSON 请求。它的路径和响应结构与 OpenAI Images 不同：图片 URL 位于 `data.image_urls`，Base64 图片位于 `data.image_base64`，还需检查 `base_resp.status_code` 是否为 `0`。本版已内置 MiniMax 图像适配器，自动使用此路径、解析图片 URL 并检查业务状态；不能仅更换模型 ID 沿用 OpenAI Images。[MiniMax 文生图接口](https://platform.minimax.cn/docs/api-reference/image-generation-t2i)、[图片生成指南](https://platform.minimax.cn/docs/guides/image-generation)

国际站文生图文档使用 `https://api.minimax.io/v1/image_generation`，目前只列出 `image-01`。应按账号所在站点核对模型与地址，不自动跨站切换密钥。[国际站文生图接口](https://platform.minimax.io/docs/api-reference/image-generation-t2i)

官方 `GET /models` 与 `GET /models/{model_id}` 提供模型身份字段，公开结构未声明输出模态；列表包含 M3 并不意味着它可以生图。账户目录不含图像和语音时，可以主动打开单独标注的官方公开清单；是否有权限仍以账户为准。[模型列表](https://platform.minimax.cn/docs/api-reference/models/openai/list-models)、[模型详情](https://platform.minimax.cn/docs/api-reference/models/openai/retrieve-model)

## 音频接口

OpenAI Speech 使用 `POST /audio/speech`，传递 `model/input/voice/speed/response_format=wav`，文本最多 4096 字符，语速 0.25–4；响应二进制 WAV 保存到本机媒体目录供播放和下载。没有 JSON 用量时保留未知 Token。[OpenAI 官方接口](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create)

MiniMax 同步语音使用 `POST /t2a_v2`，传递 `model/text/stream=false`、`voice_setting`、`audio_setting` 和 `output_format=url`；文本少于 10000 字符，语速 0.5–2。解析 `data.audio`，并检查 `base_resp.status_code`。平台返回的临时链接可能过期。[MiniMax 同步语音文档](https://platform.minimax.cn/docs/api-reference/speech-t2a-http)

上述原生适配器不实现转写、实时通话和音乐生成。自定义 JSON 音频支持媒体 URL 与 GET 轮询，需要按平台文档映射。

## 自定义 JSON

“高级参数与映射”中的“模型列表路径”（`discovery_path`）可指定自定义模型列表相对路径，例如 `/models` 或 `/catalog/models`，未填写时尝试 `/models`。第一步也可以从“连接选项 → 自定义认证与列表路径”打开配置。地址相对于当前 API 基础地址拼接，不接受查询字符串；它必须返回 JSON 对象中的 `data`、`models` 或 `items` 数组，模型项使用 `id` 或 `name` 字段。不能填写跨域绝对 URL，也不会跨域跟随重定向。没有符合结构的列表接口时会提示错误，需调整目录配置后重新获取。

独立目录协议保存在 `custom.discovery_protocol`，可选 `openai_chat`（OpenAI 兼容）、`anthropic`、`gemini` 或 `custom`。它仅控制目录读取；生成仍使用连接的 `protocol`。自定义目录的认证头和前缀由对应高级字段设置，保存后重新打开或从管理表格读取目录时会复用这份配置。

例如，虚构平台的 `/catalog/models` 可以返回：

```json
{
  "data": [
    {"id": "your-chat-model", "name": "你的答疑模型"},
    {"id": "your-image-model", "name": "你的图像模型"}
  ]
}
```

这些示例 ID 没有真实平台含义。未识别用途的条目仍需主动确认用途和协议；不会根据名称自动保证图像或视频可用。

支持 POST JSON、可选 GET 轮询、单个认证请求头，以及文本、Base64 图片或可直接访问的媒体 URL。首尾帧使用 data URI，参考图使用 data URI 数组。复杂签名、多个认证头、SDK、WebSocket、分阶段上传、任意 multipart 模板或鉴权媒体下载需要新增适配器。

可映射变量包括 `{{model}}`、`{{prompt}}`、`{{messages}}`、`{{system}}`、`{{size}}`、`{{seconds}}`、`{{first_frame}}`、`{{last_frame}}`、`{{reference_images}}`，以及高级参数的同名变量；批量张数使用 `{{n}}`。

能力需同时满足：平台支持、配置中声明开启、最终请求模板引用对应变量。尺寸／时长没有模板映射时不会开放控制。变量独占 JSON 字符串值时保留原始类型，例如 `"seed":"{{seed}}"` 会得到整数。

完整的虚构请求模板、轮询字段和 Token 字段映射示例见 [使用说明：自定义 JSON 接入示例](../使用说明.md#自定义-json-接入示例)。不要把示例当作某个供应商可直接使用的配置，也不要将 API Key 写入模板、附加 JSON 或 URL。

## 用量字段

内置适配器将平台已返回的用量统一为输入、输出、总量、缓存输入与推理输出。自定义协议可配置 `usage_paths`；没有映射时会识别常见 `usage.input_tokens/output_tokens` 或 `usage.prompt_tokens/completion_tokens`。

未返回字段保持未知；缓存和推理是子集，不能再次加到总量。用量来源仅限此应用保存的响应，不包含其他程序，也不等于平台账单。平台不返回 Token 的图像／视频服务仍可使用，相关 Token 字段显示 `—`。


## 本地 MiniMax H3 / ComfyUI

选择视频 → 本地 MiniMax H3 / ComfyUI → 一键获取模型。仅允许本机回环 HTTP 根地址（默认 `http://127.0.0.1:8188`），不需要云端 API Key。适配已安装的 W4A8、Qwen3-VL 4B 和匹配 ClipProj 工作流，检查模型文件名和节点目录，实际生成仍需本机资源足够。

首帧必填，可选尾帧。默认画幅跟随首帧，按工作流要求对齐 32 像素；首尾帧都先等比居中裁切再传入 H3，避免将竖图直接拉伸为横图。手动改横竖画幅可能裁掉主体，界面会提示。

| 档位 | 横屏 / 竖屏像素 | 可选时长 |
| --- | --- | --- |
| 细节优先（默认） | 864×480 / 480×864 | 约 5、7 秒 |
| 快速预览 | 608×352 / 352×608 | 约 5、7、10、15 秒 |

自动跟随首帧时实际尺寸可能不同。固定 24 FPS、20 步，帧数为 124 / 175 / 243 / 362，对应约 5.17 / 7.29 / 10.13 / 15.08 秒。10 / 15 秒选择会切换到预览档并提示，8GB 细节档不开放长片组合；可用系统内存、其他 GPU 任务也会影响能否完成。

目前此适配器输出静音视频，只接收首帧和可选尾帧。它不会读取提示词提及的四张分镜图，也不会把提示词中的“30 秒”变为实际时长。每次使用一个连续动作的镜头描述；多镜头广告需分段生成和剪辑，声音在后期添加。不要把本机量化低显存配置视为云端全规格模型的画质保证。

视频下载后读取文件实际宽高和时长，不使用请求参数伪造结果。已保存的本地视频通过 PyAV 提取 JPEG 封面，旧作品首次查看时同样生效；封面提取不调用模型、不修改视频或用量记录。

2026-09-29 本机验收：RTX 5060 Laptop 8GB / 16GB RAM，以竖版人物首帧和单一连续动作提示词生成 480×864、175 帧、24 FPS 视频，实际约 7.29 秒，耗时约 13 分 40 秒。全部帧解码通过；检查 7 处抽帧，未再出现原先的横向拉伸。此结果不代表完整播放质量评审、10 / 15 秒各档实测或其他电脑性能。
