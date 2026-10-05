"""Durable film scheduling. Only never-claimed segments may be auto-submitted."""
import copy
import json
import storage

ACTIVE = {'queued', 'submitting', 'polling'}


def change(job, **fields):
    if any(job.get(k) != v for k, v in fields.items()):
        return storage.update_job(job['id'], **fields)
    return job


def tick(dispatch, compose, active, lock):
    with lock, storage.LOCK:
        for parent in reversed(storage.items('jobs', -1)):
            if not parent.get('film_batch') or parent['status'] == 'succeeded' or parent.get('work_deleted_at'):
                continue
            if parent.get('film_phase') in ('composing', 'compose_failed'):
                continue
            jobs = [storage.get('jobs', s['job_id']) for s in parent['film_segments']]
            done = sum(bool(j) and j['status'] == 'succeeded' and j.get('archive_status') == 'saved' for j in jobs)
            change(parent, film_completed=done)
            issue = next((j for j in jobs if not j or j.get('work_deleted_at') or j['status'] in ('failed', 'interrupted') or (j['status'] == 'succeeded' and j.get('archive_status') in ('failed', 'partial'))), None)
            if any(j is None for j in jobs) or issue:
                change(parent, status='interrupted', film_phase='paused', error='部分片段需要处理，已完成片段已保留。请在下方查询原任务、重试保存或仅重试失败片段。')
                continue
            if done == len(jobs):
                if compose and parent['id'] not in active:
                    parent = change(parent, status='polling', film_phase='composing', error='')
                    compose(parent)
                continue
            parent = change(parent, status='polling', film_phase='generating', error='')
            limit = 3 if parent['film_execution_mode'] == 'parallel' else 1
            running = sum(j.get('film_dispatch_state') != 'waiting' and (j['status'] in ACTIVE or j.get('archive_status') == 'pending') for j in jobs)
            for job in jobs:
                if running >= limit or len(active) >= 12:
                    break
                if job.get('film_dispatch_state') != 'waiting':
                    continue
                # Commit the claim before handing off to the provider executor.
                # A crash in between is uncertain and must never trigger a second POST.
                job = storage.update_job(job['id'], film_dispatch_state='claimed')
                try:
                    dispatch(job)
                except Exception:
                    storage.update_job(job['id'], status='interrupted', error='任务交接被中断，请核对原任务后处理。未自动重复提交。')
                    break
                running += 1


def retry(body, active, lock):
    with lock, storage.LOCK:
        parent = storage.get('jobs', body.get('id', ''))
        if not parent or not parent.get('film_batch') or parent.get('work_deleted_at'):
            raise ValueError('整片任务不存在。')
        if parent['id'] in active:
            raise ValueError('整片仍在合成，请等待完成。')
        previous = body.get('retry_job_id')
        if not previous:
            if parent.get('film_phase') != 'compose_failed':
                raise ValueError('当前没有需要重试的本机合成。')
            return storage.public_job(storage.update_job(parent['id'], status='polling', film_phase='generating', error=''))
        segment = next((s for s in parent['film_segments'] if s['job_id'] == previous or previous in s['attempts']), None)
        if not segment:
            raise ValueError('片段不属于此整片。')
        if segment['job_id'] != previous:
            return storage.public_job(parent)  # A repeated retry receipt returns its existing replacement.
        job = storage.get('jobs', previous)
        if previous in active or not job or job['status'] != 'failed':
            raise ValueError('仅可重新生成已失败的片段；状态未确认的任务请先查询原任务。')
        child = {k: copy.deepcopy(job[k]) for k in ('kind', 'provider_id', 'provider_name', 'model', 'provider_snapshot', 'prompt', 'size', 'seconds', 'input_assets', 'parameters', 'capabilities_snapshot', 'mapped_controls_snapshot', 'request_timeout_seconds', 'collection_id', 'visual_project_id', 'visual_film_timeline', 'film_parent_id', 'film_segment_index') if k in job}
        child.update(id=storage.uid(), created_at=storage.now(), updated_at=storage.now(), status='queued', result={'text': '', 'assets': []}, error='', upstream_id='', usage=None, film_dispatch_state='waiting')
        segment['attempts'].append(previous)
        segment['job_id'] = child['id']
        parent.update(status='polling', film_phase='generating', error='', updated_at=storage.now())
        project = storage.get('visual_projects', parent['visual_project_id'])
        if project:
            project.setdefault('film_job_ids', []).append(child['id'])
        with storage.connect() as db:
            for item in (parent, child):
                db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?)', (item['id'], item['created_at'], json.dumps(item, ensure_ascii=False)))
            if project:
                db.execute('UPDATE visual_projects SET payload=? WHERE id=?', (json.dumps(project, ensure_ascii=False), project['id']))
        return storage.public_job(parent)
