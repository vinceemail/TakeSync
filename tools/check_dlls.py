from pathlib import Path
import pefile

root=Path(__file__).resolve().parents[1]/'dist/TakeSync/_internal'
all_files={}
for p in root.rglob('*'):
    if p.is_file() and p.suffix.lower() in ['.dll','.pyd']:
        all_files.setdefault(p.name.lower(),[]).append(p)

def choose(name,parent):
    paths=[root/name,parent/name,root/'PySide6'/name,root/'shiboken6'/name,
           Path('C:/Windows/System32')/name]+all_files.get(name.lower(),[])
    return next((p for p in paths if p.exists()),None)

seen=set();missing=[]
def walk(file):
    if file in seen:return
    seen.add(file)
    try:
        pe=pefile.PE(str(file),fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        for imp in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[]):
            name=imp.dll.decode()
            if name.lower().startswith(('api-ms-','ext-ms-')):continue
            lib=choose(name,file.parent)
            if lib is None:continue
            dep=pefile.PE(str(lib),fast_load=True)
            dep.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
            exports={x.name for x in getattr(getattr(dep,'DIRECTORY_ENTRY_EXPORT',None),'symbols',[])}
            absent=[s.name.decode(errors='replace') for s in imp.imports if s.name and s.name not in exports]
            if absent:missing.append((str(file.relative_to(root)),name,str(lib),absent[:10]))
            dep.close()
            if root in lib.parents:walk(lib)
        pe.close()
    except pefile.PEFormatError:pass

walk(root/'PySide6/QtCore.pyd')
for m in missing:print(m)
print('DLLs checked',len(seen))
