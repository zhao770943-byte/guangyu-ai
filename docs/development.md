# 开发、验证与 Windows 打包

## 开发环境

使用 Windows x64、Python 3.11 或以上。当前密钥存储依赖 Windows DPAPI；前端没有 Node.js 或 npm 构建步骤。

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe launcher.py
```

`Pillow==12.3.0` 负责验证图片上传。后端主要使用 Python 标准库，SQLite 无需独立安装。测试产生的数据与服务必须和日常使用隔离。

## 代码结构

| 文件 | 作用 |
| --- | --- |
| `launcher.py` | 启动／停止本应用服务并打开浏览器 |
| `server.py` | 本机 HTTP、任务调度、同源校验、恢复与静态资源 |
| `providers.py` | 协议请求、结果解析、轮询与用量归一化 |
| `platform_catalog.py` | 平台 API 前缀、协议、列表方式与官方文档依据 |
| `model_catalog.py` | 只读模型发现、分页／资源限制与保守用途建议 |
| `capabilities.py` | 有效能力、模板变量与提交前校验 |
| `uploads.py` | 图片验证、保存与输入素材转换 |
| `storage.py` | SQLite 和 Windows DPAPI |
| `usage.py` | 本机用量聚合与 CSV |
| `public/` | 原生 HTML、CSS、JavaScript |
| `public/connections.js` / `public/connections.css` | 模型管理表格、类型、厂商、型号三步接入向导与按需展开的高级配置 |
| `tests/` | 单元测试与隔离 HTTP 模拟接口 |

协议适配时同时更新能力声明、请求构建、响应提取与用量字段。所有新增生成行为应由用户主动发起；不要因为临时网络失败自动重试付费 POST。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv\Scripts\python.exe tests/verify_v2.py
.\.venv\Scripts\python.exe tests/verify_workbench.py
```

测试使用内置微型视频、本机模拟服务与临时数据，不要求 ffmpeg 或真实模型密钥。具体覆盖和限制见 [验收记录](../验收记录.md)。

前端交互回归（离线状态与 DOM 契约，不代表浏览器视觉验收）：

```powershell
node tests/test_workbench_ui.js
node tests/test_connection_wizard.js
node tests/test_storyboards_ui.js
node tests/test_storyboards_form.js
node tests/test_library_picker.js
```

## Windows 便携构建

在 Windows x64 上执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe scripts/build_windows.py
```

构建脚本生成 `dist/` 中的发布 ZIP。应用使用目录分发形式，用户需要完整保留 `GuangyuAI.exe` 和 `_internal/`。最终名称和校验文件以脚本输出及 GitHub Release 为准；不要把 `data/`、开发环境或测试工作目录打包进去。

发布前应实际解压 ZIP 到独立目录，核对无用户数据，再使用包内 EXE 验证启动、健康接口、停止、图片上传和重启后数据保留。仅构建命令成功不代表应用可运行。模拟接口结果不代表任何真实平台账户有调用权限。

仓库提供便携包隔离检查：

```powershell
.\.venv\Scripts\python.exe tests/smoke_packaged.py dist/GuangyuAI/GuangyuAI.exe
```

该检查使用独立副本、本机模拟服务与测试数据；运行 EXE 时不依赖 PATH 中的 Python。它不会验证真实平台额度或完整 Windows 兼容性。

便携版包含 Python 和第三方运行依赖；分发时保留相关许可。当前构建不包含代码签名，SHA-256 用于核对文件一致性。
