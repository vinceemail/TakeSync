from __future__ import annotations

from pathlib import Path
from threading import Event
import os

os.environ.setdefault('NUMBA_NUM_THREADS', str(min(8, os.cpu_count() or 2)))

import numpy as np
import librosa
import soundfile as sf
from scipy.ndimage import gaussian_filter1d
from scipy.signal import correlate, correlation_lags, find_peaks

from .models import Anchor, Project
from .media import probe, fingerprint, extract_audio, check_cancel
from .planner import regroup

SR = 22050
HOP = 256
DT = HOP / SR


def norm(x):
    return x / np.maximum(np.linalg.norm(x, axis=0, keepdims=True), 1e-8)


def features(wav: Path, cache: Path, cancel: Event):
    target = cache / (fingerprint(str(wav), 'cqt84-v2') + '.npz')
    if target.exists():
        with np.load(target) as z:
            return tuple(z[k].copy() for k in ['feature', 'onset', 'rms'])
    check_cancel(cancel)
    y, sr = sf.read(wav, dtype='float32')
    if len(y) < SR:
        raise ValueError('Recordings must contain at least one second of audio.')
    c = np.abs(librosa.cqt(y, sr=sr, hop_length=HOP, fmin=librosa.note_to_hz('C1'),
                          n_bins=84, tuning=0)).astype('float32')
    check_cancel(cancel)
    c = np.minimum(np.sqrt(c / np.maximum(c.mean(axis=1, keepdims=True), 1e-4)), 5)
    f = norm(np.concatenate([norm(c) * np.sqrt(.55),
                             norm(c.reshape(7, 12, -1).sum(axis=0)) * np.sqrt(.35),
                             norm(np.maximum(c - np.roll(c, 3, axis=1), 0)) * np.sqrt(.10)]))
    s = np.abs(librosa.stft(y, n_fft=1024, hop_length=HOP))
    onset = gaussian_filter1d(librosa.onset.onset_strength(
        S=librosa.amplitude_to_db(s), sr=sr, hop_length=HOP, center=True), .7)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=HOP)[0]
    tmp = target.with_name(target.stem + '.partial.npz')
    np.savez_compressed(tmp, feature=f, onset=onset, rms=rms)
    tmp.replace(target)
    return f, onset, rms


def camera_offset(onset_a, onset_b):
    """Normalized overlap correlation; positive delta means B's file time is later."""
    a = np.asarray(onset_a, dtype=float)
    b = np.asarray(onset_b, dtype=float)
    cc = correlate(b, a, mode='full', method='fft')
    lags = correlation_lags(len(b), len(a), mode='full')
    a0 = np.maximum(0, -lags)
    a1 = np.minimum(len(a), len(b) - lags)
    b0, b1 = a0 + lags, a1 + lags
    lengths = a1 - a0
    def sums(x, lo, hi, square=False):
        vals = x * x if square else x
        cumulative = np.r_[0, np.cumsum(vals)]
        return cumulative[hi] - cumulative[lo]
    sa, sb = sums(a, a0, a1), sums(b, b0, b1)
    ea, eb = sums(a, a0, a1, True), sums(b, b0, b1, True)
    covariance = cc - sa * sb / np.maximum(lengths, 1)
    denominator = np.sqrt(np.maximum(ea - sa**2 / np.maximum(lengths, 1), 1e-12)
                          * np.maximum(eb - sb**2 / np.maximum(lengths, 1), 1e-12))
    scores = covariance / denominator
    minimum = min(int(20 / DT), max(1, int(min(len(a), len(b)) * .35)))
    scores[lengths < minimum] = -np.inf
    best = int(np.argmax(scores))
    delta = float(lags[best])
    if 0 < best < len(scores) - 1:
        x, y, z = scores[best-1:best+2]
        den = x - 2*y + z
        if np.isfinite(den) and abs(den) > 1e-12:
            delta += float(np.clip(.5 * (x-z) / den, -.5, .5))
    return delta * DT, float(scores[best])


def active_span(rms):
    smoothed = gaussian_filter1d(rms, 3)
    # Quiet opening notes must not be mistaken for silence. The 10th percentile
    # can already contain music in tightly trimmed masters; use the quietest 1%.
    threshold = max(float(np.percentile(smoothed, 95)) * .02,
                    float(np.percentile(smoothed, 1)) * 4, 1e-6)
    active = np.flatnonzero(smoothed > threshold)
    if not len(active):
        raise ValueError('The master appears silent or too quiet to align.')
    return max(0., active[0] * DT - .15), min(len(rms) * DT, active[-1] * DT + .2)


def performance_regions(rms, master_duration, lower, upper):
    smooth = gaussian_filter1d(rms, 4)
    threshold = max(float(np.percentile(smooth, 95))*.08,
                    float(np.percentile(smooth, 10))*6, 1e-5)
    active = np.flatnonzero((smooth > threshold)
                           & (np.arange(len(smooth))*DT >= lower)
                           & (np.arange(len(smooth))*DT <= upper))
    if not len(active):
        return []
    gap = max(2.5, min(8., master_duration*.02))
    chunks = np.split(active, np.where(np.diff(active) > gap/DT)[0]+1)
    regions = []
    for chunk in chunks:
        length = (chunk[-1]-chunk[0])*DT
        if master_duration*.65 <= length <= master_duration*1.6:
            regions.append((max(lower, chunk[0]*DT-.25), min(upper, chunk[-1]*DT+.4)))
    return regions


def local_score(f, onset, m, mo, i, j, half=25):
    a, b = max(0, i-half), min(f.shape[1], i+half+1)
    shift = j-i
    if a+shift < 0 or b+shift > m.shape[1] or b <= a:
        return -1., -1.
    pitch = float(np.mean(np.sum(f[:, a:b] * m[:, a+shift:b+shift], axis=0)))
    x, y = onset[a:b], mo[a+shift:b+shift]
    attack = float(x @ y / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))
    return .65 * pitch + .35 * attack, attack


def align(camera_a: str, camera_b: str, master: str, cache: Path,
          tolerance=2, timeline_fps: str | None = None,
          camera_range: tuple[float, float] | None = None,
          progress=None, cancel: Event | None = None) -> Project:
    cancel = cancel or Event()
    notify = progress or (lambda value, message: None)
    notify(.01, 'Reading media metadata')
    a, b, master_media = probe(camera_a, True), probe(camera_b, True), probe(master)
    rate = a.rate if not timeline_fps else __import__('fractions').Fraction(timeline_fps)
    cache = Path(cache)
    check_cancel(cancel)
    sets = []
    for index, media in enumerate([a, b, master_media]):
        notify(.04 + index * .13, f'Extracting audio · {media.name}')
        wav = extract_audio(media, cache, cancel)
        notify(.08 + index * .13, f'Analysing musical features · {media.name}')
        sets.append(features(wav, cache, cancel))
    f, fo, fr = sets[0]
    bf, bo, br = sets[1]
    m, mo, mr = sets[2]
    notify(.46, 'Synchronizing the cameras')
    delta, camera_similarity = camera_offset(fo, bo)
    if a.rate == b.rate:
        # Identical camera rates can share one native-frame relationship.
        delta = round(delta * float(a.rate)) / float(a.rate)
    if camera_similarity < .15:
        raise ValueError('The camera recordings do not have a reliable shared-audio match. '
                         'Check that both videos contain the same performance with audible sound.')
    start, end = active_span(mr)
    if end - start < 2:
        raise ValueError('Not enough music was detected in the master.')
    astart, aend = 0., a.duration
    if camera_range:
        astart, aend = camera_range
        if not 0 <= astart < aend <= a.duration + .01:
            raise ValueError('The Camera A search range is outside the source recording.')
    notify(.51, 'Finding a complete performance and preserving its opening')
    regions = performance_regions(fr, end-start, astart, aend)
    if not regions:
        if camera_range:
            regions = [(astart, aend)]
        else:
            raise ValueError('Could not isolate a complete performance from the camera audio. '
                             'Set the optional Camera A In/Out range around the intended take and try again.')
    # Bound matrix memory for longer takes. Audio features retain fine timing.
    stride = max(2, int(np.ceil(max((end-start)/DT / 2200, (aend-astart)/DT / 4400))))
    first = int(start / DT)
    template = norm(m[:, first:int(end/DT):stride])
    best_match = None
    for region_start, region_end in regions:
        ai0, ai1 = int(region_start/DT), min(f.shape[1], int(region_end/DT))
        source = norm(f[:, ai0:ai1:stride])
        cost = np.maximum(1 - template.T @ source, 0).astype('float32')
        check_cancel(cancel)
        _, path = librosa.sequence.dtw(C=cost, subseq=False,
            step_sizes_sigma=np.array([[1, 1], [1, 2], [2, 1]]),
            weights_add=np.array([0, .01, .01]), weights_mul=np.array([1, 1.5, 1.5]))
        quality = float(np.mean(cost[path[:, 0], path[:, 1]]))
        if best_match is None or quality < best_match[0]:
            best_match = (quality, path[::-1].copy(), ai0)
        del cost
    _, path, ai0 = best_match
    mt = (path[:, 0] * stride + first) * DT
    at = (path[:, 1] * stride + ai0) * DT
    check_cancel(cancel)
    notify(.68, 'Refining note attacks and checking both microphones')
    master_peaks, props = find_peaks(mo, prominence=.55, distance=max(1, int(.17/DT)))
    camera_peaks, _ = find_peaks(fo, prominence=.4, distance=max(1, int(.10/DT)))
    viable = master_peaks[(master_peaks*DT >= start+.1) & (master_peaks*DT <= end-.25)]
    # At least one event per second, preferring stronger attacks in each window.
    chosen = []
    for t in np.arange(start, end, .85):
        options = viable[(viable*DT >= t) & (viable*DT < t+.85)]
        if len(options):
            chosen.append(int(max(options, key=lambda i: mo[i])))
    # Keep distinct first/last attacks as endpoints, even if quieter.
    if len(viable):
        chosen = sorted(set(chosen + [int(viable[0]), int(viable[-1])]))
    anchors = []
    for n, j0 in enumerate(chosen):
        check_cancel(cancel)
        guess = float(np.interp(j0*DT, mt, at))
        peaks = camera_peaks[np.abs(camera_peaks*DT-guess) < max(.27, DT*stride*2)]
        if not len(peaks):
            continue
        options = []
        for i in peaks:
            for j in range(max(0, j0-2), min(m.shape[1], j0+3)):
                sw, ow = local_score(f, fo, m, mo, int(i), j)
                bi = int(round((i*DT+delta)/DT))
                if not 0 <= bi < bf.shape[1]:
                    continue
                sb, ob = local_score(bf, bo, m, mo, bi, j)
                options.append(((sw+sb)/2, (ow+ob)/2, int(i), j, bi))
        if not options:
            continue
        score, attack, i, j, bi = max(options)
        if score < .70 or attack < .5:
            continue
        independent = [(local_score(bf, bo, m, mo, bi+k, j)[0], k)
                       for k in range(-9, 10) if 0 <= bi+k < bf.shape[1]]
        disagreement = abs(max(independent)[1]) * DT * 1000
        anchor = Anchor(int(round(j*DT*float(rate))), int(round(i*DT*float(rate))),
                        score, attack, disagreement, score < .82 or disagreement > 80)
        if anchors and (anchor.master_frame <= anchors[-1].master_frame
                        or anchor.source_frame <= anchors[-1].source_frame):
            continue
        anchors.append(anchor)
        if n % 10 == 0:
            notify(.68 + .23 * n / max(len(chosen), 1), f'Refining musical anchors · {len(anchors)} found')
    if len(anchors) < 3:
        raise ValueError('Too few reliable musical events matched. Try selecting the intended '
                         'take using the Camera A search range, or use clearer camera audio.')
    project = Project(a, b, master_media, str(rate), delta, camera_similarity, anchors, tolerance)
    if camera_similarity < .4:
        project.warnings.append('The camera-audio match is weak; review their synchronization.')
    if a.variable_rate or b.variable_rate:
        project.warnings.append('Variable-rate footage detected. Verify the XML import carefully; '
                                'constant-frame-rate source copies are recommended for final editing.')
    if len(anchors) * .85 < (end-start) * .55:
        project.warnings.append('Some passages have sparse reliable anchors. Review long or flagged sections.')
    notify(.95, 'Removing through edits and grouping within your tolerance')
    regroup(project, tolerance)
    from .models import camera_window
    for camera in ['A', 'B']:
        windows = [camera_window(project, s, camera) for s in project.sections]
        covered = sum(w[1]-w[0] for w in windows if w)
        if covered < project.frames:
            project.warnings.append(f'Camera {camera} has {(project.frames-covered)/float(rate):.2f}s '
                                    'without genuine source footage. These areas remain uncovered.')
    notify(1., 'Alignment ready')
    return project
