"""Exercise a frozen app using synthetic media, without Python/FFmpeg on its PATH."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import wave
import xml.etree.ElementTree as ET

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output', type=Path, default=Path('bundle-smoke'))
    args = parser.parse_args()
    executable = args.executable.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rate = 22050
    rng = np.random.default_rng(71)
    notes = []
    for midi in rng.integers(48, 85, 48):
        t = np.arange(int(rate * .6)) / rate
        frequency = 440 * 2 ** ((int(midi) - 69) / 12)
        envelope = np.minimum(t / .015, 1) * np.minimum((.6 - t) / .09, 1)
        notes.append(envelope * (.4 * np.sin(2 * np.pi * frequency * t)
                                + .15 * np.sin(4 * np.pi * frequency * t)))
    music = np.concatenate(notes)
    master = output / 'master.wav'
    camera_audio = output / 'camera.wav'
    for path, samples in [(master, np.r_[np.zeros(rate), music, np.zeros(rate)]),
                          (camera_audio, np.r_[np.zeros(rate * 3), music, np.zeros(rate)])]:
        with wave.open(str(path), 'wb') as stream:
            stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            stream.writeframes((samples * 30000).astype('<i2').tobytes())
    video = output / 'camera.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i',
                    'testsrc2=size=320x180:rate=25', '-i', str(camera_audio),
                    '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(video)], check=True)
    env = os.environ.copy()
    env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
    env.pop('PYTHONPATH', None)
    env['QT_QPA_PLATFORM'] = 'offscreen'
    project = output / 'session.takesync'
    xml = output / 'timeline.fcpxml'
    subprocess.run([str(executable), '--cli', str(video), str(video), str(master),
                    '--output', str(project), '--xml', str(xml), '--preview',
                    '--in', '2', '--out', '33'], env=env, check=True, timeout=600)
    data = json.loads(project.read_text())
    assert len(data['anchors']) > 10, 'Analysis did not generate enough musical anchors'
    assert abs(data['camera_delta']) < .05, 'Identical cameras should have zero offset'
    assert ET.parse(xml).getroot().tag == 'fcpxml'
    preview = next((output / '.takesync-cache').glob('preview-*.mp4'))
    assert preview.stat().st_size > 10000
    screenshot = output / 'app.png'
    subprocess.run([str(executable), '--project', str(project), '--preview', str(preview),
                    '--screenshot', str(screenshot)], env=env, check=True, timeout=90)
    assert screenshot.exists() and screenshot.stat().st_size > 10000
    print('Frozen app analysis, bundled FFmpeg, XML export, preview render and UI startup passed.')


if __name__ == '__main__':
    main()
