"""Read-only bundled resources and writable files deliberately use different roots."""
from pathlib import Path
import re
import sys

CUTOFF = '2026-09-22'
RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


def prepare_local_inputs(root=APP_ROOT, resources=RESOURCE_ROOT, frozen=None):
    """Seed missing inputs beside a frozen executable; never overwrite local edits."""
    if frozen is None:
        frozen = getattr(sys, 'frozen', False)
    if not frozen:
        return []
    root, resources = Path(root), Path(resources)
    required = ['exam_id.txt', 'data/设备台账数据.csv', 'data/设备维修记录.csv']
    missing = [name for name in required if not (root / name).exists()]
    for name in missing:
        if not (resources / name).is_file():
            raise FileNotFoundError(f'打包资源缺少 {name}，请下载最新版源码并重新运行 build.bat。')
    restored = []
    for name in missing:
        payload = (resources / name).read_bytes()
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open('xb') as stream:
                stream.write(payload)
        except FileExistsError:
            continue
        restored.append(name)
        print(f'已从随包资源创建本地文件：{target}', flush=True)
    return restored


def read_exam_id(root=APP_ROOT):
    path = Path(root) / 'exam_id.txt'
    if not path.exists():
        raise ValueError('请在程序旁创建 exam_id.txt 并填写抽签序号。')
    value = path.read_text(encoding='utf-8-sig').strip()
    if not re.fullmatch(r'[A-Za-z0-9\u4e00-\u9fff_-]{1,40}', value):
        raise ValueError('抽签序号仅可包含中文、英文字母、数字、下划线或短横线，长度 1—40。')
    if value.upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1,10)), *(f'LPT{i}' for i in range(1,10))}:
        raise ValueError('抽签序号不能使用 Windows 保留文件名。')
    return value
