"""One video job from an ordered set of adopted storyboard images."""
import copy
import json
import film_plan
import film_queue
import capabilities
import storage
import uploads
import video_controls
import visual_studio as visual


def generate(body, prepare, dispatch, active, active_lock):
    with active_lock, storage.LOCK:
        project = copy.deepcopy(visual.require(body.get('id')))
        token = visual.identity(body.get('request_id'))
        receipts = project.setdefault('film_requests', {})
        if token in receipts:
            return {'project': visual.public(project), 'job': storage.public_job(storage.get('jobs', receipts[token]))}
        visual.version_check(project, body)
        if len(active) >= 12:
            raise ValueError('当前队列已满，请等待已有任务完成。')
        if any((j := storage.get('jobs', key)) and j['status'] in visual.ACTIVE for key in project.get('film_job_ids', [])):
            raise ValueError('此项目的整片视频仍在生成，请在视频工作台查看进度。')
        provider = storage.get('providers', body.get('provider_id', ''))
        if not provider or provider['kind'] != 'video' or not capabilities.effective(provider)['reference_images']:
            raise ValueError('整片生成需要支持多张参考图的视频模型；仅首尾帧模型不能用于此流程。')
        ids = body.get('node_ids')
        if not isinstance(ids, list) or not 2 <= len(ids) <= 9 or len(set(ids)) != len(ids):
            raise ValueError('请选择 2–9 个不同分镜，按播放顺序排列。')
        nodes = [visual.node_for(project, key) for key in ids]
        if any(n['kind'] != 'shot' for n in nodes):
            raise ValueError('整片只能使用分镜节点，请先把角色定稿制作成独立镜头。')
        plan = film_plan.plan(body)
        seconds, lengths = plan['seconds'], body['durations']
        if len(lengths) != len(ids):raise ValueError('每个分镜必须对应一个时长。')
        ratios = {n['ratio'] for n in nodes}
        if len(ratios) != 1:
            raise ValueError('所选分镜画幅不同，请先统一画幅后生成整片。')
        ratio = nodes[0]['ratio']
        controls = video_controls.options(provider)
        if not any(r['value'] == ratio and r['enabled'] for r in controls['ratios']):
            raise ValueError('当前视频模型不支持这些分镜的画幅。')
        reviews = body.get('review_versions', {})
        if not isinstance(reviews, dict):
            raise ValueError('复核记录格式无效。')
        pending = []
        for node in nodes:
            version = visual.current(node)
            if not version:
                raise ValueError('“' + node['title'] + '”还没有采用分镜图片。')
            uploads.get(version['upload_id'])
            if not node['video_prompt'].strip():
                raise ValueError('请填写“' + node['title'] + '”的视频提示词。')
            if visual.is_stale(project, node):
                if reviews.get(node['id']) != version['id']:
                    raise ValueError('“' + node['title'] + '”需要复核：请查看图片和当前描述，确认一致后勾选。')
                pending.append(node)
        # Review explicit selections in reference order, without bypassing stale upstream masters.
        while pending:
            keys = {n['id'] for n in pending}
            node = next(n for n in pending if not any(ref in keys for ref in n['refs']))
            snapshot = visual.refs_for(project, node, strict=True)
            old = visual.current(node)
            reviewed = visual.add_version(node, old['upload_id'], node['prompt'], snapshot, old.get('job_id'))
            reviewed['reviewed_from_version_id'] = old['id']
            pending.remove(node)
        refs, timeline, clock = [], [], 0
        parts = [f'生成一条完整的 {seconds} 秒视频，画幅 {ratio}。下列 {len(nodes)} 张参考图分别对应按时间顺序排列的分镜。',
                 '按镜头编号和时间段依次演绎，保持角色外貌、服装与场景逻辑一致，镜头之间自然转场。每次只呈现当前镜头的画面，不要把多张参考图拼成网格、分屏或静态幻灯片。不要添加编号、字幕或水印。']
        if project.get('story'):
            parts.append('故事背景：' + project['story'])
        for i, (node, length) in enumerate(zip(nodes, lengths), 1):
            if visual.is_stale(project, node):
                raise ValueError('“' + node['title'] + '”仍有未复核的上游参考。')
            version = visual.current(node)
            refs.append(version['upload_id'])
            end = round(clock + length, 3)
            parts.append(f'镜头 {i}｜{clock:g}–{end:g} 秒｜参考图 {i}：{node["title"]}\n{node["video_prompt"]}')
            timeline.append({'node_id': node['id'], 'title': node['title'], 'version_id': version['id'], 'upload_id': version['upload_id'], 'start': clock, 'end': end, 'video_prompt': node['video_prompt']})
            clock = end
        params, size = {}, 'auto'
        if controls['mode'] == 'aspect':
            params['aspect_ratio'] = ratio
        else:
            target = next(r for r in controls['ratios'] if r['value'] == ratio)
            size = target['sizes'].get('720p') or next(iter(target['sizes'].values()), 'auto')
        children = []
        needs_composition = len(plan['segments']) > 1 or plan['segments'][0]['request_seconds'] != seconds
        if needs_composition:
            import film_compose
            film_compose.check_runtime()
        for segment in plan['segments']:
            clip_refs, clip_parts = [], [f"生成 {segment['request_seconds']} 秒视频，画幅 {ratio}。这是连续整片的第 {segment['index']} 段，遵循以下局部时间轴。", parts[1]]
            if project.get('story'):
                clip_parts.append('故事背景：' + project['story'])
            for ref_index, shot in enumerate(segment['shots'], 1):
                item = timeline[shot['index']]
                clip_refs.append(item['upload_id'])
                clip_parts.append(f"参考图 {ref_index}｜本段 {shot['start']-segment['start']:g}–{shot['end']-segment['start']:g} 秒｜{item['title']}\n{item['video_prompt']}")
                if shot['offset']:
                    clip_parts.append(f"此镜头已在上一段进行 {shot['offset']:g} 秒，继续同一动作与情境，不要重复开场。")
            if segment['request_seconds'] > segment['used_seconds']:
                clip_parts.append(f"前 {segment['used_seconds']:g} 秒完成上述动作，剩余时间自然延续最后一个画面；成片只使用前 {segment['used_seconds']:g} 秒。")
            child = prepare({'provider_id': provider['id'], 'prompt': '\n\n'.join(clip_parts) if needs_composition else '\n\n'.join(parts),
                             'seconds': segment['request_seconds'], 'size': size, 'input_assets': {'references': clip_refs},
                             'parameters': params, 'collection_id': 'visual:' + project['id']}, prepare_only=True)
            child.update(visual_project_id=project['id'], visual_film_timeline=[timeline[t['index']] for t in segment['shots']])
            children.append(child)
        job = children[0]
        if needs_composition:
            job = {**copy.deepcopy(job), 'id': storage.uid(), 'seconds': seconds, 'prompt': '\n\n'.join(parts),
                   'input_assets': {'references': refs}, 'visual_film_timeline': timeline, 'film_batch': True,
                   'film_phase': 'generating', 'film_execution_mode': plan['execution_mode'], 'film_segments': [],
                   'film_requested_seconds': plan['requested_seconds'], 'film_completed': 0}
            job.pop('provider_snapshot', None)
            job['usage'] = None
            for child, segment in zip(children, plan['segments']):
                child.update(film_parent_id=job['id'], film_segment_index=segment['index'], film_dispatch_state='waiting')
                job['film_segments'].append({**segment, 'job_id': child['id'], 'attempts': []})
        project.setdefault('film_job_ids', []).extend([job['id']] + [j['id'] for j in children if j['id'] != job['id']])
        receipts[token] = job['id']
        project['film_options'] = {'provider_id': provider['id'], 'seconds': seconds, 'node_ids': ids, 'durations': lengths, 'execution_mode': plan['execution_mode']}
        project['version'] += 1
        project['updated_at'] = storage.now()
        with storage.connect() as db:
            for item in children + ([job] if needs_composition else []):
                db.execute('INSERT INTO jobs VALUES (?,?,?)', (item['id'], item['created_at'], json.dumps(item, ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO visual_projects VALUES (?,?,?)', (project['id'], project['updated_at'], json.dumps(project, ensure_ascii=False)))
        if needs_composition:
            film_queue.tick(dispatch, None, active, active_lock)
        else:
            dispatch(job)
        return {'project': visual.public(project), 'job': storage.public_job(storage.get('jobs', job['id']))}
