from fractions import Fraction
import random

import pytest

from takesync.models import Media, Anchor, Project, camera_window
from takesync.planner import regroup, validate_plan


def project(offsets, fps='25', duration=30):
    a = Media('/tmp/a.mov', duration+30, fps, 1920, 1080, 2)
    b = Media('/tmp/b.mov', duration+30, fps, 1920, 1080, 2)
    m = Media('/tmp/master.wav', duration, fps, channels=2)
    anchors = [Anchor((i+1)*25, (i+1)*25-off, .9) for i, off in enumerate(offsets)]
    return Project(a, b, m, fps, -1., .95, anchors)


def test_zero_tolerance_removes_only_true_through_edits():
    p = project([-100, -100, -99, -99, -95])
    assert len(regroup(p, 0)) == 3
    assert [s.offset for s in p.sections] == [-100, -99, -95]
    validate_plan(p)


def test_two_frame_tolerance_checks_every_anchor_and_does_not_accumulate():
    p = project(list(range(-100, -80)))
    regroup(p, 2)
    assert len(p.sections) >= 4
    for section in p.sections:
        assert all(abs(a.offset-section.offset) <= 2
                   for a in p.anchors[section.first_anchor:section.last_anchor+1])


def test_large_gap_extends_next_backwards_without_moving_its_anchor():
    p = project([-100, -90])
    regroup(p, 0)
    assert p.sections[1].start == 50-10
    assert p.sections[0].end == p.sections[1].start
    assert p.anchors[1].master_frame - p.sections[1].offset == p.anchors[1].source_frame


def test_all_same_offset_is_one_section():
    p = project([-100]*15)
    assert len(regroup(p, 2)) == 1
    assert p.sections[0].start == 0 and p.sections[0].end == 750


def test_handles_are_clipped_without_inventing_footage():
    p = project([10, 10]); regroup(p, 0)
    window = camera_window(p, p.sections[0], 'A')
    assert window[0] == 10 and window[2] == 0
    assert camera_window(p, p.sections[0], 'B')[0] == 35


def test_master_end_never_loses_audio_to_frame_rounding():
    p = project([-100], fps='30000/1001', duration=3.337)
    assert p.frames / float(p.rate) >= p.master.duration
    assert (p.frames-1) / float(p.rate) < p.master.duration


def test_empty_or_invalid_anchor_order_is_rejected():
    p = project([])
    with pytest.raises(ValueError): regroup(p, 2)
    p = project([-100, -100]); p.anchors[1].source_frame = p.anchors[0].source_frame
    with pytest.raises(ValueError): regroup(p, 2)


def test_tolerance_does_not_increase_cut_count_and_preserves_coverage():
    rng = random.Random(4)
    for _ in range(20):
        offsets = [-100]
        for i in range(49): offsets.append(offsets[-1]+rng.choice([-2, -1, 0, 0, 1, 3]))
        p = project(offsets, duration=55)
        counts = []
        for tolerance in range(6):
            counts.append(len(regroup(p, tolerance))); validate_plan(p)
        assert counts == sorted(counts, reverse=True)


def test_session_roundtrip(tmp_path):
    p = project([-100, -99]); regroup(p, 2)
    path = tmp_path/'session.takesync'; p.save(path)
    loaded = Project.load(path)
    assert loaded == p
