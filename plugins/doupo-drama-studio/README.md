# 光屿 · 斗破漫剧

版本 1.0.0。个人 Codex 插件，包含制作与实现两个 Skill；不内置模型凭据，不自带收费服务。

- `$doupo-production`：续作、镜头审查、人物/道具/人群连续性、配音和交付。
- `$guangyu-workbench`：按制作问题维护光屿代码、测试并安全部署。

安装后在 Codex 插件列表启用。若当前聊天没有刷新技能目录，开启新聊天再调用。制作前读取真实项目，第一集案例不是当前任务状态。

只读检查：
```powershell
python skills/doupo-production/scripts/audit_project.py --file project.json --output audit.json
python skills/doupo-production/scripts/audit_project.py --base-url http://127.0.0.1:8786 --project-id <32位项目ID>
```

输出不含原文、提示词、密钥、媒体URL，仅输出计数、状态与问题定位。不调用生成接口、不修改审批。退出码 0 表示元数据未发现阻塞，2 表示存在阻塞，1 表示输入或连接错误；0 不代表实际视听验收。
