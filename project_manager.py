"""Project index and reversible organization, separate from production execution."""
import hashlib
import re
import storage

TABLES = {'novel': 'novel_projects', 'visual': 'visual_projects'}
ACTIVE = {'queued', 'submitting', 'polling'}


def metadata_id(kind, identity):
    return hashlib.sha256(('project-management:' + kind + ':' + identity).encode()).hexdigest()[:32]


def summarize(kind, project, jobs):
    identity = project['id']
    meta = storage.get('workspace_items', metadata_id(kind, identity)) or {}
    ids = set(project.get('film_job_ids', [])) | set(project.get('films', {}).values())
    for slot in project.get('slots', {}).values():
        ids.update(slot.get('attempts', [])); ids.add(slot.get('job_id'))
    for node in project.get('nodes', []):
        ids.update(node.get('job_ids', []))
    related = [j for j in jobs if j.get(kind + '_project_id') == identity or j['id'] in ids or j.get('collection_id') == kind + ':' + identity]
    running = sum(j.get('status') in ACTIVE or j.get('archive_status') == 'pending' for j in related)
    failed = sum(j.get('status') in ('failed', 'interrupted') for j in related)
    works = sum(j.get('status') == 'succeeded' and not j.get('work_deleted_at') and
                bool(j.get('result', {}).get('assets')) for j in related)
    phase = project.get('phase', 'visual')
    review = phase in ('script_review', 'asset_review')
    status = ('running' if running else 'complete' if phase == 'complete' else 'paused' if project.get('paused')
              else 'review' if review else 'draft' if phase == 'draft' or kind == 'visual' and not project.get('nodes') else 'working')
    # Never hide an automatic pipeline between two submitted jobs.
    can_archive = not running and (kind == 'visual' or project.get('paused') or phase in ('draft', 'script_review', 'asset_review', 'complete'))
    # Prefer the currently selected film, then a successful project image.
    # Return only a local display URL; credentials and remote signed URLs stay out of the index.
    film_ids = set(project.get('films', {}).values())
    candidates = sorted(related, key=lambda j: (j['id'] in film_ids, j.get('created_at', '')), reverse=True)
    cover_url = ''
    for job in candidates:
        if job.get('status') != 'succeeded' or job.get('work_deleted_at'):
            continue
        for asset in job.get('result', {}).get('assets', []):
            url = asset.get('url', '') if asset.get('type') == 'image' else asset.get('poster_url', '')
            if isinstance(url, str) and url.startswith('/media/') and '?' not in url:
                cover_url = url
                break
        if cover_url:
            break
    return {'id': identity, 'kind': kind, 'title': project['title'], 'phase': phase, 'status': status,
            'cover_url': cover_url,
            'updated_at': project['updated_at'], 'pinned': bool(meta.get('pinned')), 'archived': bool(meta.get('archived')),
            'management_version': meta.get('version', 0), 'running': running, 'failed': failed, 'works': works,
            'assets': len(project.get('plan', {}).get('assets', [])) if project.get('plan') else
                      sum(n.get('kind') != 'shot' for n in project.get('nodes', [])),
            'shots': sum(len(e.get('shots', [])) for e in (project.get('plan') or {}).get('episodes', [])) if kind == 'novel' else
                     sum(n.get('kind') == 'shot' for n in project.get('nodes', [])),
            'can_archive': can_archive}


def listing():
    jobs = storage.items('jobs', -1)
    return {'projects': [summarize(kind, p, jobs) for kind, table in TABLES.items() for p in storage.items(table, -1)]}


def organize(body):
    kind, identity, action = body.get('kind'), body.get('id'), body.get('action')
    if kind not in TABLES or not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{32}', identity):
        raise ValueError('项目不存在。')
    if action not in ('pin', 'unpin', 'archive', 'restore'):
        raise ValueError('不支持的项目管理操作。')
    with storage.LOCK:
        project = storage.get(TABLES[kind], identity)
        if not project:
            raise ValueError('项目不存在。')
        current = summarize(kind, project, storage.items('jobs', -1))
        if body.get('version') != current['management_version']:
            raise ValueError('项目管理状态已更新，请刷新后操作。')
        if action == 'archive' and not current['can_archive']:
            raise ValueError('项目仍在执行，请先在制作页暂停后归档。')
        meta = {'id': metadata_id(kind, identity), 'category': 'project_management', 'updated_at': storage.now(),
                'version': current['management_version'] + 1, 'pinned': current['pinned'], 'archived': current['archived']}
        meta['pinned' if action in ('pin', 'unpin') else 'archived'] = action in ('pin', 'archive')
        storage.put('workspace_items', meta)
        return summarize(kind, project, storage.items('jobs', -1))
