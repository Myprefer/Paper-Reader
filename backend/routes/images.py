"""插图路由：CRUD + AI 生成 + 翻译。"""

import mimetypes

from flask import Blueprint, abort, jsonify, request, send_from_directory

from ..config import (
    IMAGE_EN_DIR,
    IMAGE_ZH_DIR,
    OPENAI_DEFAULT_IMAGE_MODEL,
    OPENAI_DEFAULT_TEXT_MODEL,
    PDF_DIR,
)
from ..db import get_db
from ..services.openai_compatible import (
    AI_AVAILABLE,
    edit_image,
    extract_pdf_text,
    generate_image,
    image_models,
    paper_illustration_prompt,
)

bp = Blueprint("images", __name__)

IMAGE_ALLOWED_MODELS = set(image_models())
DEFAULT_IMAGE_MODEL = OPENAI_DEFAULT_IMAGE_MODEL


@bp.route("/api/papers/<int:paper_id>/images")
def api_list_images(paper_id):
    """列出论文的所有插图。"""
    db = get_db()
    images = db.execute(
        "SELECT id, title, file_path, file_zh_path, created_at "
        "FROM images WHERE paper_id = ? ORDER BY created_at",
        (paper_id,),
    ).fetchall()
    result = []
    for img in images:
        result.append(
            {
                "id": img["id"],
                "title": img["title"],
                "has_zh": img["file_zh_path"] is not None,
                "created_at": img["created_at"],
            }
        )
    return jsonify(result)


@bp.route("/api/images/<int:image_id>/<lang>")
def api_serve_image(image_id, lang):
    """按插图 ID 和语言提供图片文件。"""
    if lang not in ("en", "zh"):
        abort(404)
    db = get_db()
    image = db.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if not image:
        abort(404)

    if lang == "zh":
        if not image["file_zh_path"]:
            abort(404)
        img_dir = IMAGE_ZH_DIR
        filepath = image["file_zh_path"]
    else:
        img_dir = IMAGE_EN_DIR
        filepath = image["file_path"]

    target = (img_dir / filepath).resolve()
    try:
        target.relative_to(img_dir.resolve())
    except ValueError:
        abort(403)
    if not target.exists():
        abort(404)
    return send_from_directory(img_dir, filepath)


@bp.route("/api/papers/<int:paper_id>/generate-image", methods=["POST"])
def api_generate_image(paper_id):
    """使用 OpenAI-compatible API 为论文生成插图。"""
    if not AI_AVAILABLE:
        return jsonify({"error": "OpenAI-compatible API 未配置"}), 500

    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    pdf_file = PDF_DIR / paper["pdf_path"]
    if not pdf_file.exists():
        return jsonify({"error": "PDF 文件不存在"}), 404

    data = request.get_json(silent=True) or {}
    model = (data.get("model") or DEFAULT_IMAGE_MODEL).strip()
    if model not in IMAGE_ALLOWED_MODELS:
        return jsonify({"error": "不支持的插图模型"}), 400

    try:
        pdf_text = extract_pdf_text(pdf_file)
        prompt = paper_illustration_prompt(pdf_text, model=OPENAI_DEFAULT_TEXT_MODEL)
        image_bytes, mime_type = generate_image(prompt, model=model)

        # 确定文件路径
        existing_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM images WHERE paper_id = ?", (paper_id,)
        ).fetchone()["cnt"]
        stem = paper["pdf_path"].rsplit(".", 1)[0]

        file_ext = mimetypes.guess_extension(mime_type) or ".png"
        if existing_count == 0:
            img_path = stem + file_ext
            title = "默认插图"
        else:
            img_path = f"{stem} ({existing_count + 1}){file_ext}"
            title = f"插图 {existing_count + 1}"

        out_file = IMAGE_EN_DIR / img_path
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(image_bytes)
        cursor = db.execute(
            "INSERT INTO images (paper_id, title, file_path) VALUES (?, ?, ?)",
            (paper_id, title, img_path),
        )
        db.commit()
        return jsonify({"success": True, "id": cursor.lastrowid, "title": title})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/images/<int:image_id>/translate", methods=["POST"])
def api_translate_image(image_id):
    """将英文插图翻译为中文版本。"""
    if not AI_AVAILABLE:
        return jsonify({"error": "OpenAI-compatible API 未配置"}), 500

    db = get_db()
    image = db.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if not image:
        return jsonify({"error": "插图不存在"}), 404

    if image["file_zh_path"]:
        return jsonify({"error": "中文版已存在，请先删除再翻译"}), 409

    en_file = IMAGE_EN_DIR / image["file_path"]
    if not en_file.exists():
        return jsonify({"error": "英文插图文件不存在"}), 404

    try:
        img_bytes = en_file.read_bytes()
        mime = mimetypes.guess_type(str(en_file))[0] or "image/png"
        translated_bytes, translated_mime = edit_image(
            img_bytes,
            mime,
            "保持原图构图、风格和所有视觉元素不变，只把图中的英文文字准确翻译为简体中文。Memory 翻译为“记忆”。",
            model=DEFAULT_IMAGE_MODEL,
        )
        file_ext = mimetypes.guess_extension(translated_mime) or ".png"
        en_base = image["file_path"].rsplit(".", 1)[0]
        zh_path = en_base + file_ext
        out_file = IMAGE_ZH_DIR / zh_path
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(translated_bytes)
        db.execute(
            "UPDATE images SET file_zh_path = ? WHERE id = ?",
            (zh_path, image_id),
        )
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/images/<int:image_id>", methods=["DELETE"])
def api_delete_image(image_id):
    """删除插图（包括中英文版本）。"""
    db = get_db()
    image = db.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if not image:
        return jsonify({"error": "插图不存在"}), 404

    deleted = []

    # 删除英文文件
    en_file = IMAGE_EN_DIR / image["file_path"]
    if en_file.exists():
        en_file.unlink()
        deleted.append(image["file_path"])

    # 删除中文文件
    if image["file_zh_path"]:
        zh_file = IMAGE_ZH_DIR / image["file_zh_path"]
        if zh_file.exists():
            zh_file.unlink()
            deleted.append(image["file_zh_path"])

    db.execute("DELETE FROM images WHERE id = ?", (image_id,))
    db.commit()

    return jsonify({"success": True, "deleted": deleted})
