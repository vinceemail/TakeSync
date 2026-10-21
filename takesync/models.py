from __future__ import annotations

from dataclasses import dataclass, asdict, field
from fractions import Fraction
from pathlib import Path
import json


@dataclass
class Media:
    path: str
    duration: float
    fps: str = "25/1"
    width: int = 0
    height: int = 0
    channels: int = 0
    sample_rate: int = 48000
    timecode: str = "00:00:00:00"
    variable_rate: bool = False

    @property
    def rate(self) -> Fraction:
        return Fraction(self.fps)

    @property
    def name(self) -> str:
        return Path(self.path).name


@dataclass
class Anchor:
    master_frame: int
    source_frame: int  # In timeline-rate units, relative to camera A file start.
    score: float
    onset_score: float = 0.0
    mic_disagreement_ms: float = 0.0
    review: bool = False

    @property
    def offset(self) -> int:
        return self.master_frame - self.source_frame


@dataclass
class Section:
    start: int
    end: int
    offset: int
    first_anchor: int
    last_anchor: int


@dataclass
class Project:
    camera_a: Media
    camera_b: Media
    master: Media
    fps: str
    camera_delta: float  # camera B source seconds = camera A source seconds + delta
    camera_similarity: float
    anchors: list[Anchor]
    tolerance: int = 2
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    version: int = 1

    @property
    def rate(self) -> Fraction:
        return Fraction(self.fps)

    @property
    def frames(self) -> int:
        from math import ceil
        return ceil(self.master.duration * float(self.rate) - 1e-9)

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + '.tmp')
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding='utf-8')
        tmp.replace(target)

    @classmethod
    def load(cls, path: str | Path) -> Project:
        raw = json.loads(Path(path).read_text(encoding='utf-8'))
        if raw.get('version') != 1:
            raise ValueError('This project version is not supported.')
        for key in ['camera_a', 'camera_b', 'master']:
            raw[key] = Media(**raw[key])
        raw['anchors'] = [Anchor(**x) for x in raw['anchors']]
        raw['sections'] = [Section(**x) for x in raw['sections']]
        return cls(**raw)


def camera_window(project: Project, section: Section, camera: str) -> tuple[int, int, float] | None:
    """Clip to genuine source handles. Missing footage is never invented."""
    from math import ceil, floor
    rate = float(project.rate)
    media = project.camera_a if camera == 'A' else project.camera_b
    delta = 0.0 if camera == 'A' else project.camera_delta
    start = max(section.start, ceil(section.offset - delta * rate - 1e-7))
    end = min(section.end, floor(section.offset + (media.duration - delta) * rate + 1e-7))
    if end <= start:
        return None
    return start, end, (start - section.offset) / rate + delta
