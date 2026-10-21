from pathlib import Path
import argparse
import os
import shutil
import subprocess
import sys
import json
import importlib.metadata

ROOT = Path(__file__).resolve().parents[1]


def write_if_changed(path, text):
    if path.exists() and path.read_text(encoding='utf8') == text:
        return
    path.write_text(text, encoding='utf8')


def main():
    parser = argparse.ArgumentParser(description='Build the self-contained TakeSync app on this operating system')
    parser.add_argument('--clean', action='store_true', help='Ask PyInstaller to discard its build cache')
    args = parser.parse_args()
    vendor = ROOT/'vendor'; vendor.mkdir(exist_ok=True)
    for name in ['ffmpeg', 'ffprobe']:
        src = os.environ.get('TAKESYNC_'+name.upper()) or shutil.which(name)
        if not src:
            raise SystemExit(f'{name} is required on the build machine. Install FFmpeg before building.')
        if sys.platform == 'win32' and Path(src).stat().st_size < 200_000:
            # Chocolatey puts a launcher shim on PATH, which cannot be moved.
            chocolatey = Path(os.environ.get('ChocolateyInstall', 'C:/ProgramData/chocolatey'))
            candidates = list((chocolatey/'lib'/'ffmpeg'/'tools').rglob(name+'.exe'))
            candidates = [p for p in candidates if p.stat().st_size >= 200_000]
            if candidates:
                src = str(max(candidates, key=lambda p: p.stat().st_size))
        suffix = '.exe' if sys.platform=='win32' else ''
        destination = vendor/(name+suffix)
        if Path(src).resolve() != destination.resolve():
            shutil.copy2(src, destination)
    ffmpeg = str(vendor/('ffmpeg.exe' if sys.platform=='win32' else 'ffmpeg'))
    for flag, filename in [('-L','FFmpeg-LICENSE.txt'), ('-version','FFmpeg-build.txt')]:
        result = subprocess.run([ffmpeg,flag],capture_output=True,text=True,errors='replace',check=True)
        write_if_changed(vendor/filename,result.stdout+'\n'+result.stderr)
    notices = vendor/'licenses'; notices.mkdir(exist_ok=True)
    inventory=[]
    for dist in importlib.metadata.distributions():
        name=dist.metadata.get('Name','unknown')
        safe=''.join(x for x in name if x.isalnum() or x in '-_')
        inventory.append({'name':name,'version':dist.version,
                          'license':dist.metadata.get('License-Expression') or dist.metadata.get('License',''),
                          'homepage':dist.metadata.get('Home-page','')})
        for entry in dist.files or []:
            if not any(x in str(entry).lower() for x in ['license','licence','copying','copyright']):continue
            source=Path(dist.locate_file(entry))
            if not source.is_file() or source.suffix.lower() in ['.pyc','.dll','.pyd','.exe']:continue
            destination=notices/safe/Path(str(entry)).name
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(source,destination)
    write_if_changed(notices/'dependencies.json',json.dumps(inventory,indent=2))
    # Qt draws the icon consistently; no image-generation or proprietary artwork.
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPixmap,QPainter,QColor,QPen
    app = QApplication.instance() or QApplication([])
    pix = QPixmap(256,256); pix.fill(QColor('#152c22'))
    painter=QPainter(pix);painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#a0f0c2'),15))
    for x,height in [(48,55),(96,135),(144,90),(192,172)]:
        painter.drawLine(x,(256-height)//2,x,(256+height)//2)
    painter.end()
    if args.clean or not (ROOT/'takesync/assets/icon.ico').exists():
        pix.save(str(ROOT/'takesync/assets/icon.ico'))
    command=[sys.executable,'-m','PyInstaller','--noconfirm']
    if args.clean:command.append('--clean')
    command.append(str(ROOT/'TakeSync.spec'))
    build_env=os.environ.copy()
    if sys.platform=='win32':
        system=Path(os.environ.get('SystemRoot','C:/Windows'))
        build_env['PATH']=os.pathsep.join([str(Path(sys.executable).parent),str(Path(sys.base_prefix)),
                                         str(system/'System32'),str(system)])
    subprocess.run(command,cwd=ROOT,check=True,env=build_env)
    print('Build ready in', ROOT/'dist')


if __name__=='__main__':main()
