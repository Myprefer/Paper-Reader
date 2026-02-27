"""
导入已有数据到 PaperReader 数据目录。

将指定源目录中的 PDF、笔记、图片等文件复制到 PaperReader 数据目录，
然后运行数据库迁移注册所有文件。

用法:
    python import_data.py                           # 从项目目录导入
    python import_data.py --source D:\\path\\to\\data  # 从指定目录导入

源目录应包含以下子目录（可部分缺失）：
    pdfs/       英文 PDF
    pdfs_zh/    中文 PDF
    notes/      Markdown 笔记
    images/     英文插图
    images_zh/  中文插图
"""

import argparse
import shutil
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from backend.config import DATA_DIR, PDF_DIR, PDF_ZH_DIR, NOTE_DIR, IMAGE_EN_DIR, IMAGE_ZH_DIR
from backend.db import get_connection, init_db
from backend.config import IMAGE_EXTENSIONS

# 目录映射: (子目录名, 目标路径)
DIR_MAP = [
    ("pdfs",      PDF_DIR),
    ("pdfs_zh",   PDF_ZH_DIR),
    ("notes",     NOTE_DIR),
    ("images",    IMAGE_EN_DIR),
    ("images_zh", IMAGE_ZH_DIR),
]


def copy_tree(src: Path, dst: Path) -> int:
    """递归复制目录，跳过已存在的文件。返回复制的文件数量。"""
    count = 0
    if not src.exists():
        return 0

    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        count += 1
    return count


def find_image(img_dir: Path, stem_path: str) -> str | None:
    """尝试不同扩展名，返回第一个存在的图片相对路径。"""
    for ext in IMAGE_EXTENSIONS:
        candidate = img_dir / (stem_path + ext)
        if candidate.exists():
            return stem_path + ext
    return None


def register_to_db():
    """扫描数据目录中的 PDF 并注册到数据库（跳过已存在的）。"""
    init_db()
    conn = get_connection()
    stats = {"papers": 0, "notes": 0, "images": 0, "skipped": 0}

    try:
        pdf_files = sorted(PDF_DIR.rglob("*.pdf"))

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

            # 检查笔记
            note_path = stem + ".md"
            if (NOTE_DIR / note_path).exists():
                conn.execute(
                    "INSERT INTO notes (paper_id, title, file_path) VALUES (?, ?, ?)",
                    (paper_id, title, note_path),
                )
                stats["notes"] += 1

            # 检查英文插图
            en_img = find_image(IMAGE_EN_DIR, stem)
            if en_img:
                zh_img = find_image(IMAGE_ZH_DIR, stem)
                conn.execute(
                    "INSERT INTO images (paper_id, title, file_path, file_zh_path) VALUES (?, ?, ?, ?)",
                    (paper_id, title, en_img, zh_img),
                )
                stats["images"] += 1

        conn.commit()
        return stats
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Import existing data into PaperReader")
    parser.add_argument(
        "--source", "-s",
        type=str,
        default=str(Path(__file__).parent),
        help="Source directory containing pdfs/, notes/, images/ etc.",
    )
    args = parser.parse_args()
    source = Path(args.source)

    print("=" * 55)
    print("  PaperReader - Import Data")
    print("=" * 55)
    print(f"  Source:      {source.resolve()}")
    print(f"  Target:      {DATA_DIR.resolve()}")
    print()

    if not source.exists():
        print(f"  [ERROR] Source directory not found: {source}")
        sys.exit(1)

    # Step 1: Copy files
    print("  [1/2] Copying files...")
    total_copied = 0
    for subdir, target in DIR_MAP:
        src = source / subdir
        if not src.exists():
            print(f"         {subdir:12s}  (not found, skipped)")
            continue
        n = copy_tree(src, target)
        total_copied += n
        print(f"         {subdir:12s}  {n} files copied")

    print(f"         Total: {total_copied} files copied")
    print()

    # Step 2: Register in database
    print("  [2/2] Registering in database...")
    stats = register_to_db()
    print(f"         Papers: {stats['papers']} new, {stats['skipped']} already existed")
    print(f"         Notes:  {stats['notes']}")
    print(f"         Images: {stats['images']}")
    print()

    print("=" * 55)
    print("  Import complete!")
    print(f"  Data directory: {DATA_DIR.resolve()}")
    print("=" * 55)


if __name__ == "__main__":
    main()
