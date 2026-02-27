"""SQLite 数据库管理：模式定义、连接管理、初始化。"""

import sqlite3
from flask import g
from .config import DB_PATH, IMAGE_EXTENSIONS, IMAGE_EN_DIR, IMAGE_ZH_DIR, NOTE_DIR

# ── 数据库模式 ──
SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    folder TEXT NOT NULL DEFAULT '',
    pdf_path TEXT NOT NULL UNIQUE,
    pdf_zh_path TEXT,
    arxiv_id TEXT,
    alias TEXT,
    alias_full TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '默认笔记',
    file_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '默认插图',
    file_path TEXT NOT NULL UNIQUE,
    file_zh_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '新对话',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'model')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);
"""


def get_connection():
    """获取独立数据库连接（供脚本或流式生成器使用）。"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """获取当前 Flask 请求的数据库连接（单例模式）。"""
    if "db" not in g:
        g.db = get_connection()
    return g.db


def close_db(e=None):
    """请求结束时关闭数据库连接。"""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """初始化数据库模式（幂等操作）。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    try:
        conn.executescript(SCHEMA)
        # 迁移：为已有数据库添加缺失的列
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn):
    """检查并添加缺失的列（幂等）。"""
    cursor = conn.execute("PRAGMA table_info(papers)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "alias" not in existing_cols:
        conn.execute("ALTER TABLE papers ADD COLUMN alias TEXT")
    if "alias_full" not in existing_cols:
        conn.execute("ALTER TABLE papers ADD COLUMN alias_full TEXT")


def find_image_file(img_dir, stem_path):
    """尝试不同扩展名，返回第一个存在的图片相对路径（含扩展名），否则返回 None。"""
    for ext in IMAGE_EXTENSIONS:
        candidate = img_dir / (stem_path + ext)
        if candidate.exists():
            return stem_path + ext
    return None


def auto_discover_related(db, paper_id, stem):
    """为新注册的论文自动发现已有的笔记和插图文件。"""
    # 发现笔记
    note_path = stem + ".md"
    if (NOTE_DIR / note_path).exists():
        existing = db.execute(
            "SELECT id FROM notes WHERE file_path = ?", (note_path,)
        ).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO notes (paper_id, title, file_path) VALUES (?, ?, ?)",
                (paper_id, "默认笔记", note_path),
            )

    # 发现英文插图
    en_img = find_image_file(IMAGE_EN_DIR, stem)
    if en_img:
        existing = db.execute(
            "SELECT id FROM images WHERE file_path = ?", (en_img,)
        ).fetchone()
        if not existing:
            zh_img = find_image_file(IMAGE_ZH_DIR, stem)
            db.execute(
                "INSERT INTO images (paper_id, title, file_path, file_zh_path) VALUES (?, ?, ?, ?)",
                (paper_id, "默认插图", en_img, zh_img),
            )
