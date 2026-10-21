"""Apple FCPXML 1.10, with original media and exact rational time values."""
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

from .models import Project, camera_window
from .media import timecode_start
from .planner import validate_plan


def seconds(value) -> str:
    f = value if isinstance(value, Fraction) else Fraction(str(value)).limit_denominator(10**9)
    return f'{f.numerator}/{f.denominator}s'


def export(project: Project, target: str | Path) -> Path:
    validate_plan(project)
    target = Path(target)
    root = ET.Element('fcpxml', version='1.10')
    resources = ET.SubElement(root, 'resources')
    rate = project.rate
    ET.SubElement(resources, 'format', id='timelineFormat', name='TakeSync timeline',
                  frameDuration=seconds(1/rate), width=str(project.camera_a.width),
                  height=str(project.camera_a.height))
    for tag, media in [('A', project.camera_a), ('B', project.camera_b), ('M', project.master)]:
        fmt = 'sourceFormat' + tag
        if tag != 'M':
            ET.SubElement(resources, 'format', id=fmt, frameDuration=seconds(1/media.rate),
                          width=str(media.width), height=str(media.height))
        attrs = dict(id='source'+tag, name=media.name, start=seconds(timecode_start(media)),
                     duration=seconds(media.duration), hasAudio='1', audioSources='1',
                     audioChannels=str(media.channels), audioRate=str(media.sample_rate))
        if tag != 'M':
            attrs.update(hasVideo='1', format=fmt)
        asset = ET.SubElement(resources, 'asset', **attrs)
        ET.SubElement(asset, 'media-rep', kind='original-media', src=Path(media.path).resolve().as_uri())
    library = ET.SubElement(root, 'library')
    event = ET.SubElement(library, 'event', name='TakeSync')
    xml_project = ET.SubElement(event, 'project', name=target.stem)
    sequence = ET.SubElement(xml_project, 'sequence', format='timelineFormat',
                             duration=seconds(Fraction(project.frames, 1)/rate),
                             tcStart='0/1s', tcFormat='NDF', audioLayout='stereo', audioRate='48k')
    spine = ET.SubElement(sequence, 'spine')
    master_start = timecode_start(project.master)
    master = ET.SubElement(spine, 'asset-clip', ref='sourceM', name=project.master.name,
                           offset='0/1s', start=seconds(master_start),
                           duration=seconds(project.master.duration), audioRole='music')
    # The continuous master is the primary storyline; both camera lanes attach
    # to its source coordinate system. Camera audio never doubles the master.
    for camera, lane, media in [('A', '1', project.camera_a), ('B', '2', project.camera_b)]:
        for number, section in enumerate(project.sections, 1):
            window = camera_window(project, section, camera)
            if window is None:
                continue
            start, end, source_seconds = window
            source = timecode_start(media) + Fraction(str(source_seconds)).limit_denominator(10**8)
            clip = ET.SubElement(master, 'asset-clip', ref='source'+camera,
                name=f'Camera {camera} · {number:03d}', lane=lane,
                offset=seconds(master_start + Fraction(start, 1)/rate), start=seconds(source),
                duration=seconds(Fraction(end-start, 1)/rate),
                format='sourceFormat'+camera, srcEnable='video', videoRole='video.camera'+camera)
            for i, anchor in enumerate(project.anchors):
                if start <= anchor.master_frame < end:
                    note = (f'Master frame {anchor.master_frame}; section offset {section.offset:+d} frames; '
                            f'tolerance ±{project.tolerance} frames. Similarity {anchor.score:.3f}; '
                            f'microphone disagreement {anchor.mic_disagreement_ms:.1f}ms. '
                            'Feature similarity is not a probability of correct visual sync.')
                    ET.SubElement(clip, 'marker', start=seconds(source + Fraction(anchor.master_frame-start, 1)/rate),
                                  duration=seconds(1/rate), value=f'SYNC {i+1:03d}' + (' · REVIEW' if anchor.review else ''),
                                  note=note)
    # FCPXML orders connected clips before parent markers.
    for i, anchor in enumerate(project.anchors):
        ET.SubElement(master, 'marker', start=seconds(master_start + Fraction(anchor.master_frame, 1)/rate),
                      duration=seconds(1/rate), value=f'SYNC {i+1:03d}' + (' · REVIEW' if anchor.review else ''),
                      note=f'Original estimated offset {anchor.offset:+d} frames; sync tolerance ±{project.tolerance} frames.')
    ET.indent(root, space='  ')
    xml = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    xml = xml.replace(b'?>', b'?>\n<!DOCTYPE fcpxml>', 1)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix+'.tmp')
    tmp.write_bytes(xml)
    tmp.replace(target)
    return target
