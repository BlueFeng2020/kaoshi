"""Execute the acceptance suite and preserve its real exit status in a numbered report."""
from pathlib import Path
import platform
import subprocess
import sys
from config import APP_ROOT, read_exam_id


def main():
    exam_id=read_exam_id()
    result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=APP_ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
    directory=APP_ROOT/'validation';directory.mkdir(exist_ok=True)
    report=f'抽签序号：{exam_id}\n系统：{platform.platform()}\nPython：{sys.version}\n退出码：{result.returncode}\n\n'+result.stdout
    (directory/f'unittest_{exam_id}.txt').write_text(report,encoding='utf-8-sig')
    print(report)
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
