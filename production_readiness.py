"""Read-only production facts for the desk. Never dispatch or imply visual approval."""
import re
import production_book as book
import novel_fidelity as fidelity
import novel_quality
import storage


def local_media(job, kind):
    if not job or job.get('status') != 'succeeded' or job.get('work_deleted_at'):
        return None
    for asset in job.get('result', {}).get('assets', []):
        url = asset.get('url', '')
        extensions = 'wav|mp3|m4a|ogg|flac|aac|opus' if kind == 'audio' else 'mp4|webm|mov|mkv'
        if asset.get('type') != kind or not re.fullmatch(r'/media/[a-zA-Z0-9_-]+\.('+extensions+')', url):
            continue
        path = storage.DATA / url.lstrip('/')
        try:
            if path.is_file() and path.stat().st_size and path.resolve().parent == (storage.DATA/'media').resolve():
                return {'job_id': job['id'], 'url': url}
        except OSError:
            pass
    return None


def audio_reference(identity):
    job = storage.get('jobs', identity) if identity else None
    return local_media(job, 'audio') if job and job.get('kind') == 'audio' else None


def report(p, public):
    plan = p.get('plan') or {}; episodes = plan.get('episodes', [])
    images = public.get('image_assets', {}); state = public.get('production_state', {})
    jobs = {j['id']: j for j in public.get('jobs', [])}
    rows = []; elapsed = {}; totals = {'images': 0, 'videos': 0, 'reviewed': 0}
    for index, (key, e, s, i) in enumerate(book.pairs(p)):
        start = elapsed.get(e['id'], 0); elapsed[e['id']] = start + s['seconds']
        image = images.get(p.get('images', {}).get(key)); c = book.book(p).get('contracts', {}).get(key, {})
        vk = key.replace('shot:', 'video:', 1); job = jobs.get(p.get('slots', {}).get(vk, {}).get('job_id'))
        video = bool(local_media(job, 'video'))
        review = p.get('video_reviews', {}).get(vk, {})
        reviewed = bool(video and review.get('job_id') == job['id'])
        if reviewed and p.get('review_standard') == 'five_dimensions':
            try: novel_quality.assessment(review.get('assessment'))
            except ValueError: reviewed = False
        notes = []
        if not image: notes.append('缺少分镜图')
        missing = [k for k in book.CONTRACT_FIELDS if not c.get(k)]
        if missing: notes.append('拍摄单缺 '+str(len(missing))+' 项')
        if image and min(image.get('width', 0), image.get('height', 0)) < 720: notes.append('短边不足720px，检查细节')
        if s['seconds'] >= 10 and not s.get('dialogue'): notes.append('长无对白镜头，检查动作密度')
        if c.get('sound_mode') == 'silent' and s.get('dialogue'): notes.append('无声方案与对白冲突')
        if fidelity.speech_units(s.get('dialogue', '')) > s['seconds'] * 5: notes.append('对白密度偏高')
        shot_state = state.get('shots', {}).get(key, {})
        if shot_state.get('status') == 'stale': notes.append('分镜版本变化，需重审')
        rows.append({'index': index, 'key': key, 'episode_id': e['id'], 'shot_id': s['id'], 'start': start, 'end': elapsed[e['id']],
                     'image': bool(image), 'width': image.get('width') if image else None, 'height': image.get('height') if image else None,
                     'video': video, 'video_reviewed': reviewed, 'notes': notes, 'sound_mode': c.get('sound_mode', 'dub')})
        totals['images'] += bool(image); totals['videos'] += video; totals['reviewed'] += reviewed
    assets = plan.get('assets', []); locked = sum(bool(images.get(p.get('locked_assets', {}).get(a['id']))) for a in assets)
    voices = [{**{'asset_id': v['asset_id'], 'configured': bool(v.get('voice')), 'bound': bool(v.get('audio_job_id'))},
               'available': bool(audio_reference(v.get('audio_job_id')))} for v in book.book(p).get('voices', [])]
    current_ids = {s.get('job_id') for s in p.get('slots', {}).values()} | set(p.get('films', {}).values())
    current = [j for identity, j in jobs.items() if identity in current_ids]
    failures = [j for j in current if j.get('status') in ('failed', 'interrupted')]
    active = [j for j in current if j.get('status') in ('queued', 'submitting', 'polling') or j.get('archive_status') == 'pending']
    films = [jobs.get(identity) for identity in p.get('films', {}).values()]
    missing_films = sum(j is None or j.get('status') == 'succeeded' and not local_media(j, 'video') for j in films)
    films = [j for j in films if local_media(j, 'video')]
    legacy = not state.get('enabled')
    script_done = sum(bool(e.get('shots')) for e in episodes)
    script_pending = p.get('phase') in ('draft','outline','scripts','lighting','audit','auto_contracts','auto_rewrite','auto_script_review','script_review')
    dialogue_issues = (public.get('fidelity_report') or {}).get('issues', [])
    stages = [
        {'id': 'script', 'title': '详细剧本', 'done': script_done, 'total': len(episodes), 'detail': '集已编排', 'status': 'attention' if dialogue_issues or p.get('needs_audit') else 'recorded' if script_done and script_pending else 'ready' if script_done and script_done == len(episodes) else 'pending'},
        {'id': 'assets', 'title': '定稿资产', 'done': locked, 'total': len(assets), 'detail': '项已锁定', 'status': 'ready' if assets and locked == len(assets) else 'pending'},
        {'id': 'shots', 'title': '分镜审核', 'done': state.get('approved', 0), 'total': len(rows), 'detail': '镜当前版本已审', 'status': 'legacy' if legacy else 'ready' if rows and state.get('approved') == len(rows) else 'pending'},
        {'id': 'tasks', 'title': '视频验收', 'done': totals['reviewed'], 'total': len(rows), 'detail': '镜已实际验收', 'status': 'legacy' if legacy else 'ready' if rows and totals['reviewed'] == len(rows) else 'pending'},
        {'id': 'sound', 'title': '声音方案', 'done': sum(v['available'] for v in voices), 'total': sum(a['kind'] == 'character' for a in assets)+sum(v['asset_id'].startswith('voice:') and (v['bound'] or v['configured']) for v in voices), 'detail': '位已绑定可用试听', 'status': 'attention' if any(v['bound'] and not v['available'] for v in voices) else 'recorded' if any(v['configured'] for v in voices) else 'pending'},
        {'id': 'delivery', 'title': '成片交付', 'done': len(films), 'total': len(episodes), 'detail': '集已有成片', 'status': 'ready' if state.get('delivery_approved') else 'attention' if films else 'pending'}]
    tasks = []
    def todo(tab, title, detail, shot=None):
        tasks.append({'tab': tab, 'title': title, 'detail': detail, 'shot': shot})
    if p.get('error'): todo('tasks', '处理当前制作异常', p['error'])
    elif failures and p.get('phase') != 'complete': todo('tasks', '检查当前任务', str(len(failures))+' 个当前任务失败或中断；历史重试不重复计入。')
    if dialogue_issues: todo('script', '核对原文对白', dialogue_issues[0])
    if not episodes or script_done < len(episodes): todo('script', '完成详细剧本', '先建立逐镜动作、对白与时长。')
    elif p.get('phase') == 'script_review': todo('script', '审核详细剧本', '逐句核对对白、因果、镜头节奏后确认。')
    if missing_films: todo('delivery', '检查成片文件', '已登记的成片尚未成功保存或文件已不可用。')
    if assets and locked < len(assets): todo('assets', '确认定稿资产', str(len(assets)-locked)+' 项尚未锁定或文件缺失。')
    if not legacy and rows and state.get('approved', 0) < len(rows):
        first = next((r for r in rows if state.get('shots', {}).get(r['key'], {}).get('status') != 'approved'), None)
        todo('shots', '检查当前分镜', str(len(rows)-state.get('approved', 0))+' 镜尚未通过当前版本审核。', first['index'] if first else None)
    for issue in book.book(p).get('issues', []):
        if not issue.get('resolved'):
            r = next((r for r in rows if r['key'] == issue.get('shot')), None)
            todo('shots' if r else 'overview', issue['category'], issue['notes'], r['index'] if r else None)
    if not legacy and totals['videos'] > totals['reviewed']: todo('tasks', '播放视频并逐镜验收', str(totals['videos']-totals['reviewed'])+' 段视频等待实际效果检查。')
    if any(v['bound'] and not v['available'] for v in voices): todo('sound', '替换不可用的试听', '部分声音引用已删除或文件缺失，原记录仍保留。')
    elif script_done and not any(v['available'] for v in voices): todo('sound', '整理可复用的角色声音', '尚未登记可用试听；已有作品不会因此重做。')
    if films and not state.get('delivery_approved'): todo('delivery', '检查当前成片', '完整观看、试听后确认当前版本。')
    if p.get('phase') == 'complete': tasks.sort(key=lambda x: x['tab'] != 'delivery')
    return {'legacy': legacy, 'stages': stages, 'tasks': tasks, 'shots': rows, 'voices': voices,
            'current_failed': len(failures), 'active': len(active), 'totals': totals,
            'planned_seconds': sum(elapsed.values()), 'film_seconds': sum(next((a.get('duration_seconds') or j.get('seconds') or 0 for a in j.get('result', {}).get('assets', []) if a.get('type') == 'video'), 0) for j in films)}
