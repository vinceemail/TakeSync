# Third-party software

TakeSync uses open-source components. Their copyright and licence notices must travel with distributions.

* Python: Python Software Foundation licence, https://docs.python.org/3/license.html
* NumPy and SciPy: BSD licences, https://numpy.org/doc/stable/license.html and https://scipy.org/about/
* librosa: ISC licence, https://github.com/librosa/librosa/blob/main/LICENSE.md
* Numba and llvmlite: BSD-family licences, https://github.com/numba/numba and https://github.com/numba/llvmlite
* SoundFile and libsndfile: BSD and LGPL respectively, https://github.com/bastibe/python-soundfile and https://libsndfile.github.io/libsndfile/
* PySide6 and Qt: applicable LGPL/GPL/community terms, https://doc.qt.io/qtforpython-6/licenses.html
* Inter: SIL Open Font License 1.1. The full notice is in takesync/assets/Inter-LICENSE.txt.
* FFmpeg/ffprobe: the exact staged build's licence text and version/configuration are in vendor/FFmpeg-LICENSE.txt and vendor/FFmpeg-build.txt. Build options affect licensing. FFmpeg runs as a separate executable. The preview renderer needs an encoder with libx264 support. General licence and source information: https://ffmpeg.org/legal.html and https://ffmpeg.org/download.html

The Windows development build uses the FFmpeg build already installed on the development computer (Gyan FFmpeg Essentials). Matching release/source information is available at https://www.gyan.dev/ffmpeg/builds/ and https://ffmpeg.org/download.html. Before public redistribution, retain the exact build provenance and satisfy the source/notice requirements of the shipped binaries. This development build is not a licence-compliance audit.

PyInstaller includes its bootloader exception: https://pyinstaller.org/en/stable/license.html

Dependency wheels also retain their own licence files in the build environment. A release should include a complete dependency licence inventory in addition to this overview.
