"""Deliver only project inputs, code and reproducible outputs; exclude accounts and caches."""
from pathlib import Path
import zipfile
from config import APP_ROOT, read_exam_id


def package(destination=None):
    exam_id=read_exam_id()
    target=Path(destination) if destination else APP_ROOT/'delivery'/f'{exam_id}_源码.zip'
    target.parent.mkdir(parents=True,exist_ok=True)
    directories={'data','references','templates','static','tests','validation'}
    selected=[]
    candidates=list(APP_ROOT.iterdir())
    for directory in directories | {'output'}:
        if (APP_ROOT/directory).exists():candidates.extend((APP_ROOT/directory).rglob('*'))
    for p in sorted(candidates):
            rel=p.relative_to(APP_ROOT)
            if not p.is_file() or '__pycache__' in rel.parts:continue
            if p.name.startswith('文件清单_'):continue
            included=(len(rel.parts)==1 and p.suffix in {'.py','.txt','.bat','.md'}) or rel.parts[0] in directories
            if rel.parts[0]=='output' and 'matplotlib-cache' not in rel.parts and p.name.endswith((f'_{exam_id}.csv',f'_{exam_id}.json',f'_{exam_id}.txt',f'_{exam_id}.png')):
                included=True
            if included:selected.append(p)
    manifest=APP_ROOT/f'文件清单_{exam_id}.txt'
    manifest.write_text('抽签序号：'+exam_id+'\n源码交付文件清单（不含本清单自身；不含账号、密钥、缓存、虚拟环境）\n\n'+'\n'.join(f'{p.relative_to(APP_ROOT).as_posix()}  ({p.stat().st_size} bytes)' for p in selected)+'\n',encoding='utf-8-sig')
    selected.append(manifest)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in selected:z.write(p,Path(exam_id)/p.relative_to(APP_ROOT))
    return target


if __name__=='__main__':print(package())
