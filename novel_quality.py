"""Local technical checks and minimum remaining request planning, no model calls."""
import film_compose
import storage
import work_library

REVIEW_DIMENSIONS = ('stability', 'action', 'story', 'timing', 'design')


def assessment(value):
    """Store an explicit visual/editorial verdict; technical metadata is separate."""
    if not isinstance(value, dict) or any(value.get(k) is not True for k in REVIEW_DIMENSIONS):
        raise ValueError('请逐项确认画面稳定、动作成立、剧情推进、时长合适和设计合理；有未通过项不能批准。')
    notes = value.get('notes')
    if not isinstance(notes, str) or not notes.strip() or len(notes) > 1500:
        raise ValueError('请填写本镜实际播放后的验收依据，最多1500字。')
    return {**{k: True for k in REVIEW_DIMENSIONS}, 'notes': notes.strip()}


def inspect(job, seconds, ratio=None):
    assets = (job.get('result') or {}).get('assets', [])
    asset = next((a for a in assets if a.get('type') == 'video' and a.get('local')), None)
    if job.get('status') != 'succeeded' or not asset or job.get('work_deleted_at'):
        raise ValueError('视频尚未成功保存到本机，不能批准。')
    path = work_library.local_path(asset['url'])
    with film_compose.source(path) as container:
        stream = container.streams.video[0]
        if ratio:
            width, height = map(int, ratio.split(':'))
            if abs((stream.width / stream.height) / (width / height) - 1) > .04:
                raise ValueError('视频实际画幅与项目不一致，请重做或另行处理后再批准。')
        duration = float(stream.duration * stream.time_base) if stream.duration is not None and stream.time_base else (container.duration or 0) / 1000000
        if duration < seconds - .12:
            raise ValueError('视频实际时长不足，不能进入合成，请重做此镜。')
        return {'duration': round(duration, 3), 'width': stream.width, 'height': stream.height,
                'has_audio': bool(container.streams.audio), 'job_id': job['id'], 'checked_at': storage.now()}


def budget(p):
    import novel_automation
    if novel_automation.enabled(p):
        return novel_automation.budget(p)
    if not p.get('plan'):
        return {'known': False, 'remaining': p['request_limit']-p['requests_used'], 'minimum': None}
    keys = []
    phase = p['phase']
    order = ['draft','outline','scripts','lighting','audit','script_review','assets','visual_review','asset_review','shots','shot_review','video_audit','videos','video_review','compose','complete']
    index = order.index(phase) if phase in order else 0
    if index <= order.index('assets'):
        keys += ['asset:'+a['id'] for a in p['plan']['assets']]
    if p.get('ai_team', {}).get('costume', {}).get('provider_id') and index <= order.index('visual_review'):
        keys += ['look:'+a['id'] for a in p['plan']['assets']]
    if index <= order.index('shots'):
        keys += ['shot:'+e['id']+':'+s['id'] for e in p['plan']['episodes'] for s in e.get('shots', [])]
    if index <= order.index('video_audit'):
        keys += (['visionmotion:'+e['id']+':'+s['id'] for e in p['plan']['episodes'] for s in e.get('shots', [])]
                 if p.get('motion_vision') else ['motion:'+e['id'] for e in p['plan']['episodes']])
    if index <= order.index('videos'):
        keys += ['video:'+e['id']+':'+s['id'] for e in p['plan']['episodes'] for s in e.get('shots', [])]
    needed = sum(not p.get('slots', {}).get(k, {}).get('done') and not p.get('slots', {}).get(k, {}).get('job_id') for k in keys)
    return {'known': True, 'remaining': p['request_limit']-p['requests_used'], 'minimum': needed,
            'sufficient': p['request_limit']-p['requests_used'] >= needed}


def require_budget(p):
    value = budget(p)
    if value['known'] and not value['sufficient']:
        raise ValueError(f'剩余请求上限 {value["remaining"]} 次，后续已知制作至少需 {value["minimum"]} 次（不含重试）。请提高上限后继续。')
