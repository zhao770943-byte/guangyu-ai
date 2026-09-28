"""Persist generated media using bounded, unauthenticated GET requests only."""
import copy
import hashlib
import http.client
import ipaddress
import socket
import time
from urllib.parse import urlsplit, urljoin
import storage

MAX_BYTES = 512 * 1024 * 1024
MAX_SECONDS = 180

class SaveError(Exception):
    pass

def extension(head, kind):
    if kind == 'image':
        if head.startswith(b'\x89PNG\r\n\x1a\n'):return 'png'
        if head.startswith(b'\xff\xd8\xff'):return 'jpg'
        if head[:6] in (b'GIF87a', b'GIF89a'):return 'gif'
        if head[:4] == b'RIFF' and head[8:12] == b'WEBP':return 'webp'
    if kind == 'video':
        if head[4:8] == b'ftyp':return 'mp4'
        if head[:4] == b'\x1aE\xdf\xa3':return 'webm'
    if kind == 'audio':
        if head[:4] == b'RIFF' and head[8:12] == b'WAVE':return 'wav'
        if head[:3] == b'ID3' or (len(head)>1 and head[0]==255 and head[1]&0xe0==0xe0):return 'mp3'
        if head[:4] == b'fLaC':return 'flac'
        if head[:4] == b'OggS':return 'ogg'
        if head[4:8] == b'ftyp':return 'm4a'
    raise SaveError('返回内容不是受支持的媒体文件，原平台链接已保留。')

def connection(url, provider):
    parsed=urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or any(ord(c)<32 for c in url):
        raise SaveError('平台返回的作品地址无效。')
    host=parsed.hostname;port=parsed.port or (443 if parsed.scheme=='https' else 80)
    source=urlsplit(provider.get('base_url',''))
    source_port=source.port or (443 if source.scheme=='https' else 80)
    allow_loopback=provider.get('allow_local') and host==source.hostname and port==source_port
    addresses=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    if not addresses:raise SaveError('无法解析作品下载地址。')
    for address in addresses:
        ip=ipaddress.ip_address(address[4][0])
        if not ip.is_global and not (allow_loopback and ip.is_loopback):
            raise SaveError('作品地址指向未授权的本地或内网服务，无法自动保存。')
    cls=http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection
    conn=cls(host,port,timeout=15)
    # Pin the validated address; HTTPS still verifies the original hostname.
    conn._create_connection=lambda address,timeout,source_address=None: socket.create_connection((addresses[0][4][0],port),timeout,source_address)
    return conn,parsed

def download(asset, job, index):
    url=asset['url'];deadline=time.monotonic()+MAX_SECONDS
    temp=None
    try:
        for hop in range(6):
            conn,parsed=connection(url,job.get('provider_snapshot',{}))
            try:
                conn.request('GET',parsed.path+('?' + parsed.query if parsed.query else '') or '/',headers={'Accept':'image/*,video/*,audio/*,application/octet-stream','User-Agent':'GuangyuAI-MediaStore'})
                response=conn.getresponse()
                if response.status in (301,302,303,307,308):
                    destination=response.getheader('Location')
                    if not destination or hop==5:raise SaveError('作品下载重定向次数过多或地址缺失。')
                    url=urljoin(url,destination)
                    continue
                if response.status!=200:raise SaveError(f'原平台文件返回 HTTP {response.status}，尚未保存。链接可能已失效；重试保存不会重新生成。')
                length=response.getheader('Content-Length')
                if length and int(length)>MAX_BYTES:raise SaveError('作品超过 512 MiB，无法自动保存，请从原平台下载。')
                head=response.read(64)
                ext=extension(head,asset['type'])
                name=job['id']+'-'+hashlib.sha256((str(index)+asset['url']).encode()).hexdigest()[:16]+'.'+ext
                path=storage.DATA/'media'/name;temp=path.with_suffix('.partial')
                total=len(head)
                if total>MAX_BYTES:raise SaveError('作品超过大小限制，无法自动保存。')
                with temp.open('wb') as target:
                    target.write(head)
                    while True:
                        if time.monotonic()>deadline:raise SaveError('作品保存超时，可稍后重试保存。')
                        chunk=response.read1(256*1024)
                        if not chunk:break
                        total+=len(chunk)
                        if total>MAX_BYTES:raise SaveError('作品超过 512 MiB，无法自动保存。')
                        target.write(chunk)
                if length and total!=int(length):raise SaveError('下载未完成，原作品链接已保留，请重试保存。')
                temp.replace(path)
                return {**asset,'url':'/media/'+name,'source_url':asset['url'],'local':True,'saved_at':storage.now(),'bytes':total,'save_error':None}
            finally:conn.close()
    finally:
        if temp and temp.exists():temp.unlink()

def archive(identity):
    """Persist each asset independently; a failed download never undoes generation."""
    job=storage.get('jobs',identity)
    result=copy.deepcopy(job.get('result') or {})
    assets=result.get('assets',[])
    try:
        for index,asset in enumerate(assets):
            if asset.get('local'):continue
            try:assets[index]=download(asset,job,index)
            except SaveError as exc:asset['save_error']=str(exc)
            except OSError:asset['save_error']='网络连接或本机文件写入失败，请检查网络、磁盘空间后重试保存。'
            except Exception:asset['save_error']='作品下载失败，原平台链接已保留，请重试保存。'
            storage.update_job(identity,result=result)
    finally:
        saved=sum(bool(a.get('local')) for a in assets)
        storage.update_job(identity,result=result,archive_status='saved' if saved==len(assets) else 'partial' if saved else 'failed',archive_finished_at=storage.now())
