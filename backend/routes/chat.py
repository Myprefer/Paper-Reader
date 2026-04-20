"""AI 问答路由：会话管理 + Gemini 流式对话。"""

import json
import mimetypes
import uuid
from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from ..config import CHAT_IMAGE_DIR, PDF_DIR
from ..db import get_connection, get_db
from ..services.gemini import (
    GENAI_AVAILABLE,
    get_client,
    get_rate_limiter,
    get_types,
)

bp = Blueprint("chat", __name__)

CHAT_ALLOWED_MODELS = {
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
}
DEFAULT_CHAT_MODEL = "gemini-3.1-pro-preview"
MAX_IMAGES_PER_MESSAGE = 10


def _build_chat_config(genai_types, model: str):
    if model.startswith("gemini-2.5"):
        try:
            thinking_config = genai_types.ThinkingConfig(thinkingBudget=-1)
        except TypeError:
            thinking_config = genai_types.ThinkingConfig(thinking_budget=-1)
        return genai_types.GenerateContentConfig(thinking_config=thinking_config)

    return genai_types.GenerateContentConfig(
        thinking_config=genai_types.ThinkingConfig(thinking_level="HIGH"),
    )


# ── 会话 CRUD ──


@bp.route("/api/papers/<int:paper_id>/chat-sessions")
def api_list_sessions(paper_id):
    """列出论文的所有对话会话。"""
    db = get_db()
    rows = db.execute(
        "SELECT id, title, created_at, updated_at FROM chat_sessions "
        "WHERE paper_id = ? ORDER BY updated_at DESC",
        (paper_id,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/api/papers/<int:paper_id>/chat-sessions", methods=["POST"])
def api_create_session(paper_id):
    """为论文创建新的对话会话。"""
    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    data = request.get_json() or {}
    title = data.get("title", "").strip() or "新对话"

    cursor = db.execute(
        "INSERT INTO chat_sessions (paper_id, title) VALUES (?, ?)",
        (paper_id, title),
    )
    db.commit()
    session_id = cursor.lastrowid

    return jsonify({"success": True, "id": session_id, "title": title})


@bp.route("/api/chat-sessions/<int:session_id>", methods=["PUT"])
def api_update_session(session_id):
    """更新会话标题。"""
    db = get_db()
    session = db.execute(
        "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    data = request.get_json() or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "标题不能为空"}), 400

    db.execute(
        'UPDATE chat_sessions SET title = ?, updated_at = datetime("now") WHERE id = ?',
        (title, session_id),
    )
    db.commit()
    return jsonify({"success": True})


@bp.route("/api/chat-sessions/<int:session_id>", methods=["DELETE"])
def api_delete_session(session_id):
    """删除对话会话及其消息。"""
    db = get_db()
    session = db.execute(
        "SELECT id FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    db.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    db.commit()

    session_image_dir = CHAT_IMAGE_DIR / str(session_id)
    if session_image_dir.exists():
        for file_path in session_image_dir.glob("*"):
            if file_path.is_file():
                file_path.unlink(missing_ok=True)
        session_image_dir.rmdir()
    return jsonify({"success": True})


# ── 消息 ──


@bp.route("/api/chat-sessions/<int:session_id>/messages")
def api_list_messages(session_id):
    """获取会话的所有消息。"""
    db = get_db()
    rows = db.execute(
        "SELECT id, role, content, created_at FROM chat_messages "
        "WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()

    message_ids = [r["id"] for r in rows]
    image_map = {mid: [] for mid in message_ids}
    if message_ids:
        placeholders = ",".join(["?"] * len(message_ids))
        image_rows = db.execute(
            f"SELECT message_id, file_path FROM chat_message_images WHERE message_id IN ({placeholders}) ORDER BY sort_index ASC, id ASC",
            tuple(message_ids),
        ).fetchall()
        for image_row in image_rows:
            image_map.setdefault(image_row["message_id"], []).append(
                f"/api/chat-images/{image_row['file_path']}"
            )

    result = []
    for row in rows:
        item = dict(row)
        item["image_urls"] = image_map.get(row["id"], [])
        result.append(item)
    return jsonify(result)


@bp.route("/api/chat-images/<path:relative_path>")
def api_chat_image_file(relative_path):
    """读取聊天消息图片文件。"""
    full_path = (CHAT_IMAGE_DIR / relative_path).resolve()
    if not str(full_path).startswith(str(CHAT_IMAGE_DIR.resolve())):
        return jsonify({"error": "非法路径"}), 400
    if not full_path.exists() or not full_path.is_file():
        return jsonify({"error": "图片不存在"}), 404
    mime_type = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"
    return send_file(full_path, mimetype=mime_type)


# ── AI 对话（SSE 流式） ──


@bp.route("/api/chat-sessions/<int:session_id>/chat", methods=["POST"])
def api_chat(session_id):
    """向 Gemini 发送对话消息，SSE 流式返回回复。

    第一条消息时自动附带论文 PDF。
    """
    if not GENAI_AVAILABLE:
        return jsonify({"error": "google-genai 未安装"}), 500

    db = get_db()
    session = db.execute(
        "SELECT cs.*, p.pdf_path FROM chat_sessions cs "
        "JOIN papers p ON p.id = cs.paper_id "
        "WHERE cs.id = ?",
        (session_id,),
    ).fetchone()
    if not session:
        return jsonify({"error": "会话不存在"}), 404

    user_msg = ""
    request_images = []
    model = DEFAULT_CHAT_MODEL

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        user_msg = (request.form.get("message") or "").strip()
        model = (request.form.get("model") or DEFAULT_CHAT_MODEL).strip()

        image_files = request.files.getlist("images")
        if not image_files:
            single_file = request.files.get("image")
            if single_file:
                image_files = [single_file]

        for image_file in image_files:
            if not image_file or not image_file.filename:
                continue
            image_data = image_file.read()
            if not image_data:
                continue
            request_images.append(
                {
                    "bytes": image_data,
                    "mime": image_file.mimetype or "image/png",
                }
            )
    else:
        data = request.get_json() or {}
        user_msg = (data.get("message") or "").strip()
        model = (data.get("model") or DEFAULT_CHAT_MODEL).strip()

    if model not in CHAT_ALLOWED_MODELS:
        return jsonify({"error": "不支持的问答模型"}), 400

    if len(request_images) > MAX_IMAGES_PER_MESSAGE:
        return jsonify({"error": f"每条消息最多上传 {MAX_IMAGES_PER_MESSAGE} 张图片"}), 400

    if not user_msg and not request_images:
        return jsonify({"error": "消息和图片不能同时为空"}), 400

    # 获取历史消息
    history_rows = db.execute(
        "SELECT id, role, content FROM chat_messages "
        "WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()

    history_message_ids = [row["id"] for row in history_rows]
    history_image_map = {mid: [] for mid in history_message_ids}
    if history_message_ids:
        placeholders = ",".join(["?"] * len(history_message_ids))
        history_image_rows = db.execute(
            f"SELECT message_id, file_path FROM chat_message_images WHERE message_id IN ({placeholders}) ORDER BY sort_index ASC, id ASC",
            tuple(history_message_ids),
        ).fetchall()
        for image_row in history_image_rows:
            history_image_map.setdefault(image_row["message_id"], []).append(
                image_row["file_path"]
            )

    pdf_path = PDF_DIR / session["pdf_path"]
    is_first_message = len(history_rows) == 0

    def _stream():
        try:
            rate_limiter = get_rate_limiter()
            client = get_client()
            genai_types = get_types()

            rate_limiter.acquire()

            # 构建对话 contents
            contents = []

            if is_first_message:
                # 第一条消息：包含 PDF
                parts = []
                if pdf_path.exists():
                    pdf_bytes = pdf_path.read_bytes()
                    parts.append(
                        genai_types.Part.from_bytes(
                            data=pdf_bytes, mime_type="application/pdf"
                        )
                    )
                for image in request_images:
                    parts.append(
                        genai_types.Part.from_bytes(
                            data=image["bytes"], mime_type=image["mime"]
                        )
                    )
                if user_msg:
                    parts.append(
                        genai_types.Part.from_text(
                            text=(
                                f"{user_msg}"
                            )
                        )
                    )
                contents.append(
                    genai_types.Content(role="user", parts=parts)
                )
            else:
                # 后续消息：加载历史 + 新消息
                # 第一条历史消息添加 PDF（如果会话是带 PDF 开始的）
                for idx, row in enumerate(history_rows):
                    parts = []
                    if idx == 0 and row["role"] == "user" and pdf_path.exists():
                        pdf_bytes = pdf_path.read_bytes()
                        parts.append(
                            genai_types.Part.from_bytes(
                                data=pdf_bytes, mime_type="application/pdf"
                            )
                        )
                    if row["role"] == "user":
                        for image_rel_path in history_image_map.get(row["id"], []):
                            image_path = CHAT_IMAGE_DIR / image_rel_path
                            if image_path.exists() and image_path.is_file():
                                mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
                                parts.append(
                                    genai_types.Part.from_bytes(
                                        data=image_path.read_bytes(), mime_type=mime
                                    )
                                )
                    if row["content"]:
                        parts.append(genai_types.Part.from_text(text=row["content"]))
                    contents.append(
                        genai_types.Content(role=row["role"], parts=parts)
                    )

                # 追加当前用户消息
                current_parts = []
                for image in request_images:
                    current_parts.append(
                        genai_types.Part.from_bytes(
                            data=image["bytes"], mime_type=image["mime"]
                        )
                    )
                if user_msg:
                    current_parts.append(genai_types.Part.from_text(text=user_msg))
                contents.append(
                    genai_types.Content(
                        role="user",
                        parts=current_parts,
                    )
                )

            config = _build_chat_config(genai_types, model)

            # 流式生成
            chunks_list = []
            for chunk in client.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    chunks_list.append(chunk.text)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': chunk.text})}\n\n"

            full_reply = "".join(chunks_list)

            # 保存用户消息和 AI 回复到数据库
            conn = get_connection()
            try:
                # 保存用户消息
                stored_user_msg = user_msg
                cursor = conn.execute(
                    "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, "user", stored_user_msg),
                )
                user_message_id = cursor.lastrowid

                if request_images:
                    session_image_dir = CHAT_IMAGE_DIR / str(session_id)
                    session_image_dir.mkdir(parents=True, exist_ok=True)
                    for idx, image in enumerate(request_images):
                        file_ext = mimetypes.guess_extension(image["mime"]) or ".png"
                        file_name = f"{user_message_id}_{idx}_{uuid.uuid4().hex[:8]}{file_ext}"
                        rel_path = f"{session_id}/{file_name}"
                        out_path = CHAT_IMAGE_DIR / rel_path
                        out_path.write_bytes(image["bytes"])
                        conn.execute(
                            "INSERT INTO chat_message_images (message_id, file_path, sort_index) VALUES (?, ?, ?)",
                            (user_message_id, rel_path, idx),
                        )

                conn.execute(
                    "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, "model", full_reply),
                )
                # 更新会话时间戳；如果是第一条消息且标题为默认，则自动生成标题
                title_update = ""
                if is_first_message:
                    # 用用户消息的前 30 字作为标题
                    auto_title_seed = user_msg if user_msg else "图片问答"
                    auto_title = auto_title_seed[:30] + ("…" if len(auto_title_seed) > 30 else "")
                    conn.execute(
                        'UPDATE chat_sessions SET title = ?, updated_at = datetime("now") WHERE id = ?',
                        (auto_title, session_id),
                    )
                    title_update = auto_title
                else:
                    conn.execute(
                        'UPDATE chat_sessions SET updated_at = datetime("now") WHERE id = ?',
                        (session_id,),
                    )

                conn.commit()
            finally:
                conn.close()

            done_data = {"type": "done"}
            if title_update:
                done_data["title"] = title_update
            yield f"data: {json.dumps(done_data)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(_stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
