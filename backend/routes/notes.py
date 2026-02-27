"""笔记路由：CRUD + AI 生成。"""

import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ..config import NOTE_DIR, PDF_DIR
from ..db import get_connection, get_db
from ..services.gemini import (
    GENAI_AVAILABLE,
    get_client,
    get_rate_limiter,
    get_types,
)

bp = Blueprint("notes", __name__)


@bp.route("/api/papers/<int:paper_id>/notes")
def api_list_notes(paper_id):
    """列出论文的所有笔记。"""
    db = get_db()
    notes = db.execute(
        "SELECT id, title, created_at, updated_at FROM notes WHERE paper_id = ? ORDER BY created_at",
        (paper_id,),
    ).fetchall()
    return jsonify([dict(n) for n in notes])


@bp.route("/api/notes/<int:note_id>")
def api_get_note(note_id):
    """按笔记 ID 获取笔记内容。"""
    db = get_db()
    note = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not note:
        return jsonify({"error": "笔记不存在", "exists": False}), 404

    note_file = NOTE_DIR / note["file_path"]
    if not note_file.exists():
        return jsonify(
            {"content": "", "exists": False, "id": note_id, "title": note["title"]}
        )

    try:
        content = note_file.read_text(encoding="utf-8")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(
        {
            "content": content,
            "exists": True,
            "id": note_id,
            "title": note["title"],
        }
    )


@bp.route("/api/papers/<int:paper_id>/notes", methods=["POST"])
def api_create_note(paper_id):
    """为论文创建新笔记。"""
    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    data = request.get_json()
    content = (data or {}).get("content", "")
    title = (data or {}).get("title", "").strip()

    # 生成唯一文件路径
    existing_count = db.execute(
        "SELECT COUNT(*) AS cnt FROM notes WHERE paper_id = ?", (paper_id,)
    ).fetchone()["cnt"]
    stem = paper["pdf_path"].rsplit(".", 1)[0]

    if existing_count == 0:
        file_path = stem + ".md"
    else:
        file_path = f"{stem} ({existing_count + 1}).md"

    if not title:
        title = f"笔记 {existing_count + 1}" if existing_count > 0 else "默认笔记"

    note_file = NOTE_DIR / file_path
    note_file.parent.mkdir(parents=True, exist_ok=True)
    note_file.write_text(content, encoding="utf-8")

    cursor = db.execute(
        "INSERT INTO notes (paper_id, title, file_path) VALUES (?, ?, ?)",
        (paper_id, title, file_path),
    )
    db.commit()

    return jsonify(
        {"success": True, "id": cursor.lastrowid, "title": title}
    )


@bp.route("/api/notes/<int:note_id>", methods=["PUT"])
def api_update_note(note_id):
    """更新笔记内容。"""
    db = get_db()
    note = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not note:
        return jsonify({"error": "笔记不存在"}), 404

    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"error": "缺少 content 字段"}), 400

    title = (data or {}).get("title")

    note_file = NOTE_DIR / note["file_path"]
    note_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        note_file.write_text(data["content"], encoding="utf-8")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if title:
        db.execute(
            'UPDATE notes SET title = ?, updated_at = datetime("now") WHERE id = ?',
            (title, note_id),
        )
    else:
        db.execute(
            'UPDATE notes SET updated_at = datetime("now") WHERE id = ?', (note_id,)
        )
    db.commit()

    return jsonify({"success": True})


@bp.route("/api/notes/<int:note_id>", methods=["DELETE"])
def api_delete_note(note_id):
    """删除笔记。"""
    db = get_db()
    note = db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not note:
        return jsonify({"error": "笔记不存在"}), 404

    note_file = NOTE_DIR / note["file_path"]
    if note_file.exists():
        note_file.unlink()

    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()

    return jsonify({"success": True})


@bp.route("/api/papers/<int:paper_id>/generate-note", methods=["POST"])
def api_generate_note(paper_id):
    """使用 Gemini AI 为论文生成笔记，SSE 流式返回。"""
    if not GENAI_AVAILABLE:
        return jsonify({"error": "google-genai 未安装"}), 500

    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    pdf_file = PDF_DIR / paper["pdf_path"]
    if not pdf_file.exists():
        return jsonify({"error": "PDF 文件不存在"}), 404

    def _stream():
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
                        genai_types.Part.from_bytes(
                            data=pdf_bytes, mime_type="application/pdf"
                        ),
                        genai_types.Part.from_text(
                            text="讲解这篇论文，用中文，附必要的公式或例子"
                        ),
                    ],
                ),
            ]
            config = genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(thinking_level="HIGH"),
            )

            chunks_list = []
            for chunk in client.models.generate_content_stream(
                model="gemini-3-pro-preview",
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    chunks_list.append(chunk.text)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': chunk.text})}\n\n"

            full_text = "".join(chunks_list)

            # 保存文件并创建数据库记录
            conn = get_connection()
            try:
                existing_count = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM notes WHERE paper_id = ?",
                    (paper_id,),
                ).fetchone()["cnt"]
                stem = paper["pdf_path"].rsplit(".", 1)[0]

                if existing_count == 0:
                    file_path = stem + ".md"
                    title = "默认笔记"
                else:
                    file_path = f"{stem} ({existing_count + 1}).md"
                    title = f"笔记 {existing_count + 1}"

                note_file = NOTE_DIR / file_path
                note_file.parent.mkdir(parents=True, exist_ok=True)
                note_file.write_text(full_text, encoding="utf-8")

                cursor = conn.execute(
                    "INSERT INTO notes (paper_id, title, file_path) VALUES (?, ?, ?)",
                    (paper_id, title, file_path),
                )
                conn.commit()
                note_id = cursor.lastrowid
            finally:
                conn.close()

            yield f"data: {json.dumps({'type': 'done', 'note_id': note_id, 'title': title})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(_stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
