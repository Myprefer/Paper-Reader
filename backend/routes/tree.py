"""目录树 API：构建论文目录树，自动同步数据库。"""

from flask import Blueprint, jsonify

from ..config import PDF_DIR, PDF_ZH_DIR
from ..db import get_db, auto_discover_related

bp = Blueprint("tree", __name__)


@bp.route("/api/tree")
def api_tree():
    """构建并返回论文目录树，自动注册未知 PDF 到数据库。"""
    db = get_db()
    PDF_DIR.mkdir(exist_ok=True)

    # 预加载所有论文记录，按 pdf_path 索引
    rows = db.execute("SELECT * FROM papers").fetchall()
    papers_by_path = {r["pdf_path"]: dict(r) for r in rows}

    # 预加载笔记、图片计数和别名
    count_rows = db.execute(
        """
        SELECT p.id, p.alias, p.alias_full,
               (SELECT COUNT(*) FROM notes WHERE paper_id = p.id) AS note_count,
               (SELECT COUNT(*) FROM images WHERE paper_id = p.id) AS image_count,
               (SELECT COUNT(*) FROM images
                WHERE paper_id = p.id AND file_zh_path IS NOT NULL) AS image_zh_count
        FROM papers p
        """
    ).fetchall()
    counts_by_id = {
        r["id"]: {
            "note_count": r["note_count"],
            "image_count": r["image_count"],
            "has_image_en": r["image_count"] > 0,
            "has_image_zh": r["image_zh_count"] > 0,
            "alias": r["alias"],
            "alias_full": r["alias_full"],
        }
        for r in count_rows
    }

    tree = _build_tree(PDF_DIR, PDF_DIR, db, papers_by_path, counts_by_id)
    db.commit()
    return jsonify(tree)


def _build_tree(directory, base, db, papers_by_path, counts_by_id):
    """递归构建论文目录树。"""
    node = {
        "name": directory.name if directory != base else "论文库",
        "type": "dir",
        "path": directory.relative_to(base).as_posix() if directory != base else "",
        "children": [],
    }
    try:
        entries = sorted(
            directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        )
    except PermissionError:
        return node

    for entry in entries:
        if entry.is_dir():
            sub = _build_tree(entry, base, db, papers_by_path, counts_by_id)
            node["children"].append(sub)
        elif entry.is_file() and entry.suffix.lower() == ".pdf":
            rel = entry.relative_to(base).as_posix()
            paper = papers_by_path.get(rel)

            if not paper:
                # 自动注册新 PDF
                folder = entry.relative_to(base).parent.as_posix()
                if folder == ".":
                    folder = ""
                cursor = db.execute(
                    "INSERT INTO papers (title, folder, pdf_path) VALUES (?, ?, ?)",
                    (entry.stem, folder, rel),
                )
                paper_id = cursor.lastrowid
                paper = {
                    "id": paper_id,
                    "title": entry.stem,
                    "folder": folder,
                    "pdf_path": rel,
                }
                papers_by_path[rel] = paper

                # 自动发现关联的笔记和插图
                stem = rel.rsplit(".", 1)[0]
                auto_discover_related(db, paper_id, stem)

                # 重新查询计数
                nc = db.execute(
                    "SELECT COUNT(*) AS cnt FROM notes WHERE paper_id = ?",
                    (paper_id,),
                ).fetchone()["cnt"]
                ic = db.execute(
                    "SELECT COUNT(*) AS cnt FROM images WHERE paper_id = ?",
                    (paper_id,),
                ).fetchone()["cnt"]
                ic_zh = db.execute(
                    "SELECT COUNT(*) AS cnt FROM images WHERE paper_id = ? AND file_zh_path IS NOT NULL",
                    (paper_id,),
                ).fetchone()["cnt"]
                counts_by_id[paper_id] = {
                    "note_count": nc,
                    "image_count": ic,
                    "has_image_en": ic > 0,
                    "has_image_zh": ic_zh > 0,
                }

            paper_id = paper["id"]
            counts = counts_by_id.get(
                paper_id,
                {
                    "note_count": 0,
                    "image_count": 0,
                    "has_image_en": False,
                    "has_image_zh": False,
                },
            )
            has_pdf_zh = (PDF_ZH_DIR / rel).exists()

            node["children"].append(
                {
                    "name": entry.stem,
                    "type": "file",
                    "id": paper_id,
                    "noteCount": counts["note_count"],
                    "imageCount": counts["image_count"],
                    "hasPdfZh": has_pdf_zh,
                    "hasImageEn": counts["has_image_en"],
                    "hasImageZh": counts["has_image_zh"],
                    "alias": counts.get("alias"),
                    "aliasFullName": counts.get("alias_full"),
                }
            )

    return node
