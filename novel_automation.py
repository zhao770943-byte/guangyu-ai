"""Bounded AI editorial loops on the existing durable novel job scheduler."""
import copy
import math
import ai_control
import novel_schema as schema
import production_book as book
import storage
import novel_fidelity as fidelity

PHASES = {'auto_contracts':'细化拍摄单', 'auto_script_review':'独立审稿',
          'auto_rewrite':'编剧返修', 'auto_assets_review':'定稿像素审核', 'auto_shots_review':'分镜双重审核'}
SCRIPT_CHECKS = ('fidelity', 'dialogue', 'causality', 'timing', 'continuity', 'shootability')


def enabled(p):
    return p.get('automation', {}).get('enabled') is True


def state(p):
    return p.setdefault('automation_state', {'reports': {}, 'repairs': {}, 'image_fixes': {}, 'events': []})


def configure(p, body):
    config = body.get('automation', p.get('automation', {'enabled': False}))
    if not isinstance(config, dict) or type(config.get('enabled')) is not bool:
        raise ValueError('自动制作模式配置无效。')
    result = {'enabled': config['enabled']}
    for field, default, low, high in [('shot_target',30,16,40), ('script_revisions',2,0,3), ('image_revisions',1,0,3)]:
        n = config.get(field, default)
        if type(n) is not int or not low <= n <= high:
            raise ValueError('自动制作参数超出范围：'+field)
        result[field] = n
    p['automation'] = result
    if not enabled(p):
        return
    if not p.get('team_mode') or not p.get('ai_team', {}).get('costume', {}).get('vision'):
        raise ValueError('自动模式需要六 AI 团队，以及已确认支持图片输入的定妆审图模型。请在本页配置团队。')
    if not ai_control.resolve(p, 'costume'):
        raise ValueError('自动模式必须选择定妆审图模型，不能以文字审查代替看图。')
    p.setdefault('production_book', {})['enabled'] = True
    p['review_storyboards'] = p['review_videos'] = True
    state(p)


def density(p):
    return max(p['automation']['shot_target'], math.ceil(120/max(p['durations'])))


def validate_density(p, episode):
    if enabled(p) and not max(4, density(p)-4) <= len(episode['shots']) <= min(60, density(p)+6):
        raise ValueError(f'自动模式每集目标 {density(p)} 镜，允许少4镜至多6镜；增加有叙事作用的入场、反应、道具和过渡镜，不能重复凑时长。')


def script_version(p, episode):
    contracts = {k:v for k,v in book.book(p).get('contracts', {}).items() if k.startswith('shot:'+episode['id']+':')}
    facts = copy.deepcopy(episode)
    for shot in facts.get('shots', []):
        shot.pop('video_prompt', None)  # Later visual motion review refines wording, not shot facts.
    revision = state(p)['repairs'].get('script:'+episode['id'], 0)
    data = [p['source'], p['plan']['assets'], facts, contracts, p['ratio'], p['style'], revision]
    if fidelity.enabled(p):
        data.extend([p['production_preferences'], p['plan'].get('dialogue_ledger', [])])
    return book.digest(data)


def asset_version(p, asset):
    refs = fidelity.matched_references(p, asset)
    return book.digest([asset, p['style'], book.image_version(p['images'].get('asset:'+asset['id'])),
                        [book.image_version(r['upload_id']) for r in refs]])


def report_key(kind, identity, fingerprint):
    return 'auto:'+kind+':'+identity+':'+fingerprint[:20]


def items(p):
    phase = p['phase']; plan = p['plan']; result = []
    if phase in ('auto_contracts', 'auto_script_review', 'auto_rewrite'):
        kind = {'auto_contracts':'detail', 'auto_script_review':'script', 'auto_rewrite':'rewrite'}[phase]
        for e in plan['episodes']:
            if kind == 'rewrite' and e['id'] not in state(p).get('rewrite', {}):
                continue
            # Stable per round: detail/rewrite mutate the script during consumption.
            revision = state(p)['repairs'].get('script:'+e['id'], 0)
            fp = script_version(p,e) if kind == 'script' else book.digest([e['id'], revision, kind])
            result.append((report_key(kind,e['id'],fp), {'kind':kind,'episode':e,'fingerprint':fp}))
    elif phase == 'auto_assets_review':
        for a in plan['assets']:
            fp = asset_version(p,a)
            result.append((report_key('asset',a['id'],fp), {'kind':'asset','asset':a,'fingerprint':fp}))
    elif phase == 'auto_shots_review':
        for key,e,s,i in book.pairs(p):
            fp = book.fingerprint(p,key)
            for kind in ('frame','motion'):
                result.append((report_key(kind,e['id']+':'+s['id'],fp),
                               {'kind':kind,'episode':e,'shot':s,'slot':key,'index':i,'fingerprint':fp}))
    return result


def vision_provider(p, motion=False):
    if motion and p.get('motion_vision'):
        b = p['motion_vision']; v = storage.get('providers', b['provider_id'])
        if not v or ai_control.fingerprint(v) != b['signature']:
            raise ValueError('视觉运镜连接已变化，请恢复原连接。')
        return v
    return ai_control.resolve(p,'costume')


def task(p, key, item, prepare):
    import json
    import providers
    kind = item['kind']; role = {'detail':'camera','script':'supervisor','rewrite':'writer','asset':'costume','frame':'costume','motion':'camera'}[kind]
    visual = kind in ('asset','frame','motion')
    v = vision_provider(p, kind=='motion') if visual else ai_control.resolve(p,role)
    if not v:
        raise ValueError('自动制作缺少 '+ai_control.ROLES[role]['name']+' 模型。')
    data = {'style':p['plan']['style'], 'ratio':p['ratio']}; ids = []
    instruction = schema.SYSTEM+'\n'+ai_control.ROLES[role]['instruction']
    instruction += '\n'+p['ai_team'].get(role,{}).get('note','')
    if kind in ('detail','script','rewrite'):
        e=item['episode']; data.update(novel=p['source'], assets=p['plan']['assets'], episode=e,
            contracts={k:v for k,v in book.book(p).get('contracts',{}).items() if k.startswith('shot:'+e['id']+':')},
            shot_target=density(p), maximum_shot_seconds=max(p['durations']))
        extra_instruction, extra_data = fidelity.script_prompt(p, e)
        instruction += '\n'+(fidelity.RULES if kind == 'detail' and fidelity.enabled(p) else extra_instruction)
        data.update(extra_data)
        if kind == 'script' and fidelity.enabled(p):
            instruction += '\n逐条核对 required_dialogue 与 dialogue_omissions：真实人物问答被排除、用旁白替代、情绪或回应缺失时 dialogue 必须为 false；说明每条删改是否必要，不能只说“关键台词已保留”。'
        if kind == 'detail':
            instruction += '\n只返回 {"shots":[{"id":"现有镜号","image_prompt":"完整静态画面提示词","video_prompt":"完整动作镜头声音提示词","contract":{"start":"首帧姿势位置","beats":"按秒写少量动作节拍","end":"镜尾姿态位置","eyeline":"视线目标与轴线方向","crowd":"具体背景组、密度、距离和错时微动作","bridge":"前后镜的动作与空间衔接","avoid":"本镜禁止的额外动作","sound_mode":"native或dub或silent"}}]}。每个现有镜头恰好一项，不能增加删除镜号，不改变原文事实、对白、时长、资产。无此要素写不适用及原因。图片是单一静态时刻；视频从该时刻出发，写明前几秒的动作落点，不要一个镜头多次切镜；不要把长请求时长当成动作应拖满的时长。对白按原文，不重复报姓名；默认需要对白则native，无对白则silent，用户明确要求后期配音才dub。'
        elif kind == 'rewrite':
            data['review_feedback'] = state(p)['rewrite'][e['id']]
            instruction += '\n'+schema.SCRIPT+'\n依据独立审查意见重新写本集完整镜头表；忠于原文，不凭空加关键事件。补足入场、接近、收手、反应和退场，保留关键台词及姓名段位。目标镜数遵循 shot_target，保持120秒；逐条说明实际修改。'
        else:
            instruction += '\n你是独立终审，仅审查不改稿。必须对照原文、详细剧本和拍摄单逐项检查。返回 {"verdict":"pass或revise","checks":{"fidelity":true,"dialogue":true,"causality":true,"timing":true,"continuity":true,"shootability":true},"evidence":{"fidelity":"事实与原文具体对应","dialogue":"关键台词和重复/读音问题","causality":"动作和人物反应因果","timing":"节奏和对白时长依据","continuity":"空间、道具、人群、视线衔接","shootability":"静态首帧和动作可执行依据"},"issues":"具体问题或未发现","suggestion":"可执行修订要求或无需修改"}。任何问题为false，只有六项均通过才pass。没有看到图片，不得声称图像或视频实际效果已通过。'
    elif kind == 'asset':
        a=item['asset']; refs=fidelity.matched_references(p,a)
        ids=[r['upload_id'] for r in refs]+[p['images']['asset:'+a['id']]]
        data.update(asset=a, references=refs, image_order=['原始参考 '+r['target'] for r in refs]+['当前待审定稿'])
        instruction += '\n对照实际图片审定稿；最后一张是待审图，前面为参考，没有参考时只检查文字。返回 {"verdict":"pass或revise","checks":{"identity":true,"prop":true,"style":true},"evidence":{"identity":"外貌服饰或非人物形态依据","prop":"关键结构、材质、道具细节依据","style":"画风依据"},"issues":"实际问题或未发现","suggestion":"只修改这项图片的具体指导或无需修改"}。不可臆测未提供的官方形象。不适用项需解释原因；中性背景的多视角人物设定板正常，不能要求定稿演绎剧情。'
    else:
        s=item['shot']; e=item['episode']; i=item['index']
        data.update(shot=s, assets=[a for a in p['plan']['assets'] if a['id'] in s['asset_ids']],
                    contract=book.book(p)['contracts'][item['slot']])
        if kind == 'frame':
            ids=[p['locked_assets'][a] for a in s['asset_ids']]+[p['images'][item['slot']]]
            data['image_order']=['锁定定稿 '+a for a in s['asset_ids']]+['本镜首帧']
            checks=('identity','prop','space','crowd','eyeline','action')
            instruction += '\n实际对照前面的全部锁定定稿与最后的分镜画面，检查人物服饰、道具关键细节、站位、背景人群密度与分组、视线、首帧动作可执行性。不要把设定板多视图要求带进单帧。'
        else:
            neighbors=e['shots'][max(0,i-1):i+2]
            ids=[p['images']['shot:'+e['id']+':'+x['id']] for x in neighbors]
            data['neighbors']=neighbors
            data['neighbor_contracts']=[book.book(p)['contracts'].get('shot:'+e['id']+':'+x['id']) for x in neighbors]
            data['image_order']=[x['id']+(' 当前镜' if x['id']==s['id'] else ' 邻镜') for x in neighbors]
            checks=('space','crowd','eyeline','action','bridge')
            instruction += '\n实际比较按剧情顺序提供的前镜、本镜、后镜（边界缺邻镜正常）。判断轴线、视线、人群、道具接触方向和动作接续，不强求不同机位像素相同。发现首帧问题必须revise，不能只改视频词掩盖错误。可以补全当前镜video_prompt，严格保留原有剧情、拍摄单、对白和动作终点；不得改变镜头设计。'
        checks = fidelity.checks(p, kind, checks)
        data['required_checks']=checks
        instruction += '\n返回严格JSON {"verdict":"pass或revise","checks":{每个required_checks键:boolean},"evidence":{每个required_checks键:"基于实际像素与拍摄单的具体依据"},"issues":"具体问题或未发现","suggestion":"本镜图片修正指导或无需修改"'+(',"video_prompt":"本镜完整可执行视频提示词，含原对白及声音，不依赖其他字段"' if kind=='motion' else '')+'}。只有所有项通过才pass。不适用说明原因，不要伪称已看视频。'
    if fidelity.enabled(p) and kind in ('asset', 'frame'):
        instruction += '\n额外必需检查 clarity:boolean，并在 evidence.clarity 记录实际图片的面部、眼睛、手指、衣物边缘、关键道具纹理是否清晰；不能只因大分辨率就判清楚，发糊、融脸、重影或过度磨皮必须revise。'
    slot=p['slots'].get(key,{})
    if slot.get('repair_error'):
        data['validation_error']=slot['repair_error']
        instruction+='\n前次返回格式无效，请修正，返回完整JSON。'
    job=prepare({'provider_id':v['id'],'prompt':p['title']+' · '+PHASES[p['phase']]+' · '+key},prepare_only=True)
    job.pop('conversation_id',None)
    content=json.dumps(data,ensure_ascii=False)
    if len(content)>170000:
        raise ValueError('本阶段输入过长，请缩小章节或人工接管后精简制作资料。')
    job['messages']=[{'role':'system','content':instruction},{'role':'user','content':content}]
    job.update(ai_role=role, automation_fingerprint=item['fingerprint'])
    if visual:
        ai_control.attach_vision(v,job,ids)
        job['automation_image_versions']=[book.image_version(identity) for identity in job['vision_upload_ids']]
    providers.build(v,job)
    return job


def validate_report(value, checks):
    if value.get('verdict') not in ('pass','revise'):
        raise ValueError('审核需返回 pass 或 revise。')
    c=value.get('checks'); e=value.get('evidence')
    if not isinstance(c,dict) or not isinstance(e,dict) or any(type(c.get(k)) is not bool for k in checks):
        raise ValueError('审核检查项不完整。')
    result={'checks':{k:c[k] for k in checks}, 'evidence':{k:schema.text(e.get(k),'具体审核依据',1800) for k in checks},
            'verdict':value['verdict'], 'issues':schema.text(value.get('issues'),'审核发现',4000),
            'suggestion':schema.text(value.get('suggestion'),'修订指导',4000)}
    if (value['verdict']=='pass') != all(c[k] for k in checks):
        raise ValueError('审核结论与逐项检查不一致。')
    return result


def consume(p,key,item,slot,job):
    value=schema.parse(job['result']['text']); kind=item['kind']; st=state(p)
    if job.get('automation_fingerprint') != item['fingerprint']:
        raise ValueError('审核输入版本已变化，需要重新审查。')
    if kind in ('frame','motion','asset'):
        ids=job.get('vision_upload_ids',[])
        if not ids or job.get('automation_image_versions') != [book.image_version(i) for i in ids]:
            raise ValueError('审核图片已变化或没有真实图片输入，不能采用该结论。')
    if kind == 'detail':
        e=item['episode']; values=schema.objects(value.get('shots'),'详细拍摄单',4,60)
        if [v['id'] for v in values] != [s['id'] for s in e['shots']]:
            raise ValueError('详细拍摄单必须按原顺序包含全部镜号。')
        contracts={}; prompts=[]
        for s,v in zip(e['shots'],values):
            c=v.get('contract')
            if not isinstance(c,dict) or c.get('sound_mode') not in ('native','dub','silent'):
                raise ValueError('拍摄单缺少有效声音模式。')
            contracts['shot:'+e['id']+':'+s['id']]={**{f:schema.text(c.get(f),f,1800) for f in book.CONTRACT_FIELDS},'sound_mode':c['sound_mode']}
            prompts.append((schema.text(v.get('image_prompt'),'图片提示词',4000),schema.text(v.get('video_prompt'),'视频提示词',5000)))
            fidelity.validate_video_dialogue(p, s, prompts[-1][1], c['sound_mode'])
        for s,(im,vid) in zip(e['shots'],prompts):
            s.update(image_prompt=im,video_prompt=vid)
        p['production_book'].setdefault('contracts',{}).update(contracts)
    elif kind == 'rewrite':
        e=item['episode']; result=schema.script(value,p['plan']['assets'],max(p['durations'])); validate_density(p,result)
        fidelity.validate_script(p,e,result)
        st['events'].append({'time':storage.now(),'event':'script_rewritten','episode':e['id'],'before':copy.deepcopy(e),'job_id':job['id']})
        e.update(result)
        p['production_book']['contracts']={k:v for k,v in book.book(p).get('contracts',{}).items() if not k.startswith('shot:'+e['id']+':')}
    else:
        checks=SCRIPT_CHECKS if kind=='script' else ('identity','prop','style') if kind=='asset' else ('identity','prop','space','crowd','eyeline','action') if kind=='frame' else ('space','crowd','eyeline','action','bridge')
        checks = fidelity.checks(p, kind, checks)
        if kind == 'script':
            fidelity.validate_script(p, item['episode'], item['episode'])
        record=validate_report(value,checks)
        if kind=='motion':
            record['video_prompt']=schema.text(value.get('video_prompt'),'运镜提示词',5000)
            fidelity.validate_video_dialogue(p, item['shot'], record['video_prompt'], book.book(p).get('contracts', {}).get(item['slot'], {}).get('sound_mode', 'native'))
        record.update(fingerprint=item['fingerprint'],job_id=job['id'],source='ai_visual' if kind!='script' else 'ai_script',time=storage.now(),kind=kind,target=item.get('slot') or item.get('asset',item.get('episode',{})).get('id'))
        st['reports'][key]=record
    slot.update(done=True,invalid=False)


def reset_slot(p,key):
    slot=p['slots'].get(key)
    if not slot:
        return
    if slot.get('job_id'):
        slot.setdefault('attempts',[]).append(slot.pop('job_id'))
    slot.update(done=False,invalid=False,repairs=0)
    slot.pop('repair_error',None)


def move(p,phase):
    p.update(phase=phase,error='')
    p['history'].append({'time':storage.now(),'event':'auto_phase','phase':phase})


def transition(p):
    """Called only after all current phase receipts are consumed. No new calls here."""
    phase=p['phase']; st=state(p)
    if phase=='audit':
        move(p,'auto_contracts')
    elif phase=='auto_contracts':
        move(p,'auto_script_review')
    elif phase=='auto_rewrite':
        move(p,'auto_contracts')
    elif phase=='auto_script_review':
        failed=[(it['episode'],st['reports'][key]) for key,it in items(p) if st['reports'][key]['verdict']!='pass']
        if failed:
            for e,r in failed:
                if st['repairs'].get('script:'+e['id'],0)>=p['automation']['script_revisions']:
                    raise ValueError('剧本返修已达上限：'+e['title']+'。'+r['issues']+' 请人工接管检查。')
            st['rewrite']={e['id']:r for e,r in failed}
            for e,r in failed:
                k='script:'+e['id'];st['repairs'][k]=st['repairs'].get(k,0)+1
            move(p,'auto_rewrite')
        else:
            move(p,'assets')
    elif phase=='assets':
        move(p,'auto_assets_review')
    elif phase in ('auto_assets_review','auto_shots_review'):
        failed={}
        for key,it in items(p):
            r=st['reports'][key]
            if r['verdict']!='pass':
                target='asset:'+it['asset']['id'] if phase=='auto_assets_review' else it['slot']
                failed.setdefault(target,[]).append(r)
        if failed:
            for target,records in failed.items():
                if st['repairs'].get(target,0)>=p['automation']['image_revisions']:
                    raise ValueError('图片返修已达上限：'+target+'。'+records[0]['issues']+' 请人工接管检查。')
            for target,records in failed.items():
                st['repairs'][target]=st['repairs'].get(target,0)+1
                st['image_fixes'][target]='\n'.join(r['issues']+'；'+r['suggestion'] for r in records)
                reset_slot(p,target)
                st['events'].append({'event':'image_repair','time':storage.now(),'target':target,'reports':records})
            move(p,'assets' if phase=='auto_assets_review' else 'shots')
        elif phase=='auto_assets_review':
            p['locked_assets']={a['id']:p['images']['asset:'+a['id']] for a in p['plan']['assets']}
            move(p,'shots')
        else:
            approvals={}; prompts=[]
            for key,e,s,i in book.pairs(p):
                fp=book.fingerprint(p,key)
                rr=[st['reports'][report_key(k,e['id']+':'+s['id'],fp)] for k in ('frame','motion')]
                checks={k:all(r['checks'][k] for r in rr if k in r['checks']) for k in book.SHOT_CHECKS}
                approvals[key]={'fingerprint':fp,'checks':checks,'source':'ai_visual','job_ids':[r['job_id'] for r in rr],
                                'notes':'\n'.join(k+'：'+v for r in rr for k,v in r['evidence'].items()),'time':storage.now()}
                prompts.append((s,rr[1]['video_prompt']))
            p['production_book'].setdefault('storyboards',{}).update(approvals)
            book.require_shots(p)
            for s,prompt in prompts:s['video_prompt']=prompt
            move(p,'videos')
    elif phase=='shots':
        move(p,'auto_shots_review')
    else:
        return False
    return True


def public_state(p):
    if not enabled(p):return {'enabled':False}
    st=state(p); reports=list(st['reports'].values())
    return {'enabled':True,'target_shots':density(p),'reports':reports[-400:],
            'repair_count':sum(st['repairs'].values()),'review_count':len(reports),
            'passed_count':sum(r['verdict']=='pass' for r in reports),
            'awaiting_acceptance':p['phase'] in ('video_review','compose','complete')}


def require_ready(p):
    if not enabled(p):return
    reports=state(p)['reports']
    for e in p['plan']['episodes']:
        key=report_key('script',e['id'],script_version(p,e))
        if reports.get(key,{}).get('verdict')!='pass':
            raise ValueError('当前剧本或拍摄单尚未通过独立审查，未提交视频。')
    for a in p['plan']['assets']:
        key=report_key('asset',a['id'],asset_version(p,a))
        if reports.get(key,{}).get('verdict')!='pass' or p['locked_assets'].get(a['id'])!=p['images'].get('asset:'+a['id']):
            raise ValueError('当前定稿尚未通过像素审核，未提交视频。')
    book.require_shots(p)


def budget(p):
    remaining=p['request_limit']-p['requests_used']
    if not p.get('plan'):return {'known':False,'remaining':remaining,'minimum':None}
    phases=['outline','scripts','lighting','audit','auto_rewrite','auto_contracts','auto_script_review','assets','auto_assets_review','shots','auto_shots_review','videos','video_review','compose','complete']
    ix=phases.index(p['phase']) if p['phase'] in phases else 0
    minimum=0
    for phase in phases[ix:phases.index('video_review')]:
        if phase=='auto_rewrite' and p['phase']!='auto_rewrite':continue
        q={**p,'phase':phase}
        if phase in PHASES:
            # Before images exist their hashes are unknown: count one initial review per unit.
            try:keys=[k for k,_ in items(q)]
            except (ValueError,KeyError,OSError):
                minimum+=len(p['plan']['assets']) if phase=='auto_assets_review' else sum(2*len(e.get('shots',[])) for e in p['plan']['episodes'])
                continue
        elif phase=='outline':keys=['outline']
        elif phase in ('scripts','lighting','audit'):keys=[{'scripts':'script','lighting':'light','audit':'audit'}[phase]+':'+e['id'] for e in p['plan']['episodes']]
        elif phase=='assets':keys=['asset:'+a['id'] for a in p['plan']['assets']]
        else:keys=[('shot' if phase=='shots' else 'video')+':'+e['id']+':'+s['id'] for e in p['plan']['episodes'] for s in e.get('shots',[])]
        minimum+=sum(not p['slots'].get(k,{}).get('job_id') and not p['slots'].get(k,{}).get('done') for k in keys)
    return {'known':True,'remaining':remaining,'minimum':minimum,'sufficient':remaining>=minimum}
