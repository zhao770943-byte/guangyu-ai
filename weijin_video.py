"""WeiJin JSON video adapter. Contract: https://www.weijinapi.top/docs/."""
from urllib.parse import urlsplit


def destination(p):
    u = urlsplit(p.get('base_url',''))
    return u.scheme == 'https' and u.hostname in ('www.weijinapi.top','weijinapi.top') and u.port in (None,443) and u.path.rstrip('/') == '/v1'


def metadata(item):
    if not isinstance(item,dict):return {}
    durations=item.get('durations_seconds',[]);ratios=item.get('ratios',[])
    if not isinstance(durations,list) or not isinstance(ratios,list):return {}
    durations=sorted(set(v for v in durations if type(v) is int and 1<=v<=120))
    ratios=list(dict.fromkeys(v for v in ratios if isinstance(v,str) and v in ('16:9','9:16','1:1','21:9','4:3','3:4','2:3','3:2')))
    if not durations or not ratios:return {}
    images=item.get('max_images',0)
    resolution=item.get('resolution','')
    return {'durations_seconds':durations,'ratios':ratios,
            'max_images':min(images,9) if type(images) is int and images>=0 else 0,
            'resolution':resolution if resolution in ('480p','720p','1080p','4K') else ''}


def profile(p):
    found=metadata(p.get('video_model_metadata'))
    if found:return found
    if p.get('model')=='seedance2.5-9图':
        return {'durations_seconds':[30],'ratios':['16:9','9:16'],'max_images':9,'resolution':'720p'}
    return {}


def validate(p,job):
    info=profile(p)
    if not info:raise ValueError('此维今型号缺少时长和画幅能力，请重新获取模型列表后保存。')
    if job.get('seconds') not in info['durations_seconds']:
        raise ValueError('当前维今型号支持的时长为 '+ '、'.join(map(str,info['durations_seconds']))+' 秒。请求尚未发送。')
    params={**p.get('extra',{}),**job.get('parameters',{})}
    ratio=params.get('aspect_ratio') or info['ratios'][0]
    if ratio not in info['ratios']:raise ValueError('当前维今型号不支持此画幅比例。请求尚未发送。')
    if params.get('resolution') and params['resolution']!=info['resolution']:
        raise ValueError('当前维今型号使用固定分辨率 '+info['resolution']+'。')
    if job.get('size','auto')!='auto':raise ValueError('维今视频使用画幅比例，请将像素尺寸设为自动。')
    refs=(job.get('input_assets') or {}).get('references',[])
    if len(refs)>info['max_images']:raise ValueError(f"当前型号最多接入 {info['max_images']} 张参考图。")
    if len(job.get('prompt',''))>10000:raise ValueError('维今视频描述最多 10000 字符。')
    return {'model':p['model'],'prompt':job['prompt'],'seconds':job['seconds'],'aspect_ratio':ratio}


def execute(p,job):
    import providers, storage
    # Refresh actual key capabilities before uploading inputs or charging generation.
    catalog=providers.request(p,'/models')
    rows=catalog.get('data',[])
    item=next((v for v in rows if isinstance(v,dict) and v.get('id')==p['model']),None) if isinstance(rows,list) else None
    if item is None:raise ValueError('当前密钥的目录中没有该视频型号，请重新获取模型。尚未提交生成。')
    live=metadata(item)
    if not live:raise ValueError('平台未返回此视频型号的时长和比例能力，尚未提交生成。')
    current={**p,'video_model_metadata':live}
    body=validate(current,job)
    images=[]
    for identity in (job.get('input_assets') or {}).get('references',[]):
        upload_provider={**p,'base_url':p['base_url'].removesuffix('/v1')}
        response=providers.request(upload_provider,'/api/upload/video',{'file':providers.FilePart(identity)},multipart=True)
        url=response.get('url') or providers.dig(response,'data.url')
        if not isinstance(url,str) or urlsplit(url).scheme!='https' or not urlsplit(url).hostname:
            raise ValueError('素材上传未返回可用的 HTTPS 地址，尚未提交视频生成。')
        images.append(url)
    if images:body['images']=images
    result=providers.request(p,'/videos',body)
    providers.record_response(p,job['id'],result)
    identity=result.get('id') or result.get('task_id')
    if not isinstance(identity,str) or not identity or len(identity)>300:
        raise providers.ProviderError('视频提交未返回有效任务 ID，请先在平台核对任务；不要直接重复生成。',uncertain=True)
    job=storage.update_job(job['id'],upstream_id=identity,status='polling')
    return providers.poll(p,job,result)
