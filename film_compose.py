"""Local-only ordered MP4 assembly using the app's existing PyAV runtime."""
from contextlib import contextmanager
from fractions import Fraction
import storage
import work_library

FPS, RATE = 30, 48000


def check_runtime():
    try:
        import av
        av.Codec('libx264', 'w')
        av.Codec('aac', 'w')
    except Exception as exc:
        raise ValueError('本机视频合成组件不可用，请修复光屿运行环境后提交。') from exc


@contextmanager
def source(path):
    import av
    with path.open('rb') as raw, av.open(raw, format='matroska' if path.suffix == '.webm' else 'mov',
                                       options={'protocol_whitelist': 'pipe', 'enable_drefs': '0'}) as container:
        if not container.streams.video:
            raise ValueError('片段没有视频画面。')
        stream = container.streams.video[0]
        if not 0 < stream.width * stream.height <= 16_777_216:
            raise ValueError('视频尺寸超出本机合成范围。')
        stream.codec_context.thread_count = 2
        yield container


def compose(parent):
    import av
    check_runtime()
    clips = []
    for segment in parent['film_segments']:
        job = storage.get('jobs', segment['job_id'])
        assets = (job.get('result') or {}).get('assets', []) if job else []
        asset = next((a for a in assets if a.get('type') == 'video' and a.get('local')), None)
        if not asset or job.get('work_deleted_at'):
            raise ValueError('有片段尚未保存到本机，请先重试保存。')
        path = work_library.local_path(asset['url'])
        if path.suffix not in ('.mp4', '.webm') or not path.is_file():
            raise ValueError('片段文件已缺失，请恢复原文件后重试合成。')
        clips.append((segment, path))
    with source(clips[0][1]) as container:
        first = container.streams.video[0]
        # Bound local encoding to at most 1080p; retain portrait orientation.
        scale = min(1, 1920 / max(first.width, first.height), 1080 / min(first.width, first.height))
        width, height = max(2, int(first.width * scale) // 2 * 2), max(2, int(first.height * scale) // 2 * 2)
    url = '/media/' + parent['id'] + '-f.mp4'
    target = work_library.local_path(url)
    temp = target.with_suffix('.partial')
    try:
        with av.open(str(temp), 'w', format='mp4', options={'movflags': '+faststart'}) as out:
            video = out.add_stream('libx264', rate=FPS)
            video.width, video.height, video.pix_fmt = width, height, 'yuv420p'
            video.codec_context.thread_count = 2
            video.options = {'crf': '18', 'preset': 'fast'}
            audio = out.add_stream('aac', rate=RATE)
            audio.layout = 'stereo'
            audio.bit_rate = 192000
            for segment, path in clips:
                frames = round(segment['end'] * FPS) - round(segment['start'] * FPS)
                origin = _video(out, video, path, width, height, round(segment['start'] * FPS), frames)
                samples = round(segment['end'] * RATE) - round(segment['start'] * RATE)
                _audio(out, audio, path, origin, round(segment['start'] * RATE), samples)
            for stream in (video, audio):
                for packet in stream.encode(None):
                    out.mux(packet)
        # Opening the completed container verifies both tracks before committing it.
        with source(temp) as container:
            if not container.streams.audio:
                raise ValueError('本机合成未产生音轨。')
        temp.replace(target)
        return {'text': '', 'assets': [{'type': 'video', 'url': url, 'local': True, 'bytes': target.stat().st_size,
                                        'saved_at': storage.now(), 'duration_seconds': round(parent['seconds'] * FPS) / FPS}]}
    finally:
        temp.unlink(missing_ok=True)


def _video(out, stream, path, width, height, offset, count):
    with source(path) as container:
        source_stream = container.streams.video[0]
        if abs((source_stream.width / source_stream.height) / (width / height) - 1) > .04:
            raise ValueError('片段实际画幅不一致，已保留原片段，请检查后处理。')
        origin, previous, index, last_time = None, None, 0, 0
        rate = float(source_stream.average_rate or FPS)

        def emit(frame):
            nonlocal index
            result = frame.reformat(width=width, height=height, format='yuv420p')
            result.pts, result.time_base = offset + index, Fraction(1, FPS)
            for packet in stream.encode(result):
                out.mux(packet)
            index += 1

        for decoded, frame in enumerate(container.decode(source_stream)):
            if decoded > 150000:
                raise ValueError('片段帧数超出本机合成范围。')
            timestamp = float(frame.time) if frame.time is not None else decoded / rate
            if origin is None:
                origin = timestamp
            current = max(0, timestamp - origin)
            while previous is not None and index < count and index / FPS < current - .000001:
                emit(previous)
            if index >= count:
                break
            # Encoding may change frame timestamps. Keep timeline values separately.
            previous, last_time = frame, current
        if previous is None or last_time + 1 / rate < count / FPS - .12:
            raise ValueError('平台返回的片段短于计划时长，未用长时间静帧补齐；原片段已保留。')
        while index < count:
            emit(previous)
        return origin


def _audio(out, stream, path, video_origin, offset, count):
    import av
    cursor = 0

    def emit(frame, start, length):
        nonlocal cursor
        while length > 0:
            size = min(length, 4096)
            result = av.AudioFrame(format='fltp', layout='stereo', samples=size)
            result.sample_rate, result.time_base, result.pts = RATE, Fraction(1, RATE), offset + cursor
            for index, plane in enumerate(result.planes):
                plane.update(bytes(frame.planes[index])[start * 4:(start + size) * 4] if frame else bytes(size * 4))
            for packet in stream.encode(result):
                out.mux(packet)
            start, length, cursor = start + size, length - size, cursor + size

    def accept(frame):
        position = round((float(frame.time) - video_origin) * RATE) if frame.time is not None else cursor
        if position > cursor:
            emit(None, 0, min(count, position) - cursor)
        start = max(0, cursor - position)
        size = min(frame.samples - start, count - cursor)
        if size > 0:
            emit(frame, start, size)

    with source(path) as container:
        if container.streams.audio:
            resampler = av.AudioResampler(format='fltp', layout='stereo', rate=RATE)
            for frame in container.decode(container.streams.audio[0]):
                for converted in resampler.resample(frame):
                    accept(converted)
                if cursor >= count:
                    break
            else:
                for converted in resampler.resample(None):
                    accept(converted)
    if cursor < count:
        emit(None, 0, count - cursor)
