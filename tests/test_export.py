from fractions import Fraction
from xml.etree import ElementTree as ET

from takesync.models import Media, Project, Anchor
from takesync.planner import regroup
from takesync.fcpxml import export, seconds
from takesync.media import timecode_start


def build(tmp_path):
    a = Media(str(tmp_path/'A & B.mov'), 60, '25', 3840, 2160, 2, timecode='23:24:07:17')
    b = Media(str(tmp_path/'Other camera.mov'), 60, '25', 1920, 1080, 2, timecode='10:27:38:22')
    master = Media(str(tmp_path/'Master.wav'), 10.01, channels=2)
    p = Project(a, b, master, '25', -2., .95,
                [Anchor(50, 250, .92), Anchor(125, 326, .89), Anchor(200, 403, .8, review=True)])
    regroup(p, 2)
    return p


def parse_time(text):
    return Fraction(text.removesuffix('s'))


def test_export_master_uninterrupted_and_camera_audio_disabled(tmp_path):
    p = build(tmp_path)
    target = export(p, tmp_path/'Timeline.fcpxml')
    root = ET.parse(target).getroot()
    spine = root.find('.//spine'); assert len(spine) == 1
    master = spine[0]
    assert master.attrib['ref'] == 'sourceM'
    assert parse_time(master.attrib['duration']) == Fraction('10.01')
    assert master.attrib['offset'] == '0/1s'
    videos = master.findall('asset-clip')
    assert all(c.attrib['srcEnable'] == 'video' for c in videos)
    assert {c.attrib['lane'] for c in videos} == {'1', '2'}
    assert len(master.findall('marker')) == len(p.anchors)
    assert 'A%20%26%20B.mov' in target.read_text()


def test_marker_coordinates_account_for_media_timecode_not_alignment(tmp_path):
    p = build(tmp_path); root = ET.parse(export(p, tmp_path/'test.fcpxml')).getroot()
    assets = {x.attrib['id']: x for x in root.findall('resources/asset')}
    master = root.find('.//spine/asset-clip')
    for clip in master.findall('asset-clip'):
        start = parse_time(clip.attrib['start']); position = parse_time(clip.attrib['offset'])
        asset_start = parse_time(assets[clip.attrib['ref']].attrib['start'])
        assert start >= asset_start
        for marker in clip.findall('marker'):
            actual_master = parse_time(marker.attrib['start'])-start+position
            index = int(marker.attrib['value'].split()[1])-1
            assert actual_master == Fraction(p.anchors[index].master_frame, 25)


def test_drop_frame_timecode_is_exact(tmp_path):
    m = Media(str(tmp_path/'a.mov'), 30, '30000/1001', timecode='01:00:00;00')
    assert timecode_start(m) == Fraction(107892, 1)/Fraction(30000, 1001)
    assert seconds(Fraction(1, 25)) == '1/25s'


def test_apple_dtd_if_available(tmp_path):
    from pathlib import Path
    import pytest
    from lxml import etree
    dtd_path = Path(__file__).parents[1]/'validation'/'FCPXML.dtd'
    if not dtd_path.exists(): pytest.skip('Apple DTD download is optional outside development')
    target = export(build(tmp_path), tmp_path/'test.fcpxml')
    dtd = etree.DTD(str(dtd_path))
    assert dtd.validate(etree.parse(str(target))), str(dtd.error_log)
