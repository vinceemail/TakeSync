import json
from pathlib import Path
import subprocess
from threading import Event

import numpy as np
import pytest

from takesync.media import binary, run_ffmpeg, probe, process_options
from takesync.models import Project, Anchor
from takesync.planner import regroup
from takesync.preview import render


def test_preview_contains_both_cameras_and_only_the_master_audio(tmp_path):
    try:
        binary('ffmpeg'); binary('ffprobe')
    except RuntimeError:
        pytest.skip('FFmpeg development tools are not installed')
    paths=[]
    for colour in ['red', 'blue']:
        target=tmp_path/(colour+'.mp4')
        run_ffmpeg(['-f','lavfi','-i',f'color=c={colour}:s=160x90:r=10:d=3',
                    '-f','lavfi','-i','sine=frequency=400:sample_rate=22050:duration=3',
                    '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac',str(target)], duration=3)
        paths.append(target)
    master=tmp_path/'master.wav'
    run_ffmpeg(['-f','lavfi','-i','sine=frequency=1000:sample_rate=22050:duration=3',str(master)], duration=3)
    p=Project(probe(str(paths[0]),True),probe(str(paths[1]),True),probe(str(master)),
              '10',0,1,[Anchor(5,5,.95),Anchor(15,14,.95)])
    regroup(p,0)
    cache=tmp_path/'cache';cache.mkdir()
    result=render(p,cache,Event())
    meta=json.loads(subprocess.check_output([binary('ffprobe'),'-v','error','-show_streams','-of','json',str(result)],**process_options()))
    video=next(s for s in meta['streams'] if s['codec_type']=='video')
    assert int(video['nb_frames'])==30 and abs(float(video['duration'])-3)<.01
    raw=subprocess.check_output([binary('ffmpeg'),'-v','error','-ss','1','-i',str(result),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],**process_options())
    frame=np.frombuffer(raw,dtype=np.uint8).reshape(360,1280,3)
    left=frame[180,300].astype(float);right=frame[180,1000].astype(float)
    assert left[0]>200 and left[2]<30
    assert right[2]>200 and right[0]<30
    audio=subprocess.check_output([binary('ffmpeg'),'-v','error','-i',str(result),'-vn','-ac','1','-ar','22050','-f','f32le','-'],**process_options())
    samples=np.frombuffer(audio,dtype='<f4')[10000:40000]
    frequencies=np.fft.rfftfreq(len(samples),1/22050)
    peak=frequencies[np.argmax(np.abs(np.fft.rfft(samples))) ]
    assert abs(peak-1000)<2
    assert render(p,cache)==result
