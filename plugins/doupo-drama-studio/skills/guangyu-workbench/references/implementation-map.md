# 当前实现映射（使用前先核对源码）

| 边界 | 当前模块 |
| --- | --- |
| HTTP/Origin/CSRF、静态资源、启动 | server.py / launcher.py / watchdog.py |
| 持久化、公开任务、上传 | storage.py / uploads.py / media_store.py |
| 项目状态机、幂等收据、调度 | novel_studio.py |
| 剧本解析/AI提示模板 | novel_schema.py |
| 五项视频审核、元数据、预算 | novel_quality.py |
| 版本审图、约定、声音、问题、交付 | production_book.py |
| 六角色绑定与参考 | ai_control.py |
| 合成与任务恢复 | film_plan.py / film_queue.py / film_compose.py |
| 旧工作台与通用绑定 | public/novel-studio.js / novel-workbench.js |
| 连续漫剧七区界面 | public/production-desk.js / production-desk.css |
| 页面加载顺序 | public/index.html |
| 隔离验收 | tests/test_production_book.py / test_novel_quality.py / test_novel_studio.py |

production_book采用增量字段，不改旧项目phase或接受标志。summary按当前fingerprint推导，不永久信任一个true。studio_* 接口不调用模型。新项目 professional_workflow=true开启强制审图和视频验收；旧项目需显式启用以免恢复时突然改变流程。

数据模型：
- plan.assets: id/kind/name/description/prompt
- plan.episodes[].shots: id/title/seconds/asset_ids/action/dialogue/camera/image_prompt/video_prompt
- images['shot:e1:s1']: 上传ID；locked_assets[assetID]: 定稿上传ID
- slots: 原任务与尝试历史；films[episodeID]: 当前成片任务ID
- production_book: enabled/contracts/storyboards/voices/mix_notes/issues/delivery/delivery_history
- production_state: 当前逐镜状态/已审计数/待修数/交付状态与film_fingerprint

现有约束：120秒剧本schema与实际手工成片时长不是同一概念；不要未经设计改120秒约束。声音页保存方案与试听，不自动做TTS/人脸口型修复。当前版本hash校验可识别修改，无法自动证明审图者真的看过，因此notes和真实检查过程仍必需。

测试命令（项目根目录，指定可用Python）：
```
python -m unittest discover -s tests -p test_production_book.py
python -m unittest discover -s tests -p test_novel_quality.py
node --check public/production-desk.js
```

任何新增自动付费功能都必须展示调用范围、提供中断和原任务恢复；不允许后台无限循环“充值后重试”。
