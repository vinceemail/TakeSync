from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from threading import Event, Thread
from queue import Queue, Empty
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from .models import Media


class Cancelled(Exception):
    pass


def check_cancel(cancel: Event | None) -> None:
    if cancel and cancel.is_set():
        raise Cancelled('Cancelled. Original files were not changed.')


def binary(name: str) -> str:
    suffix = '.exe' if sys.platform == 'win32' else ''
    roots = [Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))]
    for root in roots:
        candidate = root / 'vendor' / (name + suffix)
        if candidate.is_file():
            return str(candidate)
    override = os.environ.get('TAKESYNC_' + name.upper())
    found = override or shutil.which(name)
    if not found:
        raise RuntimeError(f'{name} is missing. Use the complete TakeSync distribution, '
                           'or install FFmpeg for development.')
    return found


def process_options() -> dict:
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}


def run_ffmpeg(arguments: list[str], cancel: Event | None = None,
               progress=None, duration: float = 0) -> None:
    """Drain subprocess output without freezing cancellation or the UI."""
    check_cancel(cancel)
    command = [binary('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-y', '-progress', 'pipe:1', '-nostats'] + arguments
    queue: Queue = Queue()
    with tempfile.TemporaryFile(mode='w+b') as errors:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors,
                                text=True, encoding='utf-8', errors='replace', **process_options())
        def read_output():
            for line in proc.stdout:
                queue.put(line.strip())
        reader = Thread(target=read_output, daemon=True)
        reader.start()
        started = time.monotonic()
        try:
            while proc.poll() is None or not queue.empty():
                check_cancel(cancel)
                if time.monotonic() - started > max(120, duration * 30):
                    raise RuntimeError('FFmpeg took too long. Check that the source media is readable.')
                try:
                    line = queue.get(timeout=.1)
                except Empty:
                    continue
                if progress and duration and line.startswith('out_time_us='):
                    try:
                        progress(min(1., max(0., int(line.split('=')[1]) / 1e6 / duration)))
                    except ValueError:
                        pass
            proc.wait()
            if proc.returncode:
                errors.seek(0)
                detail = errors.read().decode('utf-8', errors='replace')[-2500:]
                raise RuntimeError('Could not process media.\n' + detail)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            reader.join(timeout=2)
            proc.stdout.close()


def fingerprint(path: str, extra: str = '') -> str:
    p = Path(path).resolve()
    s = p.stat()
    return hashlib.sha256(f'{p}|{s.st_size}|{s.st_mtime_ns}|{extra}'.encode()).hexdigest()[:24]


def probe(path: str, video_required: bool = False) -> Media:
    p = Path(path).expanduser().resolve(strict=True)
    result = subprocess.run([binary('ffprobe'), '-v', 'error', '-show_format', '-show_streams',
                             '-of', 'json', str(p)], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=40, **process_options())
    if result.returncode:
        raise ValueError(f'Cannot read {p.name}: {result.stderr[-1000:]}')
    data = json.loads(result.stdout)
    video = next((s for s in data.get('streams', []) if s['codec_type'] == 'video'
                  and not s.get('disposition', {}).get('attached_pic')), None)
    audio = next((s for s in data.get('streams', []) if s['codec_type'] == 'audio'), None)
    if not audio:
        raise ValueError(f'{p.name} has no audio stream. Camera audio is needed for alignment.')
    if video_required and not video:
        raise ValueError(f'{p.name} is not a video file.')
    stream = video if video_required else audio
    duration = float(stream.get('duration') or data['format'].get('duration') or 0)
    if duration <= 0:
        raise ValueError(f'{p.name} has no usable duration.')
    avg = (video or {}).get('avg_frame_rate', '25/1')
    if avg in ['0/0', '0/1']:
        avg = video.get('r_frame_rate', '25/1')
    fps = Fraction(avg)
    if fps <= 0 or fps > 240:
        raise ValueError(f'{p.name} has an unsupported frame rate.')
    tags = (video or audio).get('tags', {})
    tc = tags.get('timecode', data.get('format', {}).get('tags', {}).get('timecode', '00:00:00:00'))
    variable = bool(video and video.get('r_frame_rate', avg) != avg)
    return Media(str(p), duration, str(fps), (video or {}).get('width', 0),
                 (video or {}).get('height', 0), int(audio.get('channels', 2)),
                 int(audio.get('sample_rate', 48000)), tc, variable)


def extract_audio(media: Media, cache: Path, cancel=None, progress=None) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (fingerprint(media.path, 'mono22050-v1') + '.wav')
    if target.exists():
        return target
    tmp = target.with_name(target.stem + '.partial.wav')
    try:
        run_ffmpeg(['-i', media.path, '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '22050',
                    '-c:a', 'pcm_s16le', str(tmp)], cancel, progress, media.duration)
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def timecode_start(media: Media) -> Fraction:
    """Only for media interchange; NEVER used to infer musical alignment."""
    try:
        tc = media.timecode
        h, m, s, f = map(int, tc.replace(';', ':').split(':'))
        nominal = round(float(media.rate))
        count = (3600 * h + 60 * m + s) * nominal + f
        if ';' in tc and media.rate in [Fraction(30000, 1001), Fraction(60000, 1001)]:
            drop = 2 if nominal == 30 else 4
            minutes = h * 60 + m
            count -= drop * (minutes - minutes // 10)
        return Fraction(count, 1) / media.rate
    except (ValueError, ZeroDivisionError):
        return Fraction(0)
