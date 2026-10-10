"""SQLite persistence; defaults only initialized when the user table is empty."""
import re
import sqlite3
from contextlib import contextmanager
from werkzeug.security import generate_password_hash, check_password_hash


@contextmanager
def connection(path):
    db=sqlite3.connect(path,timeout=10)
    db.row_factory=sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


def initialize(path):
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN (\'admin\',\'user\')))')
        if db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0:
            db.executemany('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',[
                ('admin',generate_password_hash('Admin@123456'),'admin'),
                ('user',generate_password_hash('User@123456'),'user')])


def find_user(path, username=None, user_id=None):
    with connection(path) as db:
        row=db.execute('SELECT * FROM users WHERE '+('username=?' if username is not None else 'id=?'),(username if username is not None else user_id,)).fetchone()
        return dict(row) if row else None


def authenticate(path,username,password):
    user=find_user(path,username=username)
    return user if user and check_password_hash(user['password_hash'],password) else None


def add_user(path,username,password,role):
    username=username.strip()
    if not re.fullmatch(r'[A-Za-z0-9_\u4e00-\u9fff-]{2,32}',username):
        raise ValueError('用户名须为 2—32 位中文、字母、数字、下划线或短横线。')
    if not password.strip() or len(password)<6 or len(password)>128:
        raise ValueError('密码须为 6—128 位，不能全为空格。')
    if role not in ('admin','user'):
        raise ValueError('无效角色。')
    try:
        with connection(path) as db:
            db.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',(username,generate_password_hash(password),role))
    except sqlite3.IntegrityError as exc:
        raise ValueError('用户名已存在。') from exc


def list_users(path):
    with connection(path) as db:
        return [dict(r) for r in db.execute('SELECT id,username,role FROM users ORDER BY id')]
