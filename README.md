# 光屿 AI · Guangyu AI

**在自己的电脑上连接模型 API，把小说、参考图和创意组织成可审核、可续作的影像项目。**

当前主分支为 **3.2.1**。光屿是面向个人的中文 AIGC 工作台：小说改编、六 AI 协作、定稿与分镜画布、图像／视频／声音创作、作品库和模型用量集中在本机管理。浏览器打开界面，SQLite 和媒体文件保存在电脑上。

[3.2.1 更新说明](docs/release-v3.2.1.md) · [使用说明](使用说明.md) · [制作流程](docs/production-workbench.md) · [下载已发布安装包](https://github.com/zhao770943-byte/guangyu-ai/releases) · [提交问题](https://github.com/zhao770943-byte/guangyu-ai/issues)

主分支源码与已发布安装包可能版本不同。每次主分支推送会触发 [Windows 构建](https://github.com/zhao770943-byte/guangyu-ai/actions/workflows/windows-release.yml)；只有构建、测试和便携运行检查均通过后才提供该次构建的下载产物。现有 Release 不会自动更新。

## 3.2 工作台

| 工作区 | 主要用途 |
| --- | --- |
| 创作总览与项目 | 从项目封面、当前阶段、待办和任务进入制作，区分剧本计划与实际成片 |
| 小说制片 | 原文拆解、分集剧本、对白账本、定稿、分镜、视频和交付；支持分步或自动模式 |
| 六 AI 团队 | 导演、编剧、定妆审图、灯光特效、运镜、总监管分别绑定模型；项目保存独立配置 |
| 定稿与分镜 | 节点画布，角色／场景／道具与分镜连线，参考输入、候选采用、版本复核 |
| 图像与视频工具 | 文生图、参考图、模型支持的比例与高级参数、视频首尾帧／多图参考及原任务查询 |
| 声音工作区 | 按角色组织声音方案、发音和表演要求，绑定本机试听、导出台本；音频工具负责支持的语音合成 |
| 作品库与素材库 | 已保存媒体的筛选、复用、下载和删除；独立管理参考素材和项目归属 |
| 模型接入与用量 | 先连接厂商读取目录，再下拉选择类型和型号；复用已保存凭据、按来源管理、查看真实用量回执 |
| 网页 AI 助手 | 对话、提示词润色、创作答疑，选择需要采纳到工作区的内容 |

小说流程保持可追踪的审核条件。自动模式可以推进到视频生成，但不会替用户勾选实际视听验收或自动发布。对白缺失、过期分镜审核、缺少参考资产、模型能力不符和请求额度不足，会在对应阶段提示或停止推进。

![图像工具界面示例](docs/images/studio.jpg)

上图为已有版本的图像工具截图；当前小说项目工作台的入口与操作以 [3.2 使用说明](使用说明.md) 为准。

## Windows 一键使用

1. 从 [Releases](https://github.com/zhao770943-byte/guangyu-ai/releases) 选择已发布版本，下载 `GuangyuAI-v版本号-windows-x64.zip`。`Source code` 是开发源码，不是便携应用。
2. 完整解压到有写入权限的普通文件夹，保留 `GuangyuAI.exe` 旁的 `_internal`。
3. 双击 `GuangyuAI.exe`，浏览器打开 [本机工作台](http://127.0.0.1:8786/)。便携包无需安装 Python、Node.js 或数据库。
4. 在模型接入中选择厂商，填写自己的 API Key 并读取模型目录；已有来源可复用保存的凭据。
5. 下拉选择文本、图像、视频或音频，再选该来源的型号。保存连接后配置项目需要的模型与 AI 团队。

关闭网页后服务继续运行；等待任务结束后，使用 `停止光屿AI.cmd` 或 `GuangyuAI.exe --stop` 停止。常驻登录启动可按 [开发与维护说明](docs/development.md#windows-常驻运行) 配置。

目前支持 **Windows x64**。应用免费开源，模型服务的额度与费用由所选平台决定。程序尚未代码签名，下载时可比对对应包的 SHA-256 校验文件。

## 从源码运行最新版

需要 Windows、Python 3.11 或以上。密钥存储使用 Windows DPAPI，当前不提供 macOS／Linux 运行支持。

```powershell
git clone https://github.com/zhao770943-byte/guangyu-ai.git
cd guangyu-ai
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launcher.py
```

停止服务：

```powershell
.\.venv\Scripts\python.exe launcher.py --stop
```

前端为原生 HTML／CSS／JavaScript，没有 npm 构建步骤。Python 依赖包括 Pillow 和 PyAV；版本以 `requirements.txt` 为准。完整测试、打包与常驻服务见 [开发文档](docs/development.md)。

## 模型与数据边界

厂商预设覆盖国内外模型原厂、托管平台与本机服务。模型目录按所选来源读取，目录可见不代表当前密钥有生成权限或余额。模型输出类型与协议分别检查；可理解图片的语言模型不因此成为生图模型。

支持已适配的 OpenAI、Anthropic、Gemini、MiniMax、方舟等协议，以及自定义 JSON 请求与轮询映射。专有鉴权、上传、WebSocket 等可能需要额外适配；不保证任意平台只填 URL 即可生成。具体能力见 [接口接入指南](docs/providers.md) 与 [厂商目录](docs/provider-selection.md)。

外部 HTTPS 模型请求默认使用系统代理，本地模型始终直连；详见 [网络与系统代理](docs/provider-network.md)。

默认仅监听 `127.0.0.1:8786`。API Key 在后端使用当前 Windows 用户的 DPAPI 加密，界面不会回显密钥。用户主动运行模型任务时，相关原文、提示词和参考素材会发送给所选模型服务。

用量统计来自本应用任务和平台返回的字段，不是平台账单。未返回 Token 时显示未提供，不能用 Token 估算所有图像／视频费用。请求次数上限也不等于金额预算。

升级前停止服务并备份整个 `data/`。原文、作品、密钥、SQLite、日志和本机制作记录不属于开源发布内容。迁移步骤见 [数据与升级](docs/data-and-upgrades.md)。

## 文档与插件

- [制作流程与验收](docs/production-workbench.md) · [定稿与分镜画布](docs/visual-studio.md)
- [完整使用说明](使用说明.md) · [更新记录](CHANGELOG.md)
- [斗破漫剧制作与工作台开发插件](plugins/doupo-drama-studio/README.md)：可复用的制作 Skill、审核规则与只读审计脚本，不含小说全文、人物图片、配音或成片。
- [贡献指南](CONTRIBUTING.md) · [安全说明](SECURITY.md)

## License

[MIT](LICENSE) © 2026 zhao770943-byte。第三方依赖遵循各自许可证；模型服务和用户导入素材的权利与使用条件分别适用。
