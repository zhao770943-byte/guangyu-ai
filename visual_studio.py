"""Versioned visual references and storyboard graphs; all generation is explicit."""
import copy
import json
import math
import re
import capabilities
import storage
import storyboards
import uploads

TABLE = 'visual_projects'
MAX_NODES = 64
ACTIVE = {'queued', 'submitting', 'polling'}


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise ValueError('节点或项目 ID 无效。')
    return value


def require(value):
    project = storage.get(TABLE, identity(value))
    if not project:
        raise ValueError('定稿项目不存在。')
    return project


def node_for(project, value):
    node = next((n for n in project['nodes'] if n['id'] == value), None)
    if not node:
        raise ValueError('节点不存在。')
    return node


def current(node):
    return next((v for v in node['versions'] if v['id'] == node.get('active_version_id')), None)


def refs_for(project, node, strict=False):
    result = []
    for ref_id in node['refs']:
        ref = node_for(project, ref_id)
        if strict and is_stale(project, ref):
            raise ValueError('引用节点“' + ref['title'] + '”需要先复核或重新采用图片。')
        version = current(ref)
        if not version:
            if strict:
                raise ValueError('请先为引用节点“' + ref['title'] + '”采用一张图片。')
            result.append({'node_id': ref_id, 'version_id': None, 'upload_id': None})
        else:
            result.append({'node_id': ref_id, 'version_id': version['id'], 'upload_id': version['upload_id']})
    return result


def is_stale(project, node, memo=None):
    memo = {} if memo is None else memo
    if node['id'] in memo:
        return memo[node['id']]
    memo[node['id']] = False
    version = current(node)
    changed = bool(version and (version.get('reference_snapshot', []) != refs_for(project, node)
                               or version.get('prompt', '') != node['prompt']
                               or any(is_stale(project, node_for(project, ref), memo) for ref in node['refs'])))
    memo[node['id']] = changed
    return changed


def project_jobs(project):
    ids = list(dict.fromkeys([j for n in project['nodes'] for j in n['job_ids']] + project.get('film_job_ids', [])))
    return [j for k in ids if (j := storage.get('jobs', k))]


def public(project):
    result = copy.deepcopy(project)
    result.pop('requests', None)
    result.pop('film_requests', None)
    for node in result['nodes']:
        for version in node['versions']:
            try:
                version['asset'] = {k: v for k, v in uploads.get(version['upload_id']).items() if k != 'filename'}
            except ValueError:
                version['asset'] = None
        version = current(node)
        node['stale'] = is_stale(project, node)
    result['jobs'] = [storage.public_job(j) for j in project_jobs(project)]
    return result


def list_projects():
    return [{k: p[k] for k in ('id', 'title', 'updated_at')} for p in storage.items(TABLE)]


def version_check(project, body):
    if project['version'] != body.get('version'):
        raise ValueError('项目已在其他窗口更新。请先导出当前草稿，再重新载入，避免覆盖。')


def persist(project):
    project['version'] += 1
    project['updated_at'] = storage.now()
    storage.put(TABLE, project)
    return public(project)


def number(value, default, low, high):
    value = default if value is None else value
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('画布坐标或缩放值无效。')
    return value


def add_version(node, upload_id, prompt, snapshot, job_id=None):
    uploads.get(upload_id)
    version = {'id': storage.uid(), 'upload_id': upload_id, 'prompt': prompt,
               'reference_snapshot': copy.deepcopy(snapshot), 'job_id': job_id, 'created_at': storage.now()}
    node['versions'].append(version)
    node['active_version_id'] = version['id']
    return version


def save(body):
    with storage.LOCK:
        old = require(body['id']) if body.get('id') else None
        if old:
            version_check(old, body)
        raw = body.get('nodes', [])
        if not isinstance(raw, list) or len(raw) > MAX_NODES:
            raise ValueError('一个画布最多支持 64 个节点。')
        previous = {n['id']: n for n in old['nodes']} if old else {}
        nodes, seen, initial = [], set(), {}
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError('节点格式无效。')
            key = identity(item.get('id') or storage.uid())
            if key in seen:
                raise ValueError('节点 ID 重复。')
            seen.add(key)
            kind = item.get('kind', 'master')
            subtype = item.get('subtype', 'character')
            if kind not in ('master', 'shot') or subtype not in ('character', 'scene', 'prop', 'style'):
                raise ValueError('节点类型无效。')
            ratio = item.get('ratio', body.get('ratio', '9:16'))
            if ratio not in storyboards.RATIOS:
                raise ValueError('画幅比例无效。')
            layout = item.get('layout', 'single')
            if layout not in ('single', 'sheet'):
                raise ValueError('定稿版式无效。')
            refs = item.get('refs', [])
            if not isinstance(refs, list) or len(refs) > 8 or len(set(refs)) != len(refs):
                raise ValueError('每个节点最多引用 8 个不同节点。')
            for ref in refs:
                identity(ref)
            old_node = previous.get(key)
            node = {**(copy.deepcopy(old_node) if old_node else {'versions': [], 'active_version_id': None, 'job_ids': []}),
                    'id': key, 'kind': kind, 'subtype': subtype, 'layout': layout,
                    'title': storyboards.text(item.get('title', '未命名'), '节点名称', 80),
                    'prompt': storyboards.text(item.get('prompt', ''), '画面描述', 6000, empty=True),
                    'video_prompt': storyboards.text(item.get('video_prompt', ''), '视频描述', 16000, empty=True),
                    'provider_id': storyboards.text(item.get('provider_id', ''), '图像模型', 80, empty=True),
                    'ratio': ratio, 'refs': refs,
                    'x': number(item.get('x'), 60, -100000, 100000),
                    'y': number(item.get('y'), 60, -100000, 100000)}
            node.pop('stale', None)
            for version in node['versions']:
                version.pop('asset', None)
            if not old_node and item.get('upload_id'):
                initial[key] = identity(item['upload_id'])
                uploads.get(initial[key])
            nodes.append(node)
        for node in nodes:
            if node['id'] in node['refs'] or any(r not in seen for r in node['refs']):
                raise ValueError('引用必须连接到画布上的其他节点。')
        graph = {n['id']: n['refs'] for n in nodes}
        visited, visiting = set(), set()

        def visit(key):
            if key in visiting:
                raise ValueError('参考连线不能形成循环。')
            if key in visited:
                return
            visiting.add(key)
            for ref in graph[key]:
                visit(ref)
            visiting.remove(key)
            visited.add(key)
        for key in graph:
            visit(key)
        if old:
            for key, node in previous.items():
                if key not in seen and any((j := storage.get('jobs', job_id)) and j['status'] in ACTIVE for job_id in node['job_ids']):
                    raise ValueError('生成中的节点暂时不能移除。')
        viewport = body.get('viewport') or {}
        ratio = body.get('ratio', '9:16')
        if ratio not in storyboards.RATIOS:
            raise ValueError('项目画幅无效。')
        project = {**(copy.deepcopy(old) if old else {'id': storage.uid(), 'version': 0, 'requests': {}}),
                   'title': storyboards.text(body.get('title', '未命名定稿项目'), '项目名称', 80),
                   'story': storyboards.text(body.get('story', ''), '项目说明', 16000, empty=True),
                   'ratio': ratio, 'provider_id': storyboards.text(body.get('provider_id', ''), '默认模型', 80, empty=True),
                   'viewport': {'x': number(viewport.get('x'), 0, -100000, 100000),
                                'y': number(viewport.get('y'), 0, -100000, 100000),
                                'zoom': number(viewport.get('zoom'), 1, .15, 2)}, 'nodes': nodes}
        # Import/copy: resolve new versions in graph order, so copied internal edges stay current.
        if 'film_options' in body:
            film = body['film_options']
            if not isinstance(film, dict):
                raise ValueError('整片配置格式无效。')
            keys, lengths = film.get('node_ids', []), film.get('durations', [])
            if not isinstance(keys, list) or len(keys) > 9 or len(set(keys)) != len(keys) or any(k not in seen for k in keys):
                raise ValueError('整片配置中的分镜无效。')
            if not isinstance(lengths, list) or len(lengths) != len(keys) or any(type(t) not in (int, float) or not math.isfinite(t) or t < .1 for t in lengths):
                raise ValueError('整片配置中的镜头时长无效。')
            if film.get('execution_mode', 'serial') not in ('serial', 'parallel'):raise ValueError('整片提交方式无效。')
            project['film_options'] = {'node_ids': keys, 'durations': lengths, 'provider_id': storyboards.text(film.get('provider_id', ''), '视频模型', 80, empty=True),
                                       'seconds': number(film.get('seconds'), 15, 1, 600), 'execution_mode': film.get('execution_mode', 'serial')}
        pending = set(initial)
        while pending:
            key = next(k for k in pending if not any(r in pending for r in graph[k]))
            node = node_for(project, key)
            add_version(node, initial[key], node['prompt'], refs_for(project, node))
            pending.remove(key)
        return persist(project)


def adopt(body):
    with storage.LOCK:
        project = require(body.get('id'))
        version_check(project, body)
        node = node_for(project, body.get('node_id'))
        if body.get('version_id'):
            if not any(v['id'] == body['version_id'] for v in node['versions']):
                raise ValueError('图片版本不存在。')
            node['active_version_id'] = body['version_id']
        else:
            job_id = body.get('job_id')
            if job_id:
                if job_id not in node['job_ids']:
                    raise ValueError('生成结果不属于此节点。请从作品库导入。')
                job = storage.get('jobs', job_id)
                asset = storyboards.image_from_job(job_id, body.get('asset_index'))
                snapshot = job.get('visual_reference_snapshot', [])
                prompt = job.get('visual_node_prompt', node['prompt'])
            else:
                asset = uploads.get(body.get('upload_id'))
                snapshot, prompt = refs_for(project, node), node['prompt']
            add_version(node, asset['id'], prompt, snapshot, job_id)
        return persist(project)


def prompt_for(project, node):
    references = [node_for(project, key) for key in node['refs']]
    mapping = '\n'.join(f'参考图{i+1}：{ref["title"]}（{ref["subtype"] if ref["kind"] == "master" else "镜头构图"}）。只取与当前画面有关的人物或场景。' for i, ref in enumerate(references))
    common = f'项目背景（仅作语境，不把全部故事画在一张图）：\n{project["story"]}\n当前节点：{node["title"]}\n{node["prompt"]}\n画幅：{node["ratio"]}。\n{mapping}\n'
    if node['kind'] == 'shot':
        return common + '只生成这一镜头的一张独立静态画面。保持所选参考的人物面貌、服装和指定场景；根据本镜头重新安排动作与机位。人物设定板不是最终画面构图，不把正侧背三视图或白底带进分镜。不要添加脚本中的其他场景，无分屏、拼贴、字幕、水印。'
    if node['subtype'] == 'character' and node['layout'] == 'sheet':
        return common + '生成同一角色的横向定稿设定板：左侧为清晰面部近景，右侧依次为完整全身正面、侧面、背面，脚部完整可见。四个视图是同一个角色，不是四个人；发型、脸部特征、服装、鞋、配饰、身体比例完全一致。浅色干净背景，均匀柔光，视图整齐排列、不互相遮挡，无文字、编号、水印。只展示角色，不演绎故事。'
    return common + '生成当前角色、场景、道具或风格的独立视觉定稿。轮廓、材质和关键细节清楚，适合作为后续镜头参考，不演绎整段故事，无文字或水印。'


def generate(body, prepare, dispatch, active, active_lock):
    with active_lock, storage.LOCK:
        project = require(body.get('id'))
        token = identity(body.get('request_id'))
        if token in project['requests']:
            return public(project)
        version_check(project, body)
        selected = body.get('node_ids')
        if not isinstance(selected, list) or not 1 <= len(selected) <= 12 or len(set(selected)) != len(selected):
            raise ValueError('请选择 1–12 个节点生成。')
        if len(active) + len(selected) > 12:
            raise ValueError('当前队列空间不足，请等待任务完成。')
        prepared = []
        for key in selected:
            node = node_for(project, key)
            if any((j := storage.get('jobs', k)) and (j['status'] in ACTIVE or j.get('archive_status') == 'pending') for k in node['job_ids']):
                raise ValueError('所选节点仍在生成或保存，请稍候。')
            if not node['prompt'].strip():
                raise ValueError('请填写“' + node['title'] + '”的画面描述。')
            provider = storage.get('providers', node['provider_id'] or project['provider_id'])
            if not provider or provider['kind'] != 'image':
                raise ValueError('请选择有效的图像模型。')
            caps = capabilities.effective(provider)
            snapshot = refs_for(project, node, strict=True)
            if snapshot and not caps['reference_images']:
                raise ValueError('当前模型不支持参考图，不能执行所选连线。')
            if provider.get('extra', {}).get('n', 1) != 1:
                raise ValueError('每个节点生成一张图，请将连接附加参数 n 设为 1。')
            params = {'n': 1} if caps['batch'] else {}
            if caps['aspect_ratio']:
                params['aspect_ratio'] = node['ratio']
            job = prepare({'provider_id': provider['id'], 'prompt': prompt_for(project, node), 'size': 'auto',
                           'parameters': params, 'input_assets': {'references': [v['upload_id'] for v in snapshot]}}, prepare_only=True)
            job.update(visual_project_id=project['id'], visual_node_id=key,
                       visual_node_prompt=node['prompt'], visual_reference_snapshot=snapshot)
            node['job_ids'].append(job['id'])
            prepared.append(job)
        project['requests'][token] = [j['id'] for j in prepared]
        project['version'] += 1
        project['updated_at'] = storage.now()
        with storage.connect() as db:
            for job in prepared:
                db.execute('INSERT INTO jobs VALUES (?,?,?)', (job['id'], job['created_at'], json.dumps(job, ensure_ascii=False)))
            db.execute('INSERT OR REPLACE INTO visual_projects VALUES (?,?,?)', (project['id'], project['updated_at'], json.dumps(project, ensure_ascii=False)))
        for job in prepared:
            dispatch(job)
        return public(project)


def transfer(body):
    with storage.LOCK:
        project = require(body.get('id'))
        version_check(project, body)
        node = node_for(project, body.get('node_id'))
        version = current(node)
        if not version:
            raise ValueError('请先采用一张图片，再送往视频。')
        if is_stale(project, node):
            raise ValueError('此图片的描述或引用已变化，请先复核，或使用当前引用重新生成并采用。')
        asset = {k: v for k, v in uploads.get(version['upload_id']).items() if k != 'filename'}
        return {'asset': asset, 'ratio': node['ratio'], 'prompt': node['video_prompt'], 'title': node['title'], 'version_id': version['id']}


def acknowledge(body):
    """An explicit review records acceptance of the current image with current inputs."""
    with storage.LOCK:
        project = require(body.get('id'))
        version_check(project, body)
        node = node_for(project, body.get('node_id'))
        version = current(node)
        if not version:
            raise ValueError('没有可复核的已采用图片。')
        new = add_version(node, version['upload_id'], node['prompt'], refs_for(project, node), version.get('job_id'))
        new['reviewed_from_version_id'] = version['id']
        return persist(project)


def import_legacy(body):
    with storage.LOCK:
        legacy = storyboards.require(body.get('legacy_id'))
        # Repeated import opens the same imported project, never duplicates uploads on a retry.
        existing = next((p for p in storage.items(TABLE) if p.get('legacy_id') == legacy['id']), None)
        if existing:
            return public(existing)
        master = storage.uid()
        raw = [{'id': master, 'kind': 'master', 'subtype': 'style', 'title': '原共同定稿', 'prompt': legacy['master_prompt'] or legacy['story'], 'ratio': legacy['ratio'], 'x': 60, 'y': 100, 'refs': []}]
        if legacy.get('master_upload_id'):
            raw[0]['upload_id'] = legacy['master_upload_id']
        for index, shot in enumerate(legacy['shots']):
            raw.append({'id': storage.uid(), 'kind': 'shot', 'title': shot['title'], 'prompt': shot['prompt'],
                        'x': 430 + (index % 3) * 320, 'y': 80 + (index // 3) * 390,
                        'ratio': legacy['ratio'], 'refs': [master] if legacy.get('master_upload_id') else []})
            if shot.get('job_id'):
                job = storage.get('jobs', shot['job_id'])
                if job and job['status'] == 'succeeded':
                    try:
                        raw[-1]['upload_id'] = storyboards.image_from_job(job['id'])['id']
                    except ValueError:
                        pass
        project = save({'title': legacy['title'], 'story': legacy['story'], 'provider_id': legacy['provider_id'], 'ratio': legacy['ratio'], 'nodes': raw})
        stored = require(project['id'])
        stored['legacy_id'] = legacy['id']
        old_jobs = [legacy.get('master_job_id')] + [s.get('job_id') for s in legacy['shots']]
        for node, job_id in zip(stored['nodes'], old_jobs):
            if job_id:
                node['job_ids'] = [job_id]
                if current(node):
                    current(node)['job_id'] = job_id
        return persist(stored)
