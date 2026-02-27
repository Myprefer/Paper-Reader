"""数据迁移脚本：将已有的基于文件路径的数据导入 SQLite 数据库。

使用方法:
    python migrate.py
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from backend.config import (
    IMAGE_EN_DIR,
    IMAGE_EXTENSIONS,
    IMAGE_ZH_DIR,
    NOTE_DIR,
    PDF_DIR,
    PDF_ZH_DIR,
)
from backend.db import get_connection, init_db


def find_image(img_dir, stem_path):
    """尝试不同扩展名，返回第一个存在的图片相对路径。"""
    for ext in IMAGE_EXTENSIONS:
        candidate = img_dir / (stem_path + ext)
        if candidate.exists():
            return stem_path + ext
    return None


def migrate():
    """扫描现有文件并导入数据库。"""
    print("=" * 50)
    print("  📦 数据迁移: 文件系统 → SQLite")
    print("=" * 50)

    init_db()
    conn = get_connection()

    try:
        pdf_files = sorted(PDF_DIR.rglob("*.pdf"))
        print(f"\n找到 {len(pdf_files)} 个 PDF 文件\n")

        stats = {"papers": 0, "notes": 0, "images": 0, "skipped": 0}

        for pdf_path in pdf_files:
            rel = pdf_path.relative_to(PDF_DIR).as_posix()
            stem = rel.rsplit(".", 1)[0]
            folder = pdf_path.relative_to(PDF_DIR).parent.as_posix()
            if folder == ".":
                folder = ""
            title = pdf_path.stem

            # 检查是否已存在
            existing = conn.execute(
                "SELECT id FROM papers WHERE pdf_path = ?", (rel,)
            ).fetchone()
            if existing:
                print(f"  ⏭️  跳过（已存在）: {rel}")
                stats["skipped"] += 1
                continue

            # 检查中文 PDF
            pdf_zh_path = rel if (PDF_ZH_DIR / rel).exists() else None

            # 插入论文记录
            cursor = conn.execute(
                "INSERT INTO papers (title, folder, pdf_path, pdf_zh_path) VALUES (?, ?, ?, ?)",
                (title, folder, rel, pdf_zh_path),
            )
            paper_id = cursor.lastrowid
            stats["papers"] += 1
            print(f"  ✅ 导入论文: {rel} (ID: {paper_id})")

            # 检查笔记
            note_path = stem + ".md"
            note_file = NOTE_DIR / note_path
            if note_file.exists():
                conn.execute(
                    "INSERT INTO notes (paper_id, title, file_path) VALUES (?, ?, ?)",
                    (paper_id, "默认笔记", note_path),
                )
                stats["notes"] += 1
                print(f"    📝 导入笔记: {note_path}")

            # 检查英文插图
            en_img = find_image(IMAGE_EN_DIR, stem)
            if en_img:
                zh_img = find_image(IMAGE_ZH_DIR, stem)
                conn.execute(
                    "INSERT INTO images (paper_id, title, file_path, file_zh_path) VALUES (?, ?, ?, ?)",
                    (paper_id, "默认插图", en_img, zh_img),
                )
                stats["images"] += 1
                zh_info = f" + 中文: {zh_img}" if zh_img else ""
                print(f"    🖼️ 导入插图: {en_img}{zh_info}")

        conn.commit()

        print(f"\n{'=' * 50}")
        print(f"  迁移完成！")
        print(f"  📄 论文: {stats['papers']} 新导入, {stats['skipped']} 已跳过")
        print(f"  📝 笔记: {stats['notes']}")
        print(f"  🖼️ 插图: {stats['images']}")
        print(f"{'=' * 50}")

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
