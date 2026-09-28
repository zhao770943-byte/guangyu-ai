# 模型厂商目录与接入步骤

选择文本、音频、图像、视频卡片后，立即进入「连接厂商」。列表按该类型筛选，并显示匹配平台数量。回到第一步更改类型时，也会重新筛选；同一厂商仍支持该类型时保留已输入的地址和密钥，切换到其他厂商时清除输入密钥和旧型号。

这里的类型指模型输出或音频任务，不把「能够理解图片」当成「能够生成图片」。例如 Claude、DeepSeek、Kimi 的文本预设不会出现在生图或视频列表中。NVIDIA 预设限定为当前托管文本入口，不代表 NVIDIA 的全部服务。

目前共 24 项预设（含本机服务及自定义入口）。新增以下 8 项，链接也是核对地址和类型的官方资料：

| 平台 | 目录类型 | 资料 |
| --- | --- | --- |
| Groq | 文本、音频 | [API 文档](https://console.groq.com/docs/api-reference) |
| Cerebras | 文本 | [模型列表](https://inference-docs.cerebras.ai/api-reference/models/list-models) |
| Mistral | 文本、音频 | [模型目录](https://docs.mistral.ai/api/endpoint/models)、[音频](https://docs.mistral.ai/studio/audio/overview) |
| Together AI | 文本、音频、图像、视频 | [协议与接口差异](https://docs.together.ai/docs/inference/openai-compatibility)、[模型目录](https://docs.together.ai/reference/models) |
| Fireworks AI | 文本、图像 | [文本兼容接口](https://docs.fireworks.ai/tools-sdks/openai-compatibility)、[专有图像接口](https://docs.fireworks.ai/api-reference/generate-a-new-image-from-a-text-prompt) |
| SambaNova | 文本 | [兼容接口配置](https://docs.sambanova.ai/docs/en/integrations/vscode) |
| NVIDIA NIM | 托管文本入口 | [基础地址与模型目录](https://docs.nvidia.com/nim-operator/latest/guardrail.html) |
| DeepInfra | 文本、音频、图像、视频 | [模型类型](https://docs.deepinfra.com/models)、[文本接口](https://docs.deepinfra.com/chat/overview) |

「已有接口适配」表示当前类型有内置协议；具体型号仍需目录识别与账户授权。「需配置专用接口」表示仅预设了厂商地址与目录读取，生成适配尚未完成，不能将它理解为一键生成已验证。音频识别、实时音频等不能使用语音合成接口替代。厂商的单个目录入口也可能只返回部分类型，空列表时可按文档设置模型目录路径。

每个平台提供「获取 API Key」和「接口文档」链接。添加预设或读取目录不会发送生成请求，目录返回的地址也不会用来改写密钥的目标域名。已保存但不在当前预设类型范围内的旧连接，以自定义入口保留原地址。

目录读取支持 OpenAI 风格对象及 Together 等平台的顶层模型数组，保留响应大小限制、分页限制、密钥脱敏及禁止跨域重定向。新增的任务类型识别使用目录的 `type`，不依赖手动填写模型 ID。

验证：`tests/test_connection_wizard.js` 执行实际向导事件，覆盖四类筛选、默认类型点击跳转、切换厂商清理密钥、同地址密钥保留以及旧连接编辑；`tests/test_model_discovery.py` 覆盖类型元数据、官方链接、数组目录及只读网络请求。真实厂商密钥权限与付费生成需使用者在对应账户验证。
