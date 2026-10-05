"""Opt-in source dialogue accounting and immutable continuity snapshots."""
import copy
import re
import unicodedata
import ai_control
import image_controls
import novel_schema as schema
import storage
import uploads

RULES = '''人物对话尽量逐句保留原文的语气、称呼、回应、停顿与情绪转折，不能只留结论、关键词或改成旁白概述。
保留问答的来回、沉默和对方反应，让对白推动人物关系。表演要求写在动作/拍摄单，dialogue只放人物名和实际说出的台词。
同一长句可跨正反打或反应镜头连续说完，按实际语速预留呼吸，不加速念词；不能为两分钟或镜数删对白。
按对白容量合理分集；超过可处理的6集应报告容量问题，不能悄悄删掉后半章。补充的反应和转场必须有因果，不制造重复报幕。
画面保留面部、眼睛、手指和关键道具的可辨细节，主体清晰，景深合理；不用过度虚化、磨皮、强光和运动模糊掩盖瑕疵。'''


def enabled(p):
    return p.get('production_preferences', {}).get('version') == 1


def quotes(source):
    # Quoted labels and thoughts are candidates too: the director must explain exclusions.
    pattern = r'“([^“”]+)”|「([^「」]+)」|『([^『』]+)』|"([^"\n]+)"'
    result = []
    for match in re.finditer(pattern, source):
        value = next(v for v in match.groups() if v is not None).strip()
        if len(value) < 2:
            continue
        result.append({'id': 'd'+str(len(result)+1), 'text': value, 'offset': match.start(),
                       'context': source[max(0, match.start()-40):min(len(source), match.end()+40)]})
    if len(result) > 400:
        raise ValueError('本次章节含超过400处引语，请按场次拆分，避免遗漏对白。')
    return result


def configure(p, body):
    prefs = body.get('production_preferences', p.get('production_preferences'))
    if prefs is None:
        return  # Existing API clients and legacy projects retain their contracts.
    if not isinstance(prefs, dict) or prefs.get('version') != 1:
        raise ValueError('制作标准版本无效。')
    p['production_preferences'] = {'version': 1, 'dialogue': 'preserve', 'image_detail': 'high'}
    quotes(p['source'])
    identity = body.get('continuity_project_id', p.get('continuity_project_id', ''))
    p['continuity_project_id'] = identity
    if not identity:
        p.pop('continuity_snapshot', None)
        return
    old = storage.get('novel_projects', identity) if isinstance(identity, str) else None
    if not old or old['id'] == p['id']:
        raise ValueError('请选择另一部已有小说项目作为前作。')
    version = body.get('continuity_source_version')
    if version != old['version']:
        raise ValueError('前作版本已更新，请重新选择前作后保存。')
    items = []
    for asset in (old.get('plan') or {}).get('assets', []):
        image = old.get('locked_assets', {}).get(asset['id'])
        if image:
            uploads.get(image)
            items.append({'asset': copy.deepcopy(asset), 'upload_id': image})
    if not items:
        raise ValueError('前作没有已锁定的定稿，请先确认前作资产，或从作品库手动选择参考。')
    p['continuity_source_version'] = version
    p['continuity_snapshot'] = {'project_id': identity, 'version': version, 'title': old['title'],
        'assets': items, 'voices': copy.deepcopy(old.get('production_book', {}).get('voices', [])),
        'mix_notes': old.get('production_book', {}).get('mix_notes', '')}


def outline_prompt(p):
    if not enabled(p):
        return '', {}
    rows = quotes(p['source'])
    instruction = RULES + '''
另返回 dialogue_assignments:[{"id":"d1","episode_id":"e1","speaker":"人物名"}] 和
dialogue_omissions:[{"id":"d2","reason":"为什么属于非对白引语、重复资料或不可避免删减"}]。
source_dialogue中的每一条恰好归入一个集或排除记录，不重复、不漏项。绝大多数真实对白应保留。
按原句总量以约每秒4个汉字预估对白，再留出动作、对方反应和停顿；每集120秒，必要时多分集，勿只看章节字数。
continuity_assets是前作已锁定资料。未换装/未换场景的相同资产保持name、kind、description、prompt原样，换装或形态变化应建新资产并说明原因。'''
    return instruction, {'source_dialogue': rows,
        'continuity_assets': [r['asset'] for r in p.get('continuity_snapshot', {}).get('assets', [])]}


def bind_outline(p, plan, value):
    if not enabled(p):
        return
    source = {r['id']: r for r in quotes(p['source'])}
    assigned, omissions = value.get('dialogue_assignments', []), value.get('dialogue_omissions', [])
    if not isinstance(assigned, list) or not isinstance(omissions, list):
        raise ValueError('需要完整的对白分集与排除清单。')
    episode_ids = {e['id'] for e in plan['episodes']}
    ledger, seen = [], set()
    for row, keep in [(r, True) for r in assigned] + [(r, False) for r in omissions]:
        if not isinstance(row, dict) or row.get('id') not in source or row['id'] in seen:
            raise ValueError('原文引语清单含重复或未知编号。')
        seen.add(row['id'])
        entry = {**source[row['id']], 'status': 'keep' if keep else 'omitted'}
        if keep:
            if row.get('episode_id') not in episode_ids:
                raise ValueError('对白需要分配到有效剧集。')
            entry.update(episode_id=row['episode_id'], speaker=schema.text(row.get('speaker'), '说话人', 80))
        else:
            entry['reason'] = schema.text(row.get('reason'), '引语排除依据', 1200)
        ledger.append(entry)
    if seen != set(source):
        raise ValueError('原文引语未逐条分配，缺少：'+ '、'.join(sorted(set(source)-seen))+'。不可静默省略人物对话。')
    plan['dialogue_ledger'] = sorted(ledger, key=lambda r: r['offset'])
    for e in plan['episodes']:
        units = sum(speech_units(r['text']) for r in ledger if r.get('episode_id') == e['id'])
        if units > 420:
            raise ValueError('本集原对白较多，需增加集数为动作与停顿留时间；不能删台词来满足120秒。')


def normalize(text):
    return ''.join(c.lower() for c in unicodedata.normalize('NFKC', text) if c.isalnum())


def speech_units(text):
    return len(re.findall(r'[\u3400-\u9fff]', text)) + 1.5 * len(re.findall(r'[A-Za-z]+', text))


def episode_lines(p, episode):
    return [r for r in p.get('plan', {}).get('dialogue_ledger', []) if r.get('episode_id') == episode['id']]


def validate_script(p, episode, result):
    if not enabled(p):
        return
    required = episode_lines(p, episode)
    known = {r['id'] for r in required}
    for shot in result['shots']:
        if any(identity not in known for identity in shot.get('dialogue_ids', [])):
            raise ValueError('镜头引用了不属于本集的原文对白。')
        spoken = re.sub(r'(?:^|[\n；;])[^：:\n；;]{1,20}[:：]', '', shot['dialogue'])
        if speech_units(spoken) > shot['seconds'] * 5:
            raise ValueError('镜头 '+shot['id']+' 的台词无法自然说完，请延长有效对白时长或跨镜承接，不能删句或加速。')
    # Match occurrences, not just substrings: two identical source replies must
    # occupy two actual stretches of dialogue. Coordinates also preserve order
    # when several people speak within one shot.
    spoken_shots = [normalize(re.sub(r'(?:^|[\n；;])[^：:\n；;]{1,20}[:：]', '', s['dialogue'])) for s in result['shots']]
    consumed = set(); positions = []
    for row in required:
        selected = [(i, s) for i, s in enumerate(result['shots']) if row['id'] in s.get('dialogue_ids', [])]
        if not selected:
            raise ValueError('缺少原文对白 '+row['id']+'（'+row['speaker']+'），请恢复原句及对白编号。')
        spoken = ''.join(spoken_shots[i] for i, _ in selected)
        coordinates = [(i, n) for i, _ in selected for n in range(len(spoken_shots[i]))]
        target = normalize(row['text']); start = spoken.find(target); chosen = None
        while target and start >= 0:
            points = coordinates[start:start+len(target)]
            if not any(point in consumed for point in points):
                chosen = points; break
            start = spoken.find(target, start+1)
        if not chosen:
            raise ValueError('原文对白 '+row['id']+' 被删改或截断，请完整保留；可跨连续镜头承接。')
        consumed.update(chosen); positions.append(chosen[0])
    if positions != sorted(positions):
        raise ValueError('人物对话次序改变，请保持问答与回应顺序。')


def script_prompt(p, episode):
    if not enabled(p):
        return '', {}
    return RULES+'\n每镜返回dialogue_ids:["d1"]，无对应原文引语则为空。跨镜连续说同一句可在相关镜头重复该编号，但实际台词不能重复；将原句拆成顺序连续的片段。审校和润色也须保留这些编号与原句。', {
        'required_dialogue': episode_lines(p, episode),
        'dialogue_omissions': [r for r in p.get('plan', {}).get('dialogue_ledger', []) if r['status'] == 'omitted']}


def validate_video_dialogue(p, shot, prompt, sound_mode):
    if not enabled(p) or sound_mode != 'native':
        return
    for line in re.split(r'[\n；;]', shot.get('dialogue', '')):
        spoken = re.sub(r'^[^：:]{1,20}[:：]', '', line).strip()
        if normalize(spoken) and normalize(spoken) not in normalize(prompt):
            raise ValueError('同期声视频提示词漏了镜头 '+shot['id']+' 的实际台词，请保留完整对白后再提交。')


def matched_references(p, asset):
    rows = ai_control.matched(p, asset)
    names = {asset['name']} | set(re.split(r'[,、]', asset.get('aliases', '')))
    for item in p.get('continuity_snapshot', {}).get('assets', []):
        old = item['asset']
        if old['kind'] == asset['kind'] and old['name'] in names and item['upload_id'] not in {r['upload_id'] for r in rows}:
            rows.append({'upload_id': item['upload_id'], 'scope': 'asset', 'target': old['name']})
    return rows


def inherit_assets(p):
    """Reuse only locked pixels with exactly unchanged visual specifications."""
    snap = p.get('continuity_snapshot', {})
    mapping, pending = {}, []
    for item in snap.get('assets', []):
        old = item['asset']
        asset = next((a for a in p['plan']['assets'] if all(a.get(k) == old.get(k) for k in ('kind', 'name', 'description', 'prompt'))), None)
        if not asset:
            continue
        uploads.get(item['upload_id'])
        key = 'asset:'+asset['id']
        if key in p['slots']:
            continue
        pending.append((key, item['upload_id'], old['id']))
        mapping[old['id']] = asset['id']
    for key, upload_id, original_id in pending:
        p['images'][key] = upload_id
        p['slots'][key] = {'done': True, 'attempts': [], 'reused_from': {'project_id': snap['project_id'], 'asset_id': original_id, 'version': snap['version'], 'upload_id': upload_id}}
    if mapping:
        voices = []
        for row in snap.get('voices', []):
            aid = row['asset_id']
            if aid in mapping or aid in ('voice:narrator', 'voice:announcer', 'voice:crowd'):
                voices.append({**row, 'asset_id': mapping.get(aid, aid)})
        book = p.setdefault('production_book', {})
        book['voices'] = voices
        book['mix_notes'] = snap.get('mix_notes', '')
    # Current asset and storyboard approval still runs; no historical approval is copied.


def invalidate_changed_reuse(p, plan):
    old = {r['asset']['id']: r['asset'] for r in p.get('continuity_snapshot', {}).get('assets', [])}
    current = {a['id']: a for a in plan['assets']}
    for key, slot in list(p['slots'].items()):
        provenance = slot.get('reused_from')
        if not provenance:
            continue
        original, asset = old.get(provenance['asset_id'], {}), current.get(key.split(':', 1)[1], {})
        if any(original.get(k) != asset.get(k) for k in ('kind', 'name', 'description', 'prompt')):
            p['slots'].pop(key)
            p['images'].pop(key, None)
            p['locked_assets'].pop(asset.get('id'), None)


def image_settings(p, provider, size, params):
    if not enabled(p):
        return size, params
    opts = image_controls.options(provider)
    if opts['mode'] in ('custom', 'none'):
        return size, params  # An alias or unadvertised mapping is not a known 2K contract.
    result = dict(params)
    quality = {q[0] for q in opts['quality']}
    existing = provider.get('extra', {}).get('quality')
    if 'high' in quality and existing not in ('high', 'hd', 'xhigh', 'max'):
        result['quality'] = 'high'
    elif 'hd' in quality and existing != 'hd':
        result['quality'] = 'hd'
    if opts['mode'] == 'pixels':
        ratio = next((r for r in opts['ratios'] if r['value'] == p['ratio']), None)
        if ratio and ratio['sizes'].get('large'):
            size = ratio['sizes']['large']
    elif opts['mode'] == 'aspect' and any(level[0] == '2K' for level in opts['levels']):
        result['resolution'] = '2K'
    return size, result


def checks(p, kind, base):
    return (*base, 'clarity') if enabled(p) and kind in ('asset', 'frame') else base


def report(p):
    if not enabled(p):
        return None
    ledger = (p.get('plan') or {}).get('dialogue_ledger', [])
    issues = []
    for episode in (p.get('plan') or {}).get('episodes', []):
        if episode.get('shots'):
            try:
                validate_script(p, episode, episode)
            except ValueError as exc:
                issues.append(str(exc))
    return {'quoted_lines': len(ledger), 'retained': sum(r['status'] == 'keep' for r in ledger),
        'omissions': [r for r in ledger if r['status'] == 'omitted'], 'issues': issues,
        'reused_assets': sum(bool(s.get('reused_from')) and s['reused_from'].get('upload_id') == p.get('images', {}).get(k) for k, s in p.get('slots', {}).items()),
        'source_title': p.get('continuity_snapshot', {}).get('title', '')}
