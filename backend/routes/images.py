"""插图路由：CRUD + AI 生成 + 翻译。"""

import mimetypes

from flask import Blueprint, abort, jsonify, send_from_directory

from ..config import IMAGE_EN_DIR, IMAGE_ZH_DIR, PDF_DIR
from ..db import get_db
from ..services.gemini import (
    GENAI_AVAILABLE,
    get_client,
    get_rate_limiter,
    get_types,
)

bp = Blueprint("images", __name__)


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
    """使用 Gemini AI 为论文生成插图。"""
    if not GENAI_AVAILABLE:
        return jsonify({"error": "google-genai 未安装"}), 500

    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    pdf_file = PDF_DIR / paper["pdf_path"]
    if not pdf_file.exists():
        return jsonify({"error": "PDF 文件不存在"}), 404

    MAX_RETRIES = 5
    try:
        rate_limiter = get_rate_limiter()
        client = get_client()
        genai_types = get_types()
        rate_limiter.acquire()

        pdf_bytes = pdf_file.read_bytes()
        contents = [
            genai_types.Content(
                role="user",
                parts=[
                    genai_types.Part.from_text(
                        text="为这篇论文绘制一张清晰易懂的，科研论文配图用来辅助讲解这篇论文的核心创新点"
                    ),
                    genai_types.Part.from_bytes(
                        data=pdf_bytes, mime_type="application/pdf"
                    ),
                ],
            ),
        ]
        config = genai_types.GenerateContentConfig(
            image_config=genai_types.ImageConfig(aspect_ratio="4:3", image_size="1K"),
            response_modalities=["IMAGE", "TEXT"],
        )

        # 确定文件路径
        existing_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM images WHERE paper_id = ?", (paper_id,)
        ).fetchone()["cnt"]
        stem = paper["pdf_path"].rsplit(".", 1)[0]

        for attempt in range(1, MAX_RETRIES + 1):
            text_chunks = []
            image_saved = False

            for chunk in client.models.generate_content_stream(
                model="gemini-3-pro-image-preview",
                contents=contents,
                config=config,
            ):
                if chunk.parts is None:
                    continue
                part = chunk.parts[0]
                if part.inline_data and part.inline_data.data:
                    inline_data = part.inline_data
                    file_ext = (
                        mimetypes.guess_extension(inline_data.mime_type) or ".png"
                    )

                    if existing_count == 0:
                        img_path = stem + file_ext
                        title = "默认插图"
                    else:
                        img_path = f"{stem} ({existing_count + 1}){file_ext}"
                        title = f"插图 {existing_count + 1}"

                    out_file = IMAGE_EN_DIR / img_path
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    out_file.write_bytes(inline_data.data)

                    cursor = db.execute(
                        "INSERT INTO images (paper_id, title, file_path) VALUES (?, ?, ?)",
                        (paper_id, title, img_path),
                    )
                    db.commit()
                    image_saved = True
                    return jsonify(
                        {
                            "success": True,
                            "id": cursor.lastrowid,
                            "title": title,
                        }
                    )
                elif chunk.text:
                    text_chunks.append(chunk.text)

            if not image_saved and attempt < MAX_RETRIES:
                received_text = "".join(text_chunks).strip()
                if received_text:
                    contents.append(
                        genai_types.Content(
                            role="model",
                            parts=[
                                genai_types.Part.from_text(text=received_text),
                            ],
                        )
                    )
                contents.append(
                    genai_types.Content(
                        role="user",
                        parts=[
                            genai_types.Part.from_text(
                                text="请直接生成图片，不要只回复文字。"
                            ),
                        ],
                    )
                )

        return jsonify({"error": f"重试 {MAX_RETRIES} 次后仍未生成图片"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/images/<int:image_id>/translate", methods=["POST"])
def api_translate_image(image_id):
    """将英文插图翻译为中文版本。"""
    if not GENAI_AVAILABLE:
        return jsonify({"error": "google-genai 未安装"}), 500

    db = get_db()
    image = db.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if not image:
        return jsonify({"error": "插图不存在"}), 404

    if image["file_zh_path"]:
        return jsonify({"error": "中文版已存在，请先删除再翻译"}), 409

    en_file = IMAGE_EN_DIR / image["file_path"]
    if not en_file.exists():
        return jsonify({"error": "英文插图文件不存在"}), 404

    MAX_RETRIES = 5
    try:
        rate_limiter = get_rate_limiter()
        client = get_client()
        genai_types = get_types()
        rate_limiter.acquire()

        img_bytes = en_file.read_bytes()
        mime = mimetypes.guess_type(str(en_file))[0] or "image/png"

        contents = [
            genai_types.Content(
                role="user",
                parts=[
                    genai_types.Part.from_bytes(data=img_bytes, mime_type=mime),
                    genai_types.Part.from_text(
                        text="将图改为中文版本，Memory指的是记忆"
                    ),
                ],
            ),
        ]
        config = genai_types.GenerateContentConfig(
            image_config=genai_types.ImageConfig(aspect_ratio="4:3", image_size="2K"),
            response_modalities=["IMAGE", "TEXT"],
        )

        for attempt in range(1, MAX_RETRIES + 1):
            text_chunks = []
            image_saved = False

            for chunk in client.models.generate_content_stream(
                model="gemini-3-pro-image-preview",
                contents=contents,
                config=config,
            ):
                if chunk.parts is None:
                    continue
                part = chunk.parts[0]
                if part.inline_data and part.inline_data.data:
                    inline_data = part.inline_data
                    file_ext = (
                        mimetypes.guess_extension(inline_data.mime_type) or ".png"
                    )
                    en_base = image["file_path"].rsplit(".", 1)[0]
                    zh_path = en_base + file_ext

                    out_file = IMAGE_ZH_DIR / zh_path
                    out_file.parent.mkdir(parents=True, exist_ok=True)
                    out_file.write_bytes(inline_data.data)

                    db.execute(
                        "UPDATE images SET file_zh_path = ? WHERE id = ?",
                        (zh_path, image_id),
                    )
                    db.commit()
                    image_saved = True
                    return jsonify({"success": True})
                elif chunk.text:
                    text_chunks.append(chunk.text)

            if not image_saved and attempt < MAX_RETRIES:
                received_text = "".join(text_chunks).strip()
                if received_text:
                    contents.append(
                        genai_types.Content(
                            role="model",
                            parts=[
                                genai_types.Part.from_text(text=received_text),
                            ],
                        )
                    )
                contents.append(
                    genai_types.Content(
                        role="user",
                        parts=[
                            genai_types.Part.from_text(
                                text="请直接生成中文版图片，不要只回复文字。"
                            ),
                        ],
                    )
                )

        return jsonify({"error": f"重试 {MAX_RETRIES} 次后仍未生成图片"}), 500
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
