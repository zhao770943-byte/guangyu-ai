"""Volcengine Ark native Seedream/Seedance request contracts.

Official API: /images/generations and /contents/generations/tasks.
Uses the selected destination only; never guesses a gateway from model names.
"""
import re
import uploads

VIDEO_PATH='/contents/generations/tasks'
RATIOS=('16:9','9:16','1:1','4:3','3:4','21:9')


def supported(model,kind):
    prefix=r'^doubao-seedance-2-[05](?:-|$)' if kind=='video' else r'^doubao-seedream-(?:4-[05]|5-0)(?:-|$)'
    return bool(re.match(prefix,str(model).lower()))


def max_duration(model):
    return 30 if str(model).startswith('doubao-seedance-2-5') else 15


def build(p,job,inputs,params):
    if not supported(p['model'],p['kind']):raise ValueError('此方舟适配支持 Seedream 4/5 或 Seedance 2.0/2.5，请重新选择型号。')
    if p.get('extra'):raise ValueError('方舟媒体使用已适配参数，请先清空附加 JSON 参数。')
    if job.get('size','auto')!='auto':raise ValueError('方舟媒体请保持像素尺寸自动，视频使用画幅比例。')
    body={'model':p['model']}
    if p['kind']=='image':
        body.update(prompt=job['prompt'],response_format='url')
        if inputs['references']:body['image']=[uploads.data_uri(i) for i in inputs['references']]
        return '/images/generations',body,False
    seconds=job.get('seconds',4)
    if type(seconds) is not int or not 4<=seconds<=max_duration(p['model']):
        raise ValueError(f"此 Seedance 型号支持 4–{max_duration(p['model'])} 秒。")
    if inputs['last_frame'] and not inputs['first_frame']:raise ValueError('尾帧需要同时选择首帧。')
    if inputs['references'] and (inputs['first_frame'] or inputs['last_frame']):raise ValueError('参考图模式与首尾帧模式请二选一。')
    ratio=params.get('aspect_ratio','adaptive')
    if ratio not in RATIOS+('adaptive',):raise ValueError('此 Seedance 接口不支持所选画幅。')
    content=[{'type':'text','text':job['prompt']}]
    for role,ids in [('first_frame',[inputs['first_frame']]),('last_frame',[inputs['last_frame']]),('reference_image',inputs['references'])]:
        for identity in filter(None,ids):content.append({'type':'image_url','image_url':{'url':uploads.data_uri(identity)},'role':role})
    body.update(content=content,duration=seconds,ratio=ratio)
    for key,target in [('seed','seed'),('audio','generate_audio')]:
        if key in params:body[target]=params[key]
    return VIDEO_PATH,body,False


def polling_provider(p):
    return {**p,'protocol':'custom','custom':{'poll_path':VIDEO_PATH+'/{id}',
        'status_path':'status','success_values':['succeeded'],
        'failure_values':['failed','cancelled','expired'],'media_path':'content.video_url'}}
