"""Video output options and validation; native and mapped controls stay distinct."""
import re
import capabilities

# Platform labels describe composition, not every platform's upload requirement.
RATIOS = [('9:16','抖音竖屏','720x1280'), ('16:9','B站横屏','1280x720'),
          ('1:1','方形视频','720x720'), ('3:4','小红书竖屏','720x960'),
          ('4:3','经典横屏','960x720'), ('2:3','竖向短片','720x1080'),
          ('3:2','摄影横屏','1080x720'), ('4:5','社交竖屏','720x900'),
          ('5:4','横向短片','900x720'), ('21:9','电影宽屏','1680x720'),
          ('9:21','全屏竖屏','720x1680'), ('2:1','宽屏短片','1440x720'),
          ('1:2','长幅竖屏','720x1440')]


def sora_model(p):
    if p.get('protocol') != 'openai_video':return ''
    model=p.get('model','').lower()
    if re.match(r'^sora-2-pro(?:$|-)',model):return 'pro'
    if re.match(r'^sora-2(?:$|-)',model):return 'standard'
    return ''


def options(p):
    c=capabilities.effective(p)
    mapped=capabilities.mapped_controls(p)
    sora=sora_model(p)
    mode='native' if sora else 'aspect' if c['aspect_ratio'] else 'pixels' if mapped['size'] else 'none'
    ratios=[]
    if sora:
        for ratio,label,size in RATIOS:
            sizes={}
            if ratio in ('9:16','16:9'):
                sizes['720p']=size
                if sora=='pro':sizes['1080p']='1080x1920' if ratio=='9:16' else '1920x1080'
            ratios.append({'value':ratio,'label':label,'sizes':sizes,'enabled':bool(sizes)})
        if sora=='pro':
            ratios += [{'value':'4:7','label':'扩展竖屏','sizes':{'1024p':'1024x1792'},'enabled':True},
                       {'value':'7:4','label':'扩展横屏','sizes':{'1024p':'1792x1024'},'enabled':True}]
    else:
        for ratio,label,size in RATIOS:
            w,h=map(int,size.split('x'))
            ratios.append({'value':ratio,'label':label,'sizes':{'720p':size,'1080p':f'{w*3//2}x{h*3//2}'},'enabled':mode!='none'})
    return {'mode':mode,'ratios':ratios,'durations':[4,8,12,16,20] if sora else [4,5,6,8,10,12,15,20],
            'duration_enabled':mapped['seconds'],'custom_duration':not bool(sora),
            'custom_size':mode=='pixels','sora':sora,
            'audio_note':'声音与画面由 Sora 同步生成；此协议不提供独立声音开关，可在镜头描述中表达声音要求。' if sora else ''}


def validate(p,size,seconds):
    if p.get('kind')!='video':return
    if type(seconds) is not int or not 1<=seconds<=120:
        raise ValueError('视频时长应为 1–120 秒的整数。')
    sora=sora_model(p)
    if sora:
        if seconds not in (4,8,12,16,20):
            raise ValueError('Sora 视频时长支持 4、8、12、16、20 秒，请选择对应档位。请求尚未发送。')
        sizes={'720x1280','1280x720'}
        if sora=='pro':sizes|={'1024x1792','1792x1024','1080x1920','1920x1080'}
        effective_size=size if size!='auto' else (p.get('extra') or {}).get('size','auto')
        if effective_size!='auto' and effective_size not in sizes:
            raise ValueError('当前视频模型不支持此尺寸。Sora 2 使用 720p 横屏/竖屏；1024p 扩展画幅及 1080p 需 Sora 2 Pro。请求尚未发送。')
    elif p.get('protocol')=='custom':
        mapped=capabilities.mapped_controls(p)
        if size!='auto' and not mapped['size']:
            raise ValueError('此视频接口未映射像素尺寸，请使用已配置的画幅比例或保持自动。')
        if seconds!=4 and not mapped['seconds']:
            raise ValueError('此视频接口未映射时长，请使用平台默认设置。')
