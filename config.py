"""Read-only bundled resources and writable files deliberately use different roots."""
from pathlib import Path
import re
import sys

CUTOFF = '2026-09-22'
RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


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
