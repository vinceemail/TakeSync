from threading import Event

import numpy as np
import pytest

from takesync.engine import camera_offset, DT, active_span
from takesync.media import Cancelled, run_ffmpeg


def test_camera_offset_handles_both_start_orders():
    rng = np.random.default_rng(123)
    events = np.zeros(4000)
    locations = rng.choice(np.arange(200, 3600), 80, replace=False)
    events[locations] = rng.uniform(.2, 1, len(locations))
    b = events[321:] * .8 + rng.normal(0, .005, len(events)-321)
    delta, score = camera_offset(events, b)
    assert abs(delta+321*DT) < DT*.1 and score > .95
    delta, score = camera_offset(b, events)
    assert abs(delta-321*DT) < DT*.1 and score > .95


def test_master_silence_and_decay_do_not_become_musical_anchors():
    rms = np.r_[np.zeros(200), np.ones(1000)*.2, np.zeros(300)]
    start, end = active_span(rms)
    assert 1 < start < 3 and 13 < end < 15


def test_quiet_opening_survives_louder_later_music():
    rms = np.r_[np.zeros(200), np.ones(1100)*.008, np.ones(9000)*.2, np.zeros(200)]
    start, end = active_span(rms)
    assert start < 3


def test_aborted_starts_do_not_merge_into_main_take():
    from takesync.engine import performance_regions
    rms = np.zeros(int(300/DT))
    for start, end in [(15, 22), (40, 68), (80, 90), (100, 285)]:
        rms[int(start/DT):int(end/DT)] = .2
    regions = performance_regions(rms, 190, 0, 300)
    assert len(regions) == 1
    assert 99 < regions[0][0] < 101 and 284 < regions[0][1] < 286


def test_cancelled_job_does_not_launch_a_process():
    event = Event(); event.set()
    with pytest.raises(Cancelled): run_ffmpeg(['-invalid'], cancel=event)
