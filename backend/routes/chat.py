"""AI 问答路由：会话管理 + Gemini 流式对话。"""

import json

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ..config import PDF_DIR
from ..db import get_connection, get_db
from ..services.gemini import (
    GENAI_AVAILABLE,
    get_client,
    get_rate_limiter,
    get_types,
)

bp = Blueprint("chat", __name__)

# Gemini 模型
CHAT_MODEL = "gemini-3-pro-preview"


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
    return jsonify([dict(r) for r in rows])


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

    data = request.get_json() or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify({"error": "消息不能为空"}), 400

    # 获取历史消息
    history_rows = db.execute(
        "SELECT role, content FROM chat_messages "
        "WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()

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
                    parts.append(genai_types.Part.from_text(text=row["content"]))
                    contents.append(
                        genai_types.Content(role=row["role"], parts=parts)
                    )

                # 追加当前用户消息
                contents.append(
                    genai_types.Content(
                        role="user",
                        parts=[genai_types.Part.from_text(text=user_msg)],
                    )
                )

            config = genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(thinking_level="HIGH"),
            )

            # 流式生成
            chunks_list = []
            for chunk in client.models.generate_content_stream(
                model=CHAT_MODEL,
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
                # 保存用户消息（第一条消息存储完整提示文本）
                if is_first_message:
                    stored_user_msg = user_msg
                else:
                    stored_user_msg = user_msg

                conn.execute(
                    "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, "user", stored_user_msg),
                )
                conn.execute(
                    "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, "model", full_reply),
                )
                # 更新会话时间戳；如果是第一条消息且标题为默认，则自动生成标题
                title_update = ""
                if is_first_message:
                    # 用用户消息的前 30 字作为标题
                    auto_title = user_msg[:30] + ("…" if len(user_msg) > 30 else "")
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
