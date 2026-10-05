# 光屿本机项目协议

先确认运行实例和数据目录；端口常用8786但不可假定。首次只读：

- GET /api/health：实例标识与版本。
- GET /api/novels：项目列表。
- GET /api/novels?id=<32hex>：公开项目状态（不包含密钥）。
- GET /api/state：仅在确有必要时读取，输出要过滤。不要输出完整厂商配置、日志或用户小说。

使用 scripts/audit_project.py 可避免把全文和媒体网址输出到聊天。它不验证实际画面，不发生成请求。

制作手册在 production_book，当前检查结果在 production_state。写入 POST /api/novels/command，使用现有客户端 api() 的 Origin/CSRF；每次携带 id、version、全新32hex request_id。同一请求重试沿用 request_id；冲突先重读，不强写数据库。

支持：
- studio_enable：开启逐镜规则；保留历史。
- studio_contract：slot=shot:<episode>:<shot>，contract含start/end/eyeline/crowd/bridge/beats/avoid/sound_mode。
- studio_review_shot：检查当前图片后，携带当前fingerprint、inspected=true、七项checks和notes。禁止脚本自动填全true冒充审查。
- studio_sound：voices数组(asset_id,voice,pronunciation,direction,audio_job_id)，mix_notes。asset_id可用剧本人物ID，或voice:announcer、voice:narrator、voice:crowd分别保存报幕、旁白、人群声位。
- studio_issue：shot(可空)、category、notes。
- studio_resolve：issue_id、resolution。写具体哪版修好及依据。
- studio_delivery：当前film_fingerprint、watched、八项checks、notes；必须完整审片且无未解决问题。

studio_* 只记资料，不生成媒体。真正生成仍走现有阶段/调度、并发、预算、原任务恢复和幂等。先查询原任务能节省重复费用。image/video job succeeded 不是用户验收。

专业模式下审批与视频提交都检查当前分镜hash。旧项目可显式启用；已完成且暂停的项目不能因为安装插件被自动恢复、改成已验收或替换主选成片。

导出制作资料不包含媒体原文件。单独保留成片、原音轨、图片、字幕、剪辑区间、任务ID与hash；需要恢复时先查看实际DATA路径。不要把SQLite、API Key、用户小说章节或全部历史日志打包到插件。

如当前工作区提供交接清单或剪辑渲染清单，先从清单定位项目与素材，再用 API 验证当前主选版本。路径以当前项目实际配置为准，不将历史清单当作永久状态，避免扫描无关目录。
