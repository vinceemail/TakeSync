"""Frozen application entry point; keep internal imports discoverable by PyInstaller."""
import sys
import os
from pathlib import Path
import multiprocessing

multiprocessing.freeze_support()
if getattr(sys, 'frozen', False):
    if sys.platform == 'win32':
        cache = Path(os.environ.get('LOCALAPPDATA', Path.home()))/'TakeSync'/'numba'
    elif sys.platform == 'darwin':
        cache = Path.home()/'Library'/'Caches'/'TakeSync'/'numba'
    else:
        cache = Path.home()/'.cache'/'takesync'/'numba'
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('NUMBA_CACHE_DIR', str(cache))

if len(sys.argv) > 1 and sys.argv[1] == '--cli':
    sys.argv.pop(1)
    from takesync.cli import main
else:
    from takesync.ui import main

main()
