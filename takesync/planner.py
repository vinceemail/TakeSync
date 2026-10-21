"""Minimum-cut plans with bounded error at EVERY observed musical anchor."""
from .models import Project, Section


def regroup(project: Project, tolerance: int) -> list[Section]:
    if not 0 <= tolerance <= 30:
        raise ValueError('Sync tolerance must be between 0 and 30 frames.')
    anchors = project.anchors
    if not anchors:
        raise ValueError('No reliable musical anchors were found.')
    if any(a.master_frame >= b.master_frame or a.source_frame >= b.source_frame
           for a, b in zip(anchors, anchors[1:])):
        raise ValueError('Anchor order must increase in both recordings.')
    n = len(anchors)
    dp = [None] * (n + 1)
    dp[0] = (0, 0., [])
    for end in range(1, n + 1):
        best = None
        low, high, total, squared = -10**12, 10**12, 0., 0.
        for start in range(end - 1, -1, -1):
            off = anchors[start].offset
            low, high = max(low, off - tolerance), min(high, off + tolerance)
            if low > high:
                break
            total += off
            squared += off * off
            count = end - start
            representative = int(max(low, min(high, round(total / count))))
            error = squared - 2 * representative * total + count * representative**2
            prev = dp[start]
            option = (prev[0] + 1, prev[1] + error,
                      prev[2] + [(start, end - 1, representative)])
            if best is None or option[:2] < best[:2]:
                best = option
        dp[end] = best
    groups = dp[n][2]
    # With increasing offsets, roll the NEXT section backwards over the gap.
    # Decreasing offsets trim the previous overlap. The master never ripples.
    starts = [0]
    for previous, current in zip(groups, groups[1:]):
        boundary = anchors[current[0]].master_frame - max(0, current[2] - previous[2])
        boundary = max(starts[-1] + 1, min(boundary, anchors[current[0]].master_frame))
        starts.append(boundary)
    sections = []
    for i, (first, last, offset) in enumerate(groups):
        end = starts[i + 1] if i + 1 < len(starts) else project.frames
        if end > starts[i]:
            sections.append(Section(starts[i], end, offset, first, last))
    project.tolerance = tolerance
    project.sections = sections
    validate_plan(project)
    return sections


def validate_plan(project: Project) -> None:
    sections = project.sections
    if not sections or sections[0].start != 0 or sections[-1].end != project.frames:
        raise ValueError('The edit must span the whole master.')
    for left, right in zip(sections, sections[1:]):
        if left.end != right.start or left.offset == right.offset:
            raise ValueError('Unexpected gap, overlap or through edit in plan.')
    for section in sections:
        if section.end <= section.start:
            raise ValueError('Empty section.')
        for anchor in project.anchors[section.first_anchor:section.last_anchor + 1]:
            if abs(anchor.offset - section.offset) > project.tolerance:
                raise ValueError('An anchor exceeds the selected sync tolerance.')
