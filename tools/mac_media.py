"""Install an isolated, relocatable FFmpeg dependency tree in a Mac app."""
from pathlib import Path
import re
import shutil
import subprocess


def run(*args):
    return subprocess.check_output(list(map(str, args)), text=True)


def install(app: Path, sources: list[Path], identity: str = '-'):
    destination = app/'Contents'/'Frameworks'/'TakeSyncMedia'
    destination.mkdir(parents=True, exist_ok=True)
    records = {}
    names = {}

    def rpaths(source):
        listing = run('otool', '-l', source)
        return re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', listing)

    def expand(value, source, executable):
        return Path(value.replace('@loader_path', str(source.parent))
                         .replace('@executable_path', str(executable.parent)))

    def resolve(dependency, source, executable, inherited):
        if dependency.startswith(('/System/Library/', '/usr/lib/')):
            return None
        if dependency.startswith('@rpath/'):
            suffix = dependency[len('@rpath/'):]
            candidates = [expand(p, source, executable)/suffix
                          for p in rpaths(source)]
            candidates += [p/suffix for p in inherited]
        else:
            candidates = [expand(dependency, source, executable)]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise RuntimeError(f'Cannot resolve {dependency} required by {source}; tried {candidates}')

    def collect(source, executable, inherited=()):
        source = source.resolve()
        if source in records:
            return
        if source.name in names and names[source.name] != source:
            raise RuntimeError(f'Conflicting native media dependency: {source.name}')
        names[source.name] = source
        records[source] = []
        local_paths = tuple(expand(p, source, executable) for p in rpaths(source)) + tuple(inherited)
        for line in run('otool', '-L', source).splitlines()[1:]:
            if not line.startswith('\t'):
                continue
            dependency = line.strip().split(' (compatibility version', 1)[0]
            resolved = resolve(dependency, source, executable, local_paths)
            if resolved is None or resolved == source:
                continue
            records[source].append((dependency, resolved))
            collect(resolved, executable, local_paths)

    for source in sources:
        collect(source, source.resolve())
    for source in records:
        target = destination/source.name
        shutil.copy2(source, target)
        target.chmod(target.stat().st_mode | 0o200)
    for source, dependencies in records.items():
        target = destination/source.name
        command = ['install_name_tool']
        if source.suffix == '.dylib':
            command += ['-id', '@rpath/'+source.name]
        for old, dependency in dependencies:
            command += ['-change', old, '@loader_path/'+dependency.name]
        if len(command) > 1:
            subprocess.run(command+[str(target)], check=True)
        subprocess.run(['codesign', '--force', '--sign', identity, str(target)], check=True)
    subprocess.run(['codesign', '--force', '--deep', '--sign', identity, str(app)], check=True)
    broken = [str(p.relative_to(app)) for p in app.rglob('*') if p.is_symlink() and not p.exists()]
    if broken:
        raise RuntimeError(f'Broken application symlinks: {broken}')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', '--verbose=4', str(app)], check=True)
    print(f'Installed and signed {len(records)} isolated native media files in {destination}')
