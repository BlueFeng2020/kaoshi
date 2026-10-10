"""Run this on Windows; PyInstaller cannot cross-compile a Windows EXE on Linux."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from config import APP_ROOT, read_exam_id


def command(exam_id,mode):
    separator = os.pathsep
    return [sys.executable,'-m','PyInstaller','--noconfirm','--clean',f'--{mode}',
        '--name',exam_id,'--distpath',str(APP_ROOT/'build'/'artifacts'),
        '--workpath',str(APP_ROOT/'build'/'work'),'--specpath',str(APP_ROOT/'build'),
        '--add-data',f'{APP_ROOT / "templates"}{separator}templates',
        '--add-data',f'{APP_ROOT / "static"}{separator}static',
        '--add-data',f'{APP_ROOT / "data"}{separator}data',
        '--add-data',f'{APP_ROOT / "exam_id.txt"}{separator}.',
        '--hidden-import','matplotlib.backends.backend_agg',
        '--exclude-module','tkinter','--exclude-module','PyQt5',
        '--exclude-module','PyQt6',str(APP_ROOT/'app.py')]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['onefile','onedir'],default='onefile')
    args=parser.parse_args()
    if sys.platform!='win32':
        raise SystemExit('Windows EXE must be built on Windows. Use build.bat on the exam PC.')
    exam_id=read_exam_id()
    if exam_id=='XXX':
        raise SystemExit('Fill in your real exam number in exam_id.txt before building.')
    subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=APP_ROOT,check=True)
    subprocess.run([sys.executable,str(APP_ROOT/'app.py'),'--prepare'],cwd=APP_ROOT,check=True)
    (APP_ROOT/'build').mkdir(exist_ok=True)
    subprocess.run(command(exam_id,args.mode),cwd=APP_ROOT,check=True)
    target=APP_ROOT/'delivery'/exam_id
    target.mkdir(parents=True,exist_ok=True)
    artifact=APP_ROOT/'build'/'artifacts'
    if args.mode=='onefile':shutil.copy2(artifact/f'{exam_id}.exe',target/f'{exam_id}.exe')
    else:shutil.copytree(artifact/exam_id,target,dirs_exist_ok=True)
    shutil.copytree(APP_ROOT/'data',target/'data',dirs_exist_ok=True)
    # Never copy development accounts or session keys into a delivery.
    for name in ['exam_id.txt','README_运行说明.txt','现场验收顺序.txt']:
        shutil.copy2(APP_ROOT/name,target/name)
    for p in (APP_ROOT/'output').glob(f'*_{exam_id}.*'):
        if p.is_file():shutil.copy2(p,target/p.name)
    destination=target/'output'/'charts';destination.mkdir(parents=True,exist_ok=True)
    for p in (APP_ROOT/'output'/'charts').glob(f'*_{exam_id}.png'):shutil.copy2(p,destination/p.name)
    # Execute the final EXE itself, so a missing bundled resource fails the build.
    print('Checking final executable with --prepare...', flush=True)
    subprocess.run([str(target/f'{exam_id}.exe'),'--prepare'],cwd=target,check=True)
    archive=target.parent/f'{exam_id}.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(target.rglob('*')):
            relative=p.relative_to(target)
            if p.is_file() and 'runtime' not in relative.parts and 'matplotlib-cache' not in relative.parts:
                z.write(p,Path(exam_id)/relative)
    print(f'\n最终交付 EXE：{target / (exam_id+".exe")}\n交付 ZIP：{archive}')
    print('请运行上面的 delivery 目录内程序。build/artifacts 只是构建中间目录。')
    print('Stop the Python server, then launch the EXE and perform the Windows acceptance checklist.')
    if hasattr(os, 'startfile'):
        try:
            os.startfile(str(target))
        except OSError as exc:
            print(f'无法自动打开交付目录，请按上述路径手动打开：{exc}')


if __name__=='__main__':main()
