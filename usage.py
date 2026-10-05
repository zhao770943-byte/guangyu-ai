"""Read-only, local-workspace usage reporting. Never an account billing ledger.

Token fields contain only reported usage. None means unknown, not zero. Cache
and reasoning counts are informational subsets and never added to totals.
"""
import csv
import hashlib
import io
import json
import math
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import storage


SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')
TOKEN_FIELDS = ('input_tokens', 'output_tokens', 'total_tokens',
                'cached_input_tokens', 'reasoning_tokens')
TERMINAL = {'succeeded', 'failed', 'interrupted'}
PERIODS = {'today': ('今天', 1), '7d': ('最近 7 天', 7),
           '30d': ('最近 30 天', 30), 'all': ('全部记录', None)}


def _datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None
    else:
        return None
    # The application's storage timestamps are UTC. Preserve that interpretation
    # for older records with a missing explicit offset.
    return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed)


def _number(value, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    if integer:
        return int(value) if int(value) == value else None
    return value


def _tokens(job):
    result = job.get('result') if isinstance(job.get('result'), dict) else {}
    usage = job.get('usage')
    if not isinstance(usage, dict):
        usage = result.get('usage')
    usage = usage if isinstance(usage, dict) else {}
    tokens = {field: _number(usage.get(field), integer=True) for field in TOKEN_FIELDS}
    # Do not trust a provider total to be a sum if both canonical operands exist.
    # Adapters normalize provider-specific cache conventions before this layer.
    if tokens['input_tokens'] is not None and tokens['output_tokens'] is not None:
        tokens['total_tokens'] = tokens['input_tokens'] + tokens['output_tokens']
    elif tokens['total_tokens'] is None:
        tokens['total_tokens'] = _number(usage.get('reported_total_tokens'), integer=True)
    source = usage.get('source')
    tokens['usage_source'] = str(source)[:80] if source else None
    return tokens


def _safe_url(value):
    try:
        parts = urlsplit(str(value or ''))
        # No credentials or query values belong in reports or downloads.
        host = parts.hostname or ''
        if ':' in host:
            host = '[' + host + ']'
        if parts.port:
            host += ':' + str(parts.port)
        return urlunsplit((parts.scheme, host, parts.path, '', ''))
    except ValueError:
        return ''


def _identity(provider=None, job=None):
    provider = provider or {}
    job = job or {}
    snapshot = job.get('provider_snapshot') or provider
    if not isinstance(snapshot, dict):
        snapshot = {}
    info = {
        'provider_id': str(job.get('provider_id', snapshot.get('id', '')) or ''),
        'provider_name': str(job.get('provider_name', snapshot.get('name', '未命名连接')) or '未命名连接'),
        'model': str(job.get('model', snapshot.get('model', '未知模型')) or '未知模型'),
        'kind': str(job.get('kind', snapshot.get('kind', '')) or ''),
        'protocol': str(snapshot.get('protocol', '') or ''),
        'base_url': _safe_url(snapshot.get('base_url', '')),
    }
    # Changes to connection labels, models, or endpoints must not rewrite history.
    key = tuple(info.values())
    info['row_id'] = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:20]
    return key, info


def _empty_metrics():
    return {
        'requests': 0, 'succeeded': 0, 'failed': 0, 'interrupted': 0, 'active': 0,
        'input_tokens': None, 'output_tokens': None, 'total_tokens': None,
        'cached_input_tokens': None, 'reasoning_tokens': None,
        'usage_reported_requests': 0, 'usage_missing_requests': 0,
        'token_complete_requests': 0, 'token_incomplete_requests': 0,
        'image_count': 0, 'video_count': 0, 'audio_count': 0, 'video_seconds': None,
        'requested_video_seconds': 0,
        '_latencies': [],
    }


def _add_known(metrics, field, amount):
    if amount is not None:
        metrics[field] = (metrics[field] or 0) + amount


def _elapsed(job):
    elapsed = _number(job.get('elapsed_ms'))
    if elapsed is not None:
        return round(elapsed, 2)
    started, finished = _datetime(job.get('started_at')), _datetime(job.get('finished_at'))
    if started is not None and finished is not None and finished >= started:
        return round((finished - started).total_seconds() * 1000, 2)
    return None


def _accumulate(metrics, job, tokens, elapsed):
    metrics['requests'] += 1
    status = job.get('status', '')
    metrics[status if status in TERMINAL else 'active'] += 1
    reported = any(tokens[field] is not None for field in ('input_tokens', 'output_tokens', 'total_tokens'))
    metrics['usage_reported_requests' if reported else 'usage_missing_requests'] += 1
    metrics['token_complete_requests' if tokens['total_tokens'] is not None else 'token_incomplete_requests'] += 1
    for field in TOKEN_FIELDS:
        _add_known(metrics, field, tokens[field])
    if status in TERMINAL and elapsed is not None:
        metrics['_latencies'].append(elapsed)
    if status != 'succeeded':
        return
    result = job.get('result') if isinstance(job.get('result'), dict) else {}
    assets = (job.get('generated_assets_summary') or []) if job.get('work_deleted_at') else (result.get('assets') if isinstance(result.get('assets'), list) else [])
    images = [asset for asset in assets if isinstance(asset, dict) and asset.get('type') == 'image']
    videos = [asset for asset in assets if isinstance(asset, dict) and asset.get('type') == 'video']
    metrics['image_count'] += len(images)
    metrics['video_count'] += len(videos)
    metrics['audio_count'] += len([asset for asset in assets if isinstance(asset,dict) and asset.get('type')=='audio'])
    if videos:
        requested = _number(job.get('seconds'))
        if requested is not None:
            metrics['requested_video_seconds'] += requested * len(videos)
        # Requested duration does not verify the returned file's duration.
        durations = [_number(asset.get('duration_seconds')) for asset in videos]
        for duration in durations:
            _add_known(metrics, 'video_seconds', duration)
        if len(videos) == 1 and durations[0] is None:
            _add_known(metrics, 'video_seconds', _number(result.get('duration_seconds')))


def _finish(metrics):
    latencies = metrics.pop('_latencies')
    metrics['avg_latency_ms'] = round(sum(latencies) / len(latencies), 2) if latencies else None
    metrics['latency_reported_requests'] = len(latencies)
    terminal = metrics['succeeded'] + metrics['failed'] + metrics['interrupted']
    metrics['success_rate'] = round(metrics['succeeded'] * 100 / terminal, 1) if terminal else None
    metrics['error_rate'] = round((metrics['failed'] + metrics['interrupted']) * 100 / terminal, 1) if terminal else None
    metrics['coverage_percent'] = round(metrics['token_complete_requests'] * 100 / metrics['requests'], 1) if metrics['requests'] else None
    return metrics


def _read_records(table):
    if table not in {'jobs', 'providers'}:
        raise ValueError('未知记录类型。')
    # storage.items defaults to 200 records; accounting intentionally has no cap.
    with closing(storage.connect()) as conn:
        return [json.loads(row['payload']) for row in conn.execute('SELECT payload FROM ' + table)]


def build_report(jobs=None, providers=None, period='7d', now=None, request_limit=100):
    """Aggregate all selected records; only the displayed request list is capped.

    Date periods are calendar dates in Asia/Shanghai, including today. Pass
    request_limit=None for a full selected-period CSV export. Explicit iterables
    make isolated tests possible without reading the user's database.
    """
    if period not in PERIODS:
        raise ValueError('统计范围应为 today、7d、30d 或 all。')
    if request_limit is not None and (type(request_limit) is not int or request_limit < 0):
        raise ValueError('请求数量限制无效。')
    clock = _datetime(now) if now is not None else datetime.now(timezone.utc)
    if clock is None:
        raise ValueError('统计时间无效。')
    clock = clock.astimezone(SHANGHAI)
    label, days = PERIODS[period]
    first_day = clock.date() - timedelta(days=days - 1) if days else None
    start = datetime.combine(first_day, time.min, SHANGHAI) if first_day else None
    jobs = _read_records('jobs') if jobs is None else list(jobs)
    providers = _read_records('providers') if providers is None else list(providers)
    summary = _empty_metrics()
    models, daily, records = {}, {}, []
    for provider in providers:
        key, info = _identity(provider=provider)
        models[key] = {**info, 'connected': True, 'historical': False, **_empty_metrics()}
    selected = []
    for job in jobs:
        if job.get('film_batch'):
            continue  # Local assembly is not another provider request.
        stamp = _datetime(job.get('created_at'))
        if stamp is None:
            if period != 'all':
                continue
        elif stamp > clock or (start is not None and stamp < start):
            continue
        selected.append((stamp, job))
    dated = [stamp.astimezone(SHANGHAI).date() for stamp, _ in selected if stamp]
    first_day = first_day or (min(dated) if dated else clock.date())
    for offset in range((clock.date() - first_day).days + 1):
        day = (first_day + timedelta(days=offset)).isoformat()
        daily[day] = {'date': day, **_empty_metrics()}
    undated = 0
    for stamp, job in selected:
        # Older records without a snapshot use only available submission fields.
        key, info = _identity(job=job)
        if key not in models:
            models[key] = {**info, 'connected': False, 'historical': True, **_empty_metrics()}
        tokens = _tokens(job)
        elapsed = _elapsed(job)
        _accumulate(summary, job, tokens, elapsed)
        _accumulate(models[key], job, tokens, elapsed)
        if stamp:
            _accumulate(daily[stamp.astimezone(SHANGHAI).date().isoformat()], job, tokens, elapsed)
        else:
            undated += 1
        records.append({
            'id': str(job.get('id', '')), 'created_at': stamp.isoformat() if stamp else None,
            **{name: info[name] for name in ('provider_id', 'provider_name', 'model', 'kind')},
            'response_model': str((job.get('result') or {}).get('response_model') or job.get('response_model') or '')
                if isinstance(job.get('result') or {}, dict) else '',
            'status': str(job.get('status', '')), **tokens, 'elapsed_ms': elapsed,
        })
    records.sort(key=lambda row: (_datetime(row['created_at']) or datetime.min.replace(tzinfo=timezone.utc), row['id']), reverse=True)
    summary.update(connected_models=sum(row['connected'] for row in models.values()),
                   historical_models=sum(row['historical'] for row in models.values()),
                   undated_requests=undated)
    rows = [_finish(row) for row in models.values()]
    rows.sort(key=lambda row: (not row['connected'], -row['requests'], row['provider_name'], row['model']))
    return {
        'period': {'key': period, 'label': label, 'timezone': 'Asia/Shanghai',
                   'start': start.isoformat() if start else None, 'end': clock.isoformat(),
                   'scope': 'local_workspace', 'request_limit': request_limit},
        'summary': _finish(summary), 'models': rows,
        'daily': [_finish(row) for row in daily.values()],
        'requests': records if request_limit is None else records[:request_limit],
    }


def _csv_cell(value):
    if value is None:
        return ''
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    value = str(value)
    # Spreadsheet applications may execute formulas even when the CSV cell is
    # quoted. Prefix dangerous leading characters (including whitespace tricks).
    if value.startswith(('\t', '\r', '\n')) or value.lstrip().startswith(('=', '+', '-', '@')):
        value = "'" + value
    return value


def csv_export(report):
    """Return UTF-8-BOM-ready text with safe cells and blank unknown counts."""
    output = io.StringIO(newline='')
    output.write('\ufeff')
    writer = csv.writer(output)
    columns = (
        ('id', '请求 ID'), ('created_at', '提交时间'), ('provider_name', '连接名称'),
        ('model', '提交模型'), ('response_model', '返回模型'), ('kind', '用途'),
        ('status', '状态'), ('input_tokens', '输入 Token'), ('output_tokens', '输出 Token'),
        ('total_tokens', '合计 Token'), ('cached_input_tokens', '缓存输入 Token（输入子集）'),
        ('reasoning_tokens', '推理 Token（输出子集）'), ('elapsed_ms', '耗时 ms'),
        ('usage_source', '用量来源'),
    )
    writer.writerow([title for _, title in columns])
    for row in report.get('requests', []):
        writer.writerow([_csv_cell(row.get(name)) for name, _ in columns])
    return output.getvalue()
