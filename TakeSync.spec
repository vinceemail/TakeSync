# Run with the project's virtual-environment Python on the target OS.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

root = Path(SPECPATH)
vendor = root / 'vendor'
native = []
for name in ['ffmpeg', 'ffprobe']:
    extension = '.exe' if __import__('sys').platform == 'win32' else ''
    candidate = vendor / (name + extension)
    if not candidate.exists():
        raise RuntimeError('Run tools/build.py to stage FFmpeg before packaging.')
    native.append((str(candidate), 'vendor'))
if __import__('sys').platform == 'darwin':
    import subprocess
    ffmpeg_prefix = Path(subprocess.check_output(['brew', '--prefix', 'ffmpeg'], text=True).strip())
    # Preserve versioned library aliases: the helpers load names such as
    # libavformat.63.dylib, rather than only the fully versioned filename.
    media_libraries = {p for pattern in ['libav*.dylib', 'libsw*.dylib']
                       for p in (ffmpeg_prefix/'lib').glob(pattern)}
    native.extend((str(p), '.') for p in sorted(media_libraries))

lib_data, lib_bins, lib_hidden = collect_all('librosa')
a = Analysis([str(root / 'launch.py')], pathex=[str(root)],
    binaries=native+lib_bins,
    datas=collect_data_files('takesync')+lib_data+[(str(root/'THIRD_PARTY.md'), '.'),
          (str(root/'README.md'), '.'), (str(vendor/'FFmpeg-LICENSE.txt'), 'vendor'),
          (str(vendor/'FFmpeg-build.txt'), 'vendor'), (str(vendor/'licenses'), 'vendor/licenses')],
    hiddenimports=lib_hidden,
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtPdf', 'matplotlib', 'IPython'],
    module_collection_mode={'librosa':'pyz+py', 'numba':'pyz+py'},
    noarchive=False)
if __import__('sys').platform == 'darwin':
    # Qt's bundled FFmpeg has the same dylib names as Homebrew's build but a
    # different ABI. Playback uses AVFoundation; retain only Homebrew's codecs
    # so PyInstaller rewrites the CLI tools to their matching dependencies.
    a.binaries = [entry for entry in a.binaries if not (
        'PySide6' in entry[1] and (
            Path(entry[1]).name.startswith(('libav', 'libsw'))
            or 'ffmpegmediaplugin' in Path(entry[1]).name))]
if __import__('sys').platform == 'win32':
    # Python 3.10's older app-local MSVC runtime can shadow the newer runtime
    # required by Qt. Ship Qt's backward-compatible runtime at the bundle root.
    import PySide6
    qt_root = Path(PySide6.__file__).parent
    runtimes = list(qt_root.glob('VCRUNTIME140*.dll')) + list(qt_root.glob('MSVCP140*.dll'))
    names = {p.name.lower() for p in runtimes}
    a.binaries = [entry for entry in a.binaries if entry[0].lower() not in names]
    a.binaries += [(p.name, str(p), 'BINARY') for p in runtimes]
    # Qt uses Windows' ICU API. A generic ICU DLL from unrelated software on
    # the builder PATH is ABI-incompatible and must not shadow the OS library.
    a.binaries = [entry for entry in a.binaries
                  if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icuin.dll', 'icudt.dll'}]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TakeSync',
          debug=False, strip=False, upx=False, console=__import__('os').environ.get('TAKESYNC_CONSOLE')=='1', icon=str(root/'takesync/assets/icon.ico') if __import__('sys').platform=='win32' else None,
          codesign_identity=__import__('os').environ.get('TAKESYNC_CODESIGN_IDENTITY'))
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TakeSync')
if __import__('sys').platform == 'darwin':
    app = BUNDLE(collection, name='TakeSync.app', bundle_identifier='app.takesync.desktop',
                 info_plist={'CFBundleShortVersionString':'0.1.0', 'NSHighResolutionCapable':True,
                             'NSMicrophoneUsageDescription':'TakeSync reads selected media files; microphone capture is not used.'})
