"""Deterministic timeline partitioning, before any provider submission."""
import math
import capabilities
import storage
import video_controls


def plan(body):
    provider = storage.get('providers', body.get('provider_id', ''))
    if not provider or provider['kind'] != 'video' or not capabilities.effective(provider)['reference_images']:
        raise ValueError('请选择支持参考图的视频模型。')
    mode = body.get('execution_mode', 'serial')
    if mode not in ('serial', 'parallel'):
        raise ValueError('提交方式应为串行或并行。')
    lengths = body.get('durations')
    if not isinstance(lengths, list) or not 2 <= len(lengths) <= 9 or any(type(t) not in (int, float) or not math.isfinite(t) or t < .1 for t in lengths):
        raise ValueError('请为 2–9 个分镜填写有效时长，至少 0.1 秒。')
    total = round(sum(lengths), 3)
    if not 1 <= total <= 600:
        raise ValueError('整片时长支持 1–600 秒。')
    options = video_controls.options(provider)
    if not options['duration_enabled']:
        raise ValueError('此模型未配置可控时长，无法按时间拆段。')
    if provider['protocol'] == 'weijin_video':
        import weijin_video
        info = weijin_video.profile(provider)
        candidates, max_images = info.get('durations_seconds', []), info.get('max_images', 0)
    else:
        ceiling = max(options['durations'], default=0)
        candidates, max_images = range(1, ceiling + 1), 8
    allowed = []
    for value in candidates:
        try:
            video_controls.validate(provider, 'auto', value)
            allowed.append(value)
        except ValueError:
            pass
    allowed = sorted(set(allowed))
    if not allowed or max_images < 1:
        raise ValueError('此模型缺少可用时长或参考图能力，请刷新模型配置。')
    timeline, clock = [], 0
    for index, length in enumerate(lengths):
        end = round(clock + length, 3)
        timeline.append({'index': index, 'start': clock, 'end': end})
        clock = end
    segments, start = [], 0
    while start < total - .0001:
        end = min(total, round(start + allowed[-1], 3))
        shots = [t for t in timeline if t['end'] > start + .0001 and t['start'] < end - .0001]
        if len(shots) > max_images:
            end = shots[max_images]['start']
            shots = shots[:max_images]
        used = round(end - start, 3)
        requested = next(s for s in allowed if s >= used - .0001)
        segments.append({'index': len(segments) + 1, 'start': start, 'end': end, 'used_seconds': used,
                         'request_seconds': requested, 'shots': [dict(t, start=max(start, t['start']), end=min(end, t['end']), offset=round(max(start-t['start'], 0), 3)) for t in shots]})
        start = end
    return {'seconds': total, 'requested_seconds': sum(s['request_seconds'] for s in segments),
            'execution_mode': mode, 'concurrency': 3 if mode == 'parallel' else 1,
            'segments': segments, 'model_durations': allowed}
