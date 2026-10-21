"""Create local handoff archives without including media, caches or environments."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'releases'


def main():
    OUT.mkdir(exist_ok=True)
    source=OUT/'TakeSync-0.1.0-source.zip'
    allowed=['takesync','tools','tests','.github']
    files=[ROOT/n for n in ['README.md','THIRD_PARTY.md','pyproject.toml','constraints.txt','TakeSync.spec','launch.py','.gitignore']]
    for name in allowed:
        files.extend(p for p in (ROOT/name).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.nbc','.nbi'])
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in files:archive.write(file,file.relative_to(ROOT))
    executable=ROOT/'dist/TakeSync/TakeSync.exe'
    outputs=[source]
    if executable.exists():
        target=OUT/'TakeSync-0.1.0-Windows-preview.zip'
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for file in executable.parent.rglob('*'):
                if file.is_file():archive.write(file,Path('TakeSync')/file.relative_to(executable.parent))
        outputs.append(target)
    report=[]
    for file in outputs:
        sha=hashlib.sha256()
        with file.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):sha.update(block)
        report.append({'file':file.name,'bytes':file.stat().st_size,'sha256':sha.hexdigest()})
    (OUT/'checksums.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
