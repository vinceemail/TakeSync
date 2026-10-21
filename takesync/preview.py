"""A lightweight, CPU-rendered proxy makes playback share ONE media clock."""
from pathlib import Path
import hashlib
import json
import shutil

from .models import Project, camera_window
from .media import run_ffmpeg, fingerprint, check_cancel


def render(project: Project, cache: Path, cancel=None, progress=None) -> Path:
    notify = progress or (lambda value, text: None)
    identity = {'media': [fingerprint(x.path) for x in [project.camera_a, project.camera_b, project.master]],
                'fps': project.fps, 'delta': project.camera_delta,
                'sections': [(s.start, s.end, s.offset) for s in project.sections], 'version': 2}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    target = Path(cache) / ('preview-'+key+'.mp4')
    if target.exists():
        notify(1., 'Preview ready')
        return target
    folder = Path(cache) / ('preview-'+key+'.work')
    folder.mkdir(parents=True, exist_ok=True)
    rate = float(project.rate)
    # Split at physical source limits as well as edit boundaries so uncovered
    # material is visibly black, never a frozen or invented source frame.
    spans = []
    for section in project.sections:
        points = {section.start, section.end}
        for camera in ['A', 'B']:
            window = camera_window(project, section, camera)
            if window:
                points.update(window[:2])
        points = sorted(points)
        spans.extend((section, a, b) for a, b in zip(points, points[1:]) if b > a)
    try:
        for index, (section, start, end) in enumerate(spans):
            check_cancel(cancel)
            piece = folder / f'{index:05d}.mp4'
            if piece.exists():
                continue
            frames = end-start
            duration = frames/rate
            args = []
            for camera in ['A', 'B']:
                media = project.camera_a if camera == 'A' else project.camera_b
                window = camera_window(project, section, camera)
                if window and window[0] <= start and window[1] >= end:
                    source = (start-section.offset)/rate + (0 if camera == 'A' else project.camera_delta)
                    args += ['-ss', f'{max(0, source):.9f}', '-t', f'{duration+2/rate:.9f}',
                             '-threads', '2', '-i', media.path]
                else:
                    args += ['-f', 'lavfi', '-i', f'color=c=black:s=640x360:r={project.fps}:d={duration+1}']
            filters = []
            for camera in range(2):
                filters.append(f'[{camera}:v]scale=640:360:force_original_aspect_ratio=decrease,'
                               f'pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1,'
                               f'fps={project.fps},trim=end_frame={frames},setpts=PTS-STARTPTS[v{camera}]')
            filters.append('[v0][v1]hstack=inputs=2[v]')
            args += ['-filter_complex_threads', '2', '-filter_complex', ';'.join(filters),
                     '-map', '[v]', '-an', '-frames:v', str(frames), '-c:v', 'libx264',
                     '-preset', 'veryfast', '-crf', '25', '-pix_fmt', 'yuv420p', '-threads', '2',
                     '-video_track_timescale', str(project.rate.numerator), str(piece)]
            notify(index/max(len(spans), 1)*.94, f'Preparing preview · section {index+1}/{len(spans)}')
            run_ffmpeg(args, cancel,
                       lambda x: notify((index+x)/max(len(spans), 1)*.94,
                                        f'Preparing preview · section {index+1}/{len(spans)}'), duration)
        manifest = folder/'parts.txt'
        # Every path is a controlled local basename: no user text in concat syntax.
        manifest.write_text(''.join(f"file '{i:05d}.mp4'\n" for i in range(len(spans))), encoding='utf-8')
        tmp = target.with_suffix('.partial.mp4')
        notify(.95, 'Adding the continuous master audio')
        run_ffmpeg(['-f', 'concat', '-safe', '1', '-i', str(manifest), '-i', project.master.path,
                    '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-t', f'{project.master.duration:.9f}', '-movflags', '+faststart', str(tmp)],
                   cancel, duration=project.master.duration)
        tmp.replace(target)
        resolved = folder.resolve()
        if Path(cache).resolve() not in resolved.parents or not resolved.name.endswith('.work'):
            raise RuntimeError('Unexpected preview cache path; refused cleanup.')
        shutil.rmtree(resolved)
        notify(1., 'Preview ready')
        return target
    except BaseException:
        # Partial segment files must not become valid cached preview material.
        for piece in folder.glob('*.mp4'):
            piece.unlink(missing_ok=True)
        target.with_suffix('.partial.mp4').unlink(missing_ok=True)
        raise
