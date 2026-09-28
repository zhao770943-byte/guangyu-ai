"""Bounded, local-only video poster extraction; old works need no migration."""
import hashlib
import threading
import storage
import work_library

LOCK=threading.Lock()

def cache_url(url):
    return '/media/'+hashlib.sha256(('video-poster-v1:'+url).encode()).hexdigest()+'.jpg'

def public_asset(job, index, asset):
    if asset.get('type')=='video' and asset.get('local') and not job.get('work_deleted_at'):
        return {**asset,'poster_url':f"/api/video-poster?id={job['id']}&index={index}"}
    return asset

def get(identity,index):
    import av
    from PIL import ImageStat
    # Exclude deletion while reading/caching. Never fetch a provider URL here.
    with storage.LOCK, LOCK:
        job=storage.get('jobs',identity)
        if not job or job.get('work_deleted_at') or job.get('status')!='succeeded':raise ValueError('视频作品不存在。')
        assets=(job.get('result') or {}).get('assets',[])
        if type(index) is not int or not 0<=index<len(assets):raise ValueError('视频序号无效。')
        asset=assets[index]
        if asset.get('type')!='video' or not asset.get('local'):raise ValueError('视频尚未保存到本机。')
        source=work_library.local_path(asset['url'])
        if source.suffix not in ('.mp4','.webm') or not source.is_file():raise ValueError('视频文件不存在。')
        target=work_library.local_path(cache_url(asset['url']))
        if target.is_file() and target.stat().st_mtime_ns>=source.stat().st_mtime_ns:return target
        best=None;score=-1
        try:
            # Explicit demuxers prevent a disguised playlist from fetching URLs.
            with source.open('rb') as raw, av.open(raw,format='mov' if source.suffix=='.mp4' else 'matroska',
                                                  options={'protocol_whitelist':'pipe','enable_drefs':'0'}) as container:
                stream=container.streams.video[0]
                if not 0<stream.width*stream.height<=16_777_216:raise ValueError('视频尺寸超出封面解码范围。')
                stream.codec_context.thread_count=2
                for number,frame in enumerate(container.decode(stream)):
                    if number>=48:break
                    image=frame.to_image();image.thumbnail((640,640))
                    stat=ImageStat.Stat(image.convert('L'))
                    value=stat.stddev[0] if 8<stat.mean[0]<247 else -0.5
                    if value>score:best=image;score=value
                    if number>=6 and score>12:break
            if best is None:raise ValueError('视频没有可解码画面。')
            temp=target.with_suffix('.part')
            try:
                best.convert('RGB').save(temp,format='JPEG',quality=88)
                temp.replace(target)
            finally:temp.unlink(missing_ok=True)
        except Exception as ex:
            raise ValueError('视频封面暂时无法提取，仍可打开原视频。') from ex
        return target
