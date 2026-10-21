# TakeSync · desktop preview build

A local desktop app for aligning two synchronized camera recordings to another performance of the same music, then exporting an editable FCPXML timeline. The app uses CPU audio analysis and keeps original recordings untouched.

## Using the app

1. Open **TakeSync**. Drop or choose Camera A, Camera B, and the master audio. Both videos need audible sound from the same performance.
2. Leave the timeline frame rate on **Match Camera A**, or choose your editing rate.
3. Click **Analyse & align**. Camera synchronization and full-take selection are automatic. If the recording has several complete takes or the app cannot isolate the right one, set the optional Camera A In/Out range in source-file seconds.
4. Adjust **Sync tolerance** in timeline frames. Zero retains every measured timing correction but removes true through edits. Higher values merge more sections. Every checked anchor in a merged section stays within the chosen tolerance of its event-specific estimate. This is not a guarantee about every intervening frame or every musician.
5. Click **Build preview**. The app creates a low-resolution side-by-side comparison with the proposed cuts baked in and one continuous master audio track. This preparation uses the CPU; once ready, playback and scrubbing run normally. Changing tolerance invalidates the old preview; rebuild to see the new edit. Camera A appears left, Camera B right.
6. Review flagged anchors by selecting a row or clicking the sync map. Listen and watch before committing to the edit.
7. Click **Export FCPXML**. The XML references the original files, includes two connected video lanes and numbered markers, and keeps the entire original master as the continuous primary storyline. It does not render or modify your source videos. Import the XML into your editor, then make your creative camera choices.

Save a `.takesync` project to reopen the anchors and settings without reanalysing. The media must remain at its recorded paths. Keep the app folder intact; the executable relies on its bundled libraries and media tools. No Python installation, network connection, account, or Resolve MCP is needed to use a packaged build.

## What this first version includes

* Windows/macOS desktop UI, with local drag-and-drop inputs.
* Shared-audio camera synchronization.
* Automatic full-performance region detection, anchored musical alignment, pitch and attack matching, and microphone cross-checks.
* Settable tolerance, minimum-section grouping, removal of through edits, and filling gaps by extending the next section backwards.
* Genuine source-handle checks: unavailable footage remains uncovered rather than being invented. The UI reports missing coverage.
* A/B comparison preview with playback, seeking and continuous master audio.
* FCPXML 1.10 export, exact rational frame timing, source timecode handling for interchange, and session save/open.
* Background processing, cancellation, reusable analysis caches, and safe source-file handling.

The engine never uses recording timecodes to infer musical synchronization. It includes source timecode origins only when describing media in the exported XML. All video plays at normal speed. A strong match score is a feature-similarity measure, not a probability of correct visible playing.

## Current limits

This is a **0.1 preview build**, not a finished team release. macOS builds require a macOS build machine or CI runner and real Mac import/playback testing. The Windows package is built and checked separately.

The first build focuses on the main performance. Searching earlier false starts for optional alternate layers, manually moving individual anchors, audio-only audition controls, automatic media relinking, signed installers and automatic updating are not implemented yet. The preview must be prepared before playback; it is not instantaneous live editing of two 4K sources. The editable original-media export is the final output.

Other takes must contain the same musical sequence in the same order. Major omissions, repeats, very different orchestration, long silent passages, or a master assembled from substantially different material may require a narrower search range or further work. Variable-frame-rate sources are flagged; constant-frame-rate sources are preferable for reliable interchange. Differences in individual musicians' relative timing cannot all be corrected by moving both cameras together.

## Development

Use Python 3.10–3.13. Python 3.11 is the release-build target. Install FFmpeg and ffprobe, with libx264 support for the comparison preview.

```sh
python -m venv .venv
# macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m takesync
python -m pytest -q
```

Build a self-contained application **on each target operating system**:

```sh
python tools/build.py
```

Output is `dist/TakeSync/TakeSync.exe` on Windows and `dist/TakeSync.app` on macOS. Build tools stage FFmpeg/ffprobe in `vendor/`; end users do not install those tools. On macOS, PyInstaller collects the native dependencies of the staged FFmpeg executables; validate the result on a clean Mac. The included workflow builds on Windows and macOS runners but does not publish or notarize anything. Set `TAKESYNC_CODESIGN_IDENTITY` on a configured Mac builder if you have an appropriate signing identity. A public Mac release should also be notarized.

The optional CLI uses the same engine:

```sh
python -m takesync.cli camera-a.mov camera-b.mov master.wav --output session.takesync --xml timeline.fcpxml
```

Do not add source media, analysis caches, or the virtual environment to a source repository. Dependencies and native tools have third-party licences; see `THIRD_PARTY.md` and the notices included in the build.
