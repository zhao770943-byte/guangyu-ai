"""Persist generated media using bounded, unauthenticated GET requests only."""
import copy
import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
import urllib.request
import urllib.error
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
    def connect_validated(address, timeout, source_address=None):
        last_error = None
        for candidate in addresses:
            try:
                return socket.create_connection((candidate[4][0], port), timeout, source_address)
            except OSError as exc:
                last_error = exc
        raise last_error
    conn._create_connection=connect_validated
    if parsed.scheme=='https':
        original_connect=conn.connect
        def connect_https():
            last_error=None
            for candidate in addresses:
                conn._create_connection=lambda address,timeout,source_address=None: socket.create_connection((candidate[4][0],port),timeout,source_address)
                try:
                    original_connect()
                    return
                except ssl.SSLCertVerificationError:
                    conn.close()
                    raise
                except OSError as exc:
                    conn.close()
                    last_error=exc
            raise last_error
        conn.connect=connect_https
    return conn,parsed

def download(asset, job, index):
    url=asset['url'];deadline=time.monotonic()+MAX_SECONDS
    temp=None
    try:
        # This provider CDN is reachable through the user's existing system proxy.
        # Keep the exception narrow: public HTTPS image host, no credentials or redirects.
        parsed = urlsplit(url)
        if asset['type'] == 'image' and parsed.scheme == 'https' and parsed.hostname == 'media.lensapi.cn' and urllib.request.getproxies().get('https'):
            validated, _ = connection(url, {})
            validated.close()
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args):
                    raise SaveError('代理下载发生重定向，请核对原作品地址。')
            try:
                opener = urllib.request.build_opener(NoRedirect())
                with opener.open(urllib.request.Request(url, headers={'Accept':'image/*','User-Agent':'GuangyuAI-MediaStore'}), timeout=15) as response:
                    if response.status != 200:
                        raise SaveError('原平台图片下载未成功。')
                    raw = response.read(10*1024*1024+1)
                    if len(raw)>10*1024*1024:
                        raise SaveError('代理图片超过 10 MiB 上限。')
                ext = extension(raw[:64], 'image')
                name = job['id']+'-'+hashlib.sha256((str(index)+url).encode()).hexdigest()[:16]+'.'+ext
                path = storage.DATA/'media'/name;temp=path.with_suffix('.partial')
                temp.write_bytes(raw);temp.replace(path)
                return {**asset,'url':'/media/'+name,'source_url':url,'local':True,'saved_at':storage.now(),'bytes':len(raw),'save_error':None}
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, ssl.SSLCertVerificationError):
                    raise SaveError('媒体服务器证书验证失败。') from exc
                # An unavailable proxy can still fall back to validated direct HTTPS.
        for hop in range(6):
            conn,parsed=connection(url,job.get('provider_snapshot',{}))
            try:
                request_headers={'Accept':'image/*,video/*,audio/*,application/octet-stream','User-Agent':'GuangyuAI-MediaStore'}
                provider=job.get('provider_snapshot',{})
                if asset.get('authenticated_content') and provider.get('protocol')=='weijin_video' and hop==0:
                    import providers
                    from urllib.parse import quote
                    expected=providers.endpoint(provider,'/videos/'+quote(str(job.get('upstream_id','')),safe='')+'/content')
                    if url!=expected:raise SaveError('鉴权作品地址与原任务不匹配。')
                    request_headers.update(providers.headers(provider))
                conn.request('GET',parsed.path+('?' + parsed.query if parsed.query else '') or '/',headers=request_headers)
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
