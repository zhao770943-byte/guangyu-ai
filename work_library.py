"""Delete generated files while preserving generation and usage receipts."""
import copy
import re
import storage


def local_path(url):
    if not isinstance(url, str) or not re.fullmatch(r'/media/[a-f0-9-]+\.(png|jpg|webp|gif|mp4|webm|wav|mp3|m4a|ogg|flac)', url):
        raise ValueError('作品文件路径无效，未执行删除。')
    root = (storage.DATA / 'media').resolve()
    if root != storage.DATA.resolve() / 'media':
        raise ValueError('媒体目录指向了其他位置，未执行删除。')
    path = storage.DATA / url.lstrip('/')
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError('作品文件路径超出媒体目录，未执行删除。')
    return path


def cleanup(job):
    """A durable pending list makes interrupted/locked-file cleanup retryable."""
    pending = []
    for url in job.get('work_cleanup_pending', []):
        try:
            if url.endswith(('.mp4','.webm')):
                import video_posters
                local_path(video_posters.cache_url(url)).unlink(missing_ok=True)
            local_path(url).unlink(missing_ok=True)
        except (OSError, ValueError):
            pending.append(url)
    return storage.update_job(job['id'], work_cleanup_pending=pending)


def remove(identity):
    # The caller also holds ACTIVE_LOCK, excluding generation/archive dispatch.
    with storage.LOCK:
        job = storage.get('jobs', identity)
        if not job:
            raise ValueError('作品不存在。')
        if job.get('work_deleted_at'):
            return cleanup(job) if job.get('work_cleanup_pending') else job
        if job.get('novel_project_id'):
            project = storage.get('novel_projects', job['novel_project_id'])
            if project and project['phase'] != 'complete':
                raise ValueError('此作品仍用于小说项目制作，请在项目完成后删除。')
        if job.get('film_parent_id'):
            parent = storage.get('jobs', job['film_parent_id'])
            if parent and parent['status'] != 'succeeded' and not parent.get('work_deleted_at'):
                raise ValueError('此片段仍用于整片合成，请在整片完成后删除。')
        assets = (job.get('result') or {}).get('assets', [])
        if job['status'] != 'succeeded' or job['kind'] not in ('image', 'video', 'audio') or not assets:
            raise ValueError('只能删除生成成功的媒体作品。')
        if job.get('archive_status') == 'pending':
            raise ValueError('作品正在保存，请等待完成后再删除。')
        urls = {a['url'] for a in assets if a.get('local')}
        for url in urls:
            local_path(url)  # Validate the complete set before touching records/files.
        shared = {a.get('url') for other in storage.items('jobs', -1)
                  if other['id'] != identity and not other.get('work_deleted_at')
                  for a in (other.get('result') or {}).get('assets', []) if a.get('local')}
        result = copy.deepcopy(job['result'])
        result['assets'] = []
        summary = [{k: a[k] for k in ('type', 'duration_seconds') if k in a} for a in assets]
        job = storage.update_job(identity, result=result, generated_assets_summary=summary,
                                 work_deleted_at=storage.now(), archive_status='deleted',
                                 work_cleanup_pending=sorted(urls - shared))
        return cleanup(job)
