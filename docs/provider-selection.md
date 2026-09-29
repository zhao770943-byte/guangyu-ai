# 模型厂商目录与接入步骤

核对日期：2026-09-29。共 43 个选项（含自定义）；按类型分别有 33 个文本、16 个音频、21 个图像、14 个视频入口，不含自定义。数量包含原厂、托管平台及本地服务，不能解读为全部已完成原生协议适配。

选择类型后自动进入第二步。左侧按国内原厂、国际原厂、开源厂商托管、聚合平台、本地服务分组，可以搜索厂商名或模型系列；右侧显示所选厂商的 Key 链接、文档和当前类型的地址。不同模态可使用不同基础地址，地址改变时清空输入的密钥。

点击「一键获取模型」只读取当前账户目录；也可主动点击「选择官方公开型号」，无需手填 ID。官方目录不会被标记成已经验证账户权限，401 等错误不会被假目录掩盖。

## 重点型号与接入状态

- OpenAI：GPT Image 2.5 Sunburst / Flare、GPT Image 2.0；使用 Images 接口。以官方 API ID 保存，不用展示名称代替调用 ID。
- Google：Nano Banana 2 / Pro / Nano Banana，分别使用 `gemini-3.1-flash-image`、`gemini-3-pro-image`、`gemini-2.5-flash-image`。香蕉属于图像生成；Veo / Omni 归视频，专用视频协议待适配。
- 火山方舟：Seedream 5.0 Pro / Flash、4.5 / 4.0；支持文字与参考图生图，保留平台默认画面参数。Seedance 2.5 / 2.0 / 2.0 Fast 原生提交、查询、任务 ID 保存，支持首帧、首尾帧或参考图。2.5 时长 4–30 秒，2.0 为 4–15 秒；不混用参考图与首尾帧。
- xAI：Grok Imagine Image 2.0 生图；Grok Imagine Video 1.5 预置文生视频 JSON 映射及异步查询，时长 1–15 秒。此视频映射未开启参考图功能。
- MiniMax：保留 Image-01 与 Speech 原生适配、本地 H3；云端 Hailuo 专用接口待适配。
- 智谱：CogView-4 图像接口已适配；GLM 文本使用兼容接口，CogVideo 专用接口待适配。
- Luma：Photon / Photon Flash 文生图已预置异步映射；Ray 视频及 CDN 参考图待适配。
- Meta / Microsoft / IBM：明确通过 NVIDIA NIM 托管调用，只显示对应原厂模型；需要 NVIDIA Key，也可通过 Ollama / LM Studio 自行部署。
- BFL、Stability、Runway、可灵、ElevenLabs、Recraft、Ideogram 已补厂商目录、型号系列和官方入口；尚未完成的专用鉴权或响应协议明确标记「专用接口待适配」，不冒充可直接生成。

OpenAI 官方 Sora API 已于 2026-09-24 停止，新增视频厂商不再展示该官方入口。已有连接、历史任务和兼容平台的旧协议保留。火山方舟不把另一个产品的 SeedTTS 音频 API 冒充为相同地址/密钥可用。

## 目录与官方依据

| 厂商 / 平台 | 分组 | 当前入口的类型 | 模型系列 | 官方文档 |
| --- | --- | --- | --- | --- |
| 火山方舟 / 豆包 | 国内原厂 | 文本、图像、视频 | 文本：Doubao Seed / 豆包；图像：Seedream 5 / 4.5 / 4；视频：Seedance 2.5 / 2.0 | [文档](https://docs.volcengine.com/docs/ark/model-release-announcement?lang=zh) |
| 百川智能 | 国内原厂 | 文本 | 文本：Baichuan / 百川 | [文档](https://platform.baichuan-ai.com/docs/api) |
| 百度千帆 / 文心 | 国内原厂 | 文本 | 文本：ERNIE / 文心 | [文档](https://cloud.baidu.com/doc/qianfan-docs/s/Fm9l6ocai) |
| 阿里云百炼 / 通义千问 | 国内原厂 | 文本、音频、图像、视频 | 文本：Qwen / 通义千问；图像：Qwen Image / Wan 万相；音频：Qwen TTS / ASR / Omni；视频：Wan / 万相 / HappyHorse | [文档](https://help.aliyun.com/en/model-studio/deepseek-harness) |
| DeepSeek | 国内原厂 | 文本 | 文本：DeepSeek Chat / Reasoner | [文档](https://api-docs.deepseek.com/api/list-models/) |
| 科大讯飞 / 星火 | 国内原厂 | 文本 | 文本：Spark X2 Flash / 星火 | [文档](https://www.xfyun.cn/doc/spark/X2-Flash.html) |
| 快手 / 可灵 | 国内原厂 | 图像、视频 | 图像：Kolors / 可图；视频：Kling / 可灵 | [文档](https://app.klingai.com/cn/dev/document-api) |
| MiniMax | 国内原厂 | 文本、音频、图像、视频 | 文本：MiniMax M3 / M 系列；图像：Image-01；音频：Speech / Music；视频：Hailuo / MiniMax H3 | [文档](https://platform.minimax.cn/docs/api-reference/models/openai/list-models) |
| 月之暗面 / Kimi | 国内原厂 | 文本 | 文本：Kimi / Moonshot | [文档](https://platform.kimi.com/docs/api/list-models) |
| 阶跃星辰 / StepFun | 国内原厂 | 文本、图像、音频 | 文本：Step 5 / Step 3.7 / Step 3.5；图像：Step Image；音频：StepAudio / TTS / Music / ASR | [文档](https://platform.stepfun.com/docs) |
| 腾讯混元 | 国内原厂 | 文本 | 文本：Hunyuan / 混元 | [文档](https://cloud.tencent.com/document/product/1729/111007) |
| 零一万物 / Yi | 国内原厂 | 文本 | 文本：Yi Lightning / Yi Large | [文档](https://platform.lingyiwanwu.com/docs) |
| 智谱 / GLM | 国内原厂 | 文本、音频、图像、视频 | 文本：GLM / 智谱；图像：CogView / GLM Image；视频：CogVideoX；音频：GLM TTS / ASR / Voice | [文档](https://docs.bigmodel.cn/cn/guide/start/quick-start) |
| Anthropic / Claude | 国际原厂 | 文本 | 文本：Claude Fable / Opus / Sonnet / Haiku | [文档](https://platform.claude.com/docs/en/api/models/list) |
| Black Forest Labs / FLUX | 国际原厂 | 图像 | 图像：FLUX.2 / FLUX.1 Kontext | [文档](https://docs.bfl.ai/quick_start/generating_images) |
| Cohere | 国际原厂 | 文本、音频 | 文本：Command / Aya；音频：Cohere Transcribe | [文档](https://docs.cohere.com/docs/compatibility-api) |
| ElevenLabs | 国际原厂 | 音频 | 音频：Eleven / Scribe / Music | [文档](https://elevenlabs.io/docs/overview/models) |
| Google Gemini | 国际原厂 | 文本、音频、图像、视频 | 文本：Gemini Pro / Flash；图像：Nano Banana 香蕉 / Nano Banana 2 / Pro；音频：Gemini TTS / Live；视频：Veo / Omni | [文档](https://ai.google.dev/api/models) |
| Ideogram | 国际原厂 | 图像 | 图像：Ideogram | [文档](https://developer.ideogram.ai/) |
| Luma AI | 国际原厂 | 图像、视频 | 图像：Photon；视频：Ray | [文档](https://docs.lumalabs.ai/docs/video-generation) |
| Mistral AI | 国际原厂 | 文本、音频 | 文本：Mistral / Codestral / Devstral；音频：Voxtral | [文档](https://docs.mistral.ai/api/endpoint/models) |
| NVIDIA NIM · 托管文本接口 | 国际原厂 | 文本 | 文本：Nemotron / Meta Llama / Microsoft Phi / IBM Granite（托管） | [文档](https://docs.nvidia.com/nim-operator/latest/guardrail.html) |
| OpenAI | 国际原厂 | 文本、音频、图像 | 文本：GPT / o 系列；图像：GPT Image 2.5 Sunburst / Flare · GPT Image 2；音频：GPT TTS / Whisper / Realtime | [文档](https://developers.openai.com/api/reference/resources/models/methods/list) |
| Recraft | 国际原厂 | 图像 | 图像：Recraft | [文档](https://www.recraft.ai/docs) |
| Runway | 国际原厂 | 图像、视频 | 图像：Gen Image；视频：Gen / Aleph / Act | [文档](https://docs.dev.runwayml.com/guides/models/) |
| Stability AI | 国际原厂 | 图像、音频 | 图像：Stable Image / Stable Diffusion；音频：Stable Audio | [文档](https://platform.stability.ai/docs/api-reference) |
| xAI / Grok | 国际原厂 | 文本、音频、图像、视频 | 文本：Grok；图像：Grok Imagine Image；视频：Grok Imagine Video；音频：Grok Voice | [文档](https://docs.x.ai/developers/rest-api-reference/inference/models) |
| IBM · NVIDIA 托管 | 开源厂商 / NVIDIA 托管 | 文本 | 文本：Granite · 开源模型托管入口 | [文档](https://docs.api.nvidia.com/nim/reference/models-1) |
| Meta · NVIDIA 托管 | 开源厂商 / NVIDIA 托管 | 文本 | 文本：Llama · 开源模型托管入口 | [文档](https://docs.api.nvidia.com/nim/reference/models-1) |
| Microsoft · NVIDIA 托管 | 开源厂商 / NVIDIA 托管 | 文本 | 文本：Phi · 开源模型托管入口 | [文档](https://docs.api.nvidia.com/nim/reference/models-1) |
| Cerebras | 聚合与推理平台 | 文本 | 文本：Cerebras 托管文本模型 | [文档](https://inference-docs.cerebras.ai/api-reference/models/list-models) |
| DeepInfra | 聚合与推理平台 | 文本、音频、图像、视频 | 以账户目录为准 | [文档](https://docs.deepinfra.com/models) |
| Fireworks AI | 聚合与推理平台 | 文本、图像 | 以账户目录为准 | [文档](https://docs.fireworks.ai/tools-sdks/openai-compatibility) |
| Groq | 聚合与推理平台 | 文本、音频 | 以账户目录为准 | [文档](https://console.groq.com/docs/api-reference) |
| OpenRouter | 聚合与推理平台 | 文本、音频、图像 | 以账户目录为准 | [文档](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties) |
| SambaNova | 聚合与推理平台 | 文本 | 文本：SambaNova 托管文本模型 | [文档](https://docs.sambanova.ai/docs/en/integrations/vscode) |
| 硅基流动 / SiliconFlow | 聚合与推理平台 | 文本、音频、图像、视频 | 以账户目录为准 | [文档](https://api-docs.siliconflow.cn/docs/api/models-get) |
| Together AI | 聚合与推理平台 | 文本、音频、图像、视频 | 以账户目录为准 | [文档](https://docs.together.ai/docs/inference/openai-compatibility) |
| 维今 / ONE API | 聚合与推理平台 | 文本、图像、视频 | 文本：账户文本目录；图像：GPT Image / Nano Banana 等（以账户为准）；视频：Seedance 2.5 / 2.0 等（以账户为准） | [文档](https://www.weijinapi.top/docs/) |
| 本地 MiniMax H3 / ComfyUI | 本地服务 | 视频 | 视频：MiniMax H3 · 本地 8GB | [文档](https://docs.comfy.org/tutorials/video/minimax/minimax-h3) |
| LM Studio · 本机 | 本地服务 | 文本 | 以账户目录为准 | [文档](https://lmstudio.ai/docs/developer/openai-compat/models) |
| Ollama · 本机 | 本地服务 | 文本 | 以账户目录为准 | [文档](https://docs.ollama.com/api/openai-compatibility) |

## 维护与验证

厂商原型位于 `platform_catalog.py`，本轮扩展及分模态连接配置位于 `catalog_extensions.py`；所有预设通过 `/api/platforms` 返回。模型 ID 和原厂系列名称是不同字段，不能把系列名称当调用参数。

官方依据：[OpenAI 生图](https://developers.openai.com/api/docs/guides/image-generation)、[OpenAI 停用公告](https://developers.openai.com/api/docs/deprecations)、[Google 型号更新](https://ai.google.dev/gemini-api/docs/changelog)、[火山型号发布](https://docs.volcengine.com/docs/ark/model-release-announcement?lang=zh)、[火山创建任务](https://api.volcengine.com/api-docs/view?action=CreateContentsGenerationsTasks&serviceCode=ark&version=2024-01-01)、[xAI 视频](https://docs.x.ai/developers/model-capabilities/video/generation)、[Luma 图像](https://docs.lumalabs.ai/docs/image-generation)。

验证覆盖四模态筛选、自动跳步、型号搜索、官方目录与账户目录区分、同厂商不同地址的密钥清理、旧连接编辑、第三方响应不得覆盖目标地址、任务提交与 GET 查询、失败后保留任务 ID、继续查询不重复 POST。测试使用本地 HTTP 及模拟响应，不验证真实账户的余额、权限或生成画质。
