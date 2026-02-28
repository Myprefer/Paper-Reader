"""论文路由：PDF 服务、中文 PDF 获取、导入、移动、文件夹列表、上传。"""

import json
import mimetypes
import re
import shutil
from pathlib import Path

import requests
from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    request,
    send_from_directory,
    stream_with_context,
)
from werkzeug.utils import secure_filename

from ..config import (
    IMAGE_EN_DIR,
    IMAGE_EXTENSIONS,
    IMAGE_ZH_DIR,
    NOTE_DIR,
    PDF_DIR,
    PDF_ZH_DIR,
)
from ..db import get_connection, get_db
from ..services.gemini import (
    GENAI_AVAILABLE,
    get_client,
    get_rate_limiter,
    get_types,
)

bp = Blueprint("papers", __name__)


# ────────── PDF 服务 ──────────


@bp.route("/api/papers/<int:paper_id>/pdf/<lang>")
def api_pdf(paper_id, lang):
    """根据论文 ID 和语言提供 PDF 文件。"""
    if lang not in ("en", "zh"):
        abort(404)
    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        abort(404)

    pdf_root = PDF_ZH_DIR if lang == "zh" else PDF_DIR
    filepath = paper["pdf_path"]
    target = (pdf_root / filepath).resolve()
    try:
        target.relative_to(pdf_root.resolve())
    except ValueError:
        abort(403)
    if not target.exists():
        abort(404)
    return send_from_directory(pdf_root, filepath)


@bp.route("/api/papers/<int:paper_id>/pdf-exists/<lang>")
def api_pdf_exists(paper_id, lang):
    """检查指定语言的 PDF 是否存在。"""
    if lang not in ("en", "zh"):
        return jsonify({"exists": False})
    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"exists": False})

    pdf_root = PDF_ZH_DIR if lang == "zh" else PDF_DIR
    target = (pdf_root / paper["pdf_path"]).resolve()
    try:
        target.relative_to(pdf_root.resolve())
    except ValueError:
        return jsonify({"exists": False})
    return jsonify({"exists": target.exists() and target.is_file()})


# ────────── 上传中文 PDF ──────────


@bp.route("/api/papers/<int:paper_id>/upload-zh-pdf", methods=["POST"])
def api_upload_zh_pdf(paper_id):
    """手动上传中文 PDF 文件。"""
    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "请上传 PDF 文件"}), 400

    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "仅支持 PDF 文件"}), 400

    dest_path = PDF_ZH_DIR / paper["pdf_path"]
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    f.save(str(dest_path))

    db.execute(
        'UPDATE papers SET pdf_zh_path = ?, updated_at = datetime("now") WHERE id = ?',
        (paper["pdf_path"], paper_id),
    )
    db.commit()

    return jsonify({"success": True, "size": dest_path.stat().st_size})


# ────────── 获取中文 PDF ──────────


@bp.route("/api/papers/<int:paper_id>/fetch-zh-pdf", methods=["POST"])
def api_fetch_zh_pdf(paper_id):
    """通过 arXiv ID 从 hjfy.top 下载中文翻译 PDF。"""
    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    dest_path = PDF_ZH_DIR / paper["pdf_path"]
    if dest_path.exists():
        return jsonify({"error": "中文 PDF 已存在"}), 409

    data = request.get_json()
    raw = (data or {}).get("arxiv_id", "").strip()
    if not raw:
        return jsonify({"error": "请提供 arXiv ID"}), 400

    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", raw)
    if not m:
        return jsonify({"error": f"无法解析 arXiv ID: {raw}"}), 400
    arxiv_id = m.group(1)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://hjfy.top/arxiv/{arxiv_id}",
    }
    try:
        resp = requests.get(
            f"https://hjfy.top/api/arxivFiles/{arxiv_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        api_data = resp.json()
        zh_url = api_data.get("data", {}).get("zhCN")
        if not zh_url:
            return jsonify({"error": "该论文暂无中文翻译（hjfy.top 未收录）"}), 404

        pdf_resp = requests.get(zh_url, headers=headers, timeout=120)
        pdf_resp.raise_for_status()

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(pdf_resp.content)

        db.execute(
            'UPDATE papers SET pdf_zh_path = ?, updated_at = datetime("now") WHERE id = ?',
            (paper["pdf_path"], paper_id),
        )
        db.commit()

        return jsonify({"success": True, "size": len(pdf_resp.content)})
    except requests.RequestException as e:
        return jsonify({"error": f"下载失败: {e}"}), 500


# ────────── 文件夹列表 ──────────


@bp.route("/api/folders")
def api_folders():
    """列出 pdfs/ 下指定父目录的直接子文件夹。"""
    parent = request.args.get("parent", "").strip()
    target = (PDF_DIR / parent).resolve()
    try:
        target.relative_to(PDF_DIR.resolve())
    except ValueError:
        abort(403)
    if not target.is_dir():
        return jsonify([])

    children = []
    try:
        for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if entry.is_dir():
                rel = entry.relative_to(PDF_DIR).as_posix()
                has_sub = any(e.is_dir() for e in entry.iterdir())
                children.append(
                    {"name": entry.name, "path": rel, "hasChildren": has_sub}
                )
    except PermissionError:
        pass
    return jsonify(children)


# ────────── 移动论文 ──────────


@bp.route("/api/papers/<int:paper_id>/move", methods=["POST"])
def api_move_paper(paper_id):
    """移动论文及其关联文件到新的文件夹。"""
    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    data = request.get_json()
    dest_folder = (data or {}).get("dest_folder", "").strip()

    old_pdf_path = paper["pdf_path"]
    filename = old_pdf_path.rsplit("/", 1)[-1]
    new_pdf_path = f"{dest_folder}/{filename}" if dest_folder else filename

    if old_pdf_path == new_pdf_path:
        return jsonify({"error": "源路径与目标相同"}), 400

    if (PDF_DIR / new_pdf_path).exists():
        return jsonify({"error": f"目标已存在: {new_pdf_path}"}), 409

    moved = []
    try:
        # 移动英文 PDF
        src = PDF_DIR / old_pdf_path
        dst = PDF_DIR / new_pdf_path
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved.append(new_pdf_path)

        # 移动中文 PDF
        src_zh = PDF_ZH_DIR / old_pdf_path
        dst_zh = PDF_ZH_DIR / new_pdf_path
        if src_zh.exists():
            dst_zh.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_zh), str(dst_zh))
            moved.append(f"pdfs_zh/{new_pdf_path}")

        # 移动笔记文件
        notes = db.execute(
            "SELECT * FROM notes WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        for note in notes:
            old_note_path = note["file_path"]
            note_filename = old_note_path.rsplit("/", 1)[-1]
            new_note_path = (
                f"{dest_folder}/{note_filename}" if dest_folder else note_filename
            )
            src_n = NOTE_DIR / old_note_path
            dst_n = NOTE_DIR / new_note_path
            if src_n.exists():
                dst_n.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_n), str(dst_n))
                moved.append(f"notes/{new_note_path}")
            db.execute(
                "UPDATE notes SET file_path = ? WHERE id = ?",
                (new_note_path, note["id"]),
            )

        # 移动插图文件
        images = db.execute(
            "SELECT * FROM images WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        for img in images:
            old_img_path = img["file_path"]
            img_filename = old_img_path.rsplit("/", 1)[-1]
            new_img_path = (
                f"{dest_folder}/{img_filename}" if dest_folder else img_filename
            )
            src_i = IMAGE_EN_DIR / old_img_path
            dst_i = IMAGE_EN_DIR / new_img_path
            if src_i.exists():
                dst_i.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src_i), str(dst_i))
                moved.append(f"images/{new_img_path}")

            new_img_zh_path = None
            if img["file_zh_path"]:
                old_zh = img["file_zh_path"]
                zh_filename = old_zh.rsplit("/", 1)[-1]
                new_img_zh_path = (
                    f"{dest_folder}/{zh_filename}" if dest_folder else zh_filename
                )
                src_iz = IMAGE_ZH_DIR / old_zh
                dst_iz = IMAGE_ZH_DIR / new_img_zh_path
                if src_iz.exists():
                    dst_iz.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src_iz), str(dst_iz))
                    moved.append(f"images_zh/{new_img_zh_path}")

            db.execute(
                "UPDATE images SET file_path = ?, file_zh_path = ? WHERE id = ?",
                (new_img_path, new_img_zh_path, img["id"]),
            )

        # 更新论文记录
        pdf_zh_path = new_pdf_path if paper["pdf_zh_path"] else None
        db.execute(
            'UPDATE papers SET folder = ?, pdf_path = ?, pdf_zh_path = ?, updated_at = datetime("now") WHERE id = ?',
            (dest_folder, new_pdf_path, pdf_zh_path, paper_id),
        )
        db.commit()

    except Exception as e:
        return jsonify({"error": f"移动失败: {e}", "moved": moved}), 500

    return jsonify({"success": True, "moved": moved})


# ────────── 手动上传导入论文 ──────────


@bp.route("/api/upload-paper", methods=["POST"])
def api_upload_paper():
    """手动上传本地 PDF 文件导入论文。

    接受 multipart/form-data：
      - file: 英文/原版 PDF（必填）
      - file_zh: 中文 PDF（可选）
      - folder: 保存文件夹路径（可选）
      - title: 论文标题（可选，默认取文件名）
    """
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "请上传 PDF 文件"}), 400

    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "仅支持 PDF 文件"}), 400

    folder = request.form.get("folder", "").strip()
    title = request.form.get("title", "").strip()
    filename = f.filename  # 保持原始文件名

    # 清理文件名中的危险字符，但保留中文等 Unicode 字符
    safe_chars = re.sub(r'[<>:"/\\|?*]', '', filename)
    if not safe_chars:
        safe_chars = "paper.pdf"
    if not safe_chars.lower().endswith(".pdf"):
        safe_chars += ".pdf"

    if not title:
        title = safe_chars.rsplit(".", 1)[0]  # 去掉 .pdf

    pdf_path = f"{folder}/{safe_chars}" if folder else safe_chars

    # 检查是否已存在
    db = get_db()
    existing = db.execute(
        "SELECT id FROM papers WHERE pdf_path = ?", (pdf_path,)
    ).fetchone()
    if existing:
        return jsonify({"error": f"论文已存在: {pdf_path}", "paper_id": existing["id"]}), 409

    # 保存英文 PDF
    en_dest = PDF_DIR / pdf_path
    en_dest.parent.mkdir(parents=True, exist_ok=True)
    f.save(str(en_dest))

    # 保存中文 PDF（如果有）
    f_zh = request.files.get("file_zh")
    pdf_zh_path = None
    if f_zh and f_zh.filename:
        zh_dest = PDF_ZH_DIR / pdf_path
        zh_dest.parent.mkdir(parents=True, exist_ok=True)
        f_zh.save(str(zh_dest))
        pdf_zh_path = pdf_path

    # 注册到数据库
    cursor = db.execute(
        "INSERT INTO papers (title, folder, pdf_path, pdf_zh_path) VALUES (?, ?, ?, ?)",
        (title, folder, pdf_path, pdf_zh_path),
    )
    paper_id = cursor.lastrowid
    db.commit()

    # 提取论文别名（使用 flash 模型，很快）
    try:
        alias, alias_full = _extract_alias(en_dest)
        if alias:
            db.execute(
                "UPDATE papers SET alias = ?, alias_full = ? WHERE id = ?",
                (alias, alias_full, paper_id),
            )
            db.commit()
    except Exception:
        pass  # 别名提取失败不影响导入

    return jsonify({
        "success": True,
        "paper_id": paper_id,
        "title": title,
        "pdf_path": pdf_path,
    })


# ────────── 导入论文 ──────────


@bp.route("/api/import-paper", methods=["POST"])
def api_import_paper():
    """通过 arXiv ID 导入论文，SSE 流式返回进度。"""
    data = request.get_json()
    raw = (data or {}).get("arxiv_id", "").strip()
    folder = (data or {}).get("folder", "").strip()

    if not raw:
        return jsonify({"error": "请提供 arXiv ID"}), 400

    m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?", raw)
    if not m:
        return jsonify({"error": f"无法解析 arXiv ID: {raw}"}), 400
    arxiv_id = m.group(1)

    def stream():
        paper_id = None
        safe_name = arxiv_id
        stem_rel = None
        pdf_path = None

        # ── Step 1: 获取论文标题 ──
        yield _sse(
            {"step": "title", "status": "working", "msg": "正在获取论文信息…"}
        )
        try:
            resp = requests.get(
                f"http://export.arxiv.org/api/query?id_list={arxiv_id}", timeout=15
            )
            resp.raise_for_status()
            all_titles = re.findall(
                r"<title[^>]*>(.*?)</title>", resp.text, re.DOTALL
            )
            paper_title = arxiv_id
            for t in all_titles:
                t = t.strip()
                if t and t.lower() != "arxiv query:":
                    paper_title = re.sub(r"[\n\r]+", " ", t).strip()
                    paper_title = re.sub(r"\s+", " ", paper_title)

            safe_name = re.sub(r'[<>:"/\\|?*]', "", paper_title)[:150].strip()
            if not safe_name:
                safe_name = arxiv_id

            stem_rel = f"{folder}/{safe_name}" if folder else safe_name
            pdf_path = stem_rel + ".pdf"

            yield _sse(
                {
                    "step": "title",
                    "status": "done",
                    "msg": f"标题: {paper_title}",
                }
            )
        except Exception:
            stem_rel = f"{folder}/{safe_name}" if folder else safe_name
            pdf_path = stem_rel + ".pdf"
            yield _sse(
                {
                    "step": "title",
                    "status": "warn",
                    "msg": f"获取标题失败，使用 ID: {arxiv_id}",
                }
            )

        # ── Step 2: 下载原文 PDF ──
        en_pdf = PDF_DIR / pdf_path
        if en_pdf.exists():
            yield _sse(
                {"step": "pdf_en", "status": "skip", "msg": "原文 PDF 已存在，跳过"}
            )
        else:
            yield _sse(
                {
                    "step": "pdf_en",
                    "status": "working",
                    "msg": "正在下载原文 PDF…",
                }
            )
            try:
                r = requests.get(
                    f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                    timeout=120,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    },
                )
                r.raise_for_status()
                en_pdf.parent.mkdir(parents=True, exist_ok=True)
                en_pdf.write_bytes(r.content)
                yield _sse(
                    {
                        "step": "pdf_en",
                        "status": "done",
                        "msg": f"原文 PDF 下载完成 ({len(r.content) // 1024}KB)",
                    }
                )
            except Exception as e:
                yield _sse(
                    {
                        "step": "pdf_en",
                        "status": "error",
                        "msg": f"原文 PDF 下载失败: {e}",
                    }
                )
                yield _sse(
                    {
                        "step": "finish",
                        "status": "error",
                        "msg": "无法下载原文 PDF，导入终止",
                    }
                )
                return

        # 注册论文到数据库
        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT id FROM papers WHERE pdf_path = ?", (pdf_path,)
            ).fetchone()
            if existing:
                paper_id = existing["id"]
            else:
                cursor = conn.execute(
                    "INSERT INTO papers (title, folder, pdf_path, arxiv_id) VALUES (?, ?, ?, ?)",
                    (safe_name, folder, pdf_path, arxiv_id),
                )
                paper_id = cursor.lastrowid
                conn.commit()
        finally:
            conn.close()

        # ── 提取论文别名（快速，使用 flash 模型） ──
        yield _sse(
            {"step": "alias", "status": "working", "msg": "正在提取论文别名…"}
        )
        try:
            alias, alias_full = _extract_alias(en_pdf)
            if alias:
                conn = get_connection()
                try:
                    conn.execute(
                        "UPDATE papers SET alias = ?, alias_full = ? WHERE id = ?",
                        (alias, alias_full, paper_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
                alias_parts = [p for p in [alias, alias_full] if p]
                yield _sse(
                    {
                        "step": "alias",
                        "status": "done",
                        "msg": f"别名: {' - '.join(alias_parts)}",
                    }
                )
            else:
                yield _sse(
                    {"step": "alias", "status": "skip", "msg": "未检测到论文别名"}
                )
        except Exception as e:
            yield _sse(
                {"step": "alias", "status": "warn", "msg": f"别名提取失败: {e}"}
            )

        # 提前发送 paper_id，前端收到后即可关闭导入窗口
        yield _sse(
            {
                "step": "registered",
                "status": "done",
                "paper_id": paper_id,
                "msg": "论文已就绪，后续处理将在后台继续",
            }
        )

        # ── Step 3: 下载中文翻译 PDF ──
        zh_pdf = PDF_ZH_DIR / pdf_path
        if zh_pdf.exists():
            yield _sse(
                {"step": "pdf_zh", "status": "skip", "msg": "中文 PDF 已存在，跳过"}
            )
        else:
            yield _sse(
                {
                    "step": "pdf_zh",
                    "status": "working",
                    "msg": "正在获取中文翻译 PDF…",
                }
            )
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Referer": f"https://hjfy.top/arxiv/{arxiv_id}",
                }
                resp = requests.get(
                    f"https://hjfy.top/api/arxivFiles/{arxiv_id}",
                    headers=headers,
                    timeout=30,
                )
                resp.raise_for_status()
                api_data = resp.json()
                zh_url = api_data.get("data", {}).get("zhCN")
                if zh_url:
                    pdf_resp = requests.get(zh_url, headers=headers, timeout=120)
                    pdf_resp.raise_for_status()
                    zh_pdf.parent.mkdir(parents=True, exist_ok=True)
                    zh_pdf.write_bytes(pdf_resp.content)
                    conn = get_connection()
                    try:
                        conn.execute(
                            "UPDATE papers SET pdf_zh_path = ? WHERE id = ?",
                            (pdf_path, paper_id),
                        )
                        conn.commit()
                    finally:
                        conn.close()
                    yield _sse(
                        {
                            "step": "pdf_zh",
                            "status": "done",
                            "msg": f"中文 PDF 下载完成 ({len(pdf_resp.content) // 1024}KB)",
                        }
                    )
                else:
                    yield _sse(
                        {
                            "step": "pdf_zh",
                            "status": "warn",
                            "msg": "该论文暂无中文翻译（hjfy.top 未收录）",
                        }
                    )
            except Exception as e:
                yield _sse(
                    {
                        "step": "pdf_zh",
                        "status": "warn",
                        "msg": f"中文 PDF 获取失败: {e}",
                    }
                )

        # ── Step 4: 生成笔记 ──
        conn = get_connection()
        try:
            existing_note = conn.execute(
                "SELECT id FROM notes WHERE paper_id = ?", (paper_id,)
            ).fetchone()
        finally:
            conn.close()

        if existing_note:
            yield _sse(
                {"step": "note", "status": "skip", "msg": "笔记已存在，跳过"}
            )
        elif not GENAI_AVAILABLE:
            yield _sse(
                {
                    "step": "note",
                    "status": "warn",
                    "msg": "google-genai 未安装，跳过笔记生成",
                }
            )
        elif not en_pdf.exists():
            yield _sse(
                {
                    "step": "note",
                    "status": "warn",
                    "msg": "原文 PDF 不存在，跳过笔记生成",
                }
            )
        else:
            yield _sse(
                {
                    "step": "note",
                    "status": "working",
                    "msg": "正在生成笔记…（AI 生成中）",
                }
            )
            try:
                rate_limiter = get_rate_limiter()
                client = get_client()
                genai_types = get_types()
                rate_limiter.acquire()
                pdf_bytes = en_pdf.read_bytes()
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
                chunks = []
                for chunk in client.models.generate_content_stream(
                    model="gemini-3-pro-preview",
                    contents=contents,
                    config=config,
                ):
                    if chunk.text:
                        chunks.append(chunk.text)
                        if len(chunks) % 10 == 0:
                            yield _sse(
                                {
                                    "step": "note",
                                    "status": "working",
                                    "msg": f"正在生成笔记…（已生成 {sum(len(c) for c in chunks)} 字符）",
                                }
                            )

                full_text = "".join(chunks)
                note_path = stem_rel + ".md"
                note_file = NOTE_DIR / note_path
                note_file.parent.mkdir(parents=True, exist_ok=True)
                note_file.write_text(full_text, encoding="utf-8")

                conn = get_connection()
                try:
                    conn.execute(
                        "INSERT INTO notes (paper_id, title, file_path) VALUES (?, ?, ?)",
                        (paper_id, "默认笔记", note_path),
                    )
                    conn.commit()
                finally:
                    conn.close()

                yield _sse(
                    {
                        "step": "note",
                        "status": "done",
                        "msg": f"笔记生成完成（{len(full_text)} 字符）",
                    }
                )
            except Exception as e:
                yield _sse(
                    {
                        "step": "note",
                        "status": "warn",
                        "msg": f"笔记生成失败: {e}",
                    }
                )

        # ── Step 5: 生成插图 ──
        conn = get_connection()
        try:
            existing_img = conn.execute(
                "SELECT id FROM images WHERE paper_id = ?", (paper_id,)
            ).fetchone()
        finally:
            conn.close()

        if existing_img:
            yield _sse(
                {"step": "image", "status": "skip", "msg": "插图已存在，跳过"}
            )
        elif not GENAI_AVAILABLE:
            yield _sse(
                {
                    "step": "image",
                    "status": "warn",
                    "msg": "google-genai 未安装，跳过插图生成",
                }
            )
        elif not en_pdf.exists():
            yield _sse(
                {
                    "step": "image",
                    "status": "warn",
                    "msg": "原文 PDF 不存在，跳过插图生成",
                }
            )
        else:
            yield _sse(
                {
                    "step": "image",
                    "status": "working",
                    "msg": "正在生成插图…（AI 生成中）",
                }
            )
            try:
                rate_limiter = get_rate_limiter()
                client = get_client()
                genai_types = get_types()
                rate_limiter.acquire()
                pdf_bytes = en_pdf.read_bytes()
                img_contents = [
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
                img_config = genai_types.GenerateContentConfig(
                    image_config=genai_types.ImageConfig(
                        aspect_ratio="4:3", image_size="1K"
                    ),
                    response_modalities=["IMAGE", "TEXT"],
                )
                image_saved = False
                MAX_RETRIES = 3
                for attempt in range(1, MAX_RETRIES + 1):
                    text_chunks = []
                    for chunk in client.models.generate_content_stream(
                        model="gemini-3-pro-image-preview",
                        contents=img_contents,
                        config=img_config,
                    ):
                        if chunk.parts is None:
                            continue
                        part = chunk.parts[0]
                        if part.inline_data and part.inline_data.data:
                            inline_data = part.inline_data
                            file_ext = (
                                mimetypes.guess_extension(inline_data.mime_type)
                                or ".png"
                            )
                            img_path = stem_rel + file_ext
                            out_file = IMAGE_EN_DIR / img_path
                            out_file.parent.mkdir(parents=True, exist_ok=True)
                            out_file.write_bytes(inline_data.data)
                            image_saved = True

                            conn = get_connection()
                            try:
                                conn.execute(
                                    "INSERT INTO images (paper_id, title, file_path) VALUES (?, ?, ?)",
                                    (paper_id, "默认插图", img_path),
                                )
                                conn.commit()
                            finally:
                                conn.close()
                            break
                        elif chunk.text:
                            text_chunks.append(chunk.text)

                    if image_saved:
                        break
                    if attempt < MAX_RETRIES:
                        received_text = "".join(text_chunks).strip()
                        if received_text:
                            img_contents.append(
                                genai_types.Content(
                                    role="model",
                                    parts=[
                                        genai_types.Part.from_text(
                                            text=received_text
                                        ),
                                    ],
                                )
                            )
                        img_contents.append(
                            genai_types.Content(
                                role="user",
                                parts=[
                                    genai_types.Part.from_text(
                                        text="请直接生成图片，不要只回复文字。"
                                    ),
                                ],
                            )
                        )
                        yield _sse(
                            {
                                "step": "image",
                                "status": "working",
                                "msg": f"插图生成重试 ({attempt}/{MAX_RETRIES})…",
                            }
                        )

                if image_saved:
                    yield _sse(
                        {"step": "image", "status": "done", "msg": "插图生成完成"}
                    )
                else:
                    yield _sse(
                        {
                            "step": "image",
                            "status": "warn",
                            "msg": f"重试 {MAX_RETRIES} 次后仍未生成插图",
                        }
                    )
            except Exception as e:
                yield _sse(
                    {
                        "step": "image",
                        "status": "warn",
                        "msg": f"插图生成失败: {e}",
                    }
                )

        yield _sse(
            {
                "step": "finish",
                "status": "done",
                "msg": "导入完成！",
                "paper_id": paper_id,
            }
        )

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(data: dict) -> str:
    """将字典格式化为 SSE data 行。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ────────── 别名提取 ──────────

_ALIAS_PROMPT = """# Role
You are an expert in academic literature data extraction. Your task is to identify and extract the "Alias" (or acronym) of the primary method, model, system, or dataset proposed by the authors in the provided paper text.

# Definitions
- Alias: A short, memorable name or acronym created by the authors for their specific contribution (e.g., "YOLO", "BERT", "ResNet").

# Extraction Rules
1. Target only the authors' own proposal. Do NOT extract the names of baseline models, prior works, or evaluation metrics mentioned in the text.
2. Look for keywords such as "we propose [Alias]", "named [Alias]", "called [Alias]", "referred to as [Alias]", or acronyms defined in parentheses immediately following a capitalized method name.
3. If the authors did not give their method a specific alias/acronym, output `null` for both fields. Do NOT invent or guess an acronym from the title.

# Output Format
Provide the result strictly in the following JSON format, without any markdown formatting or explanations:
{
  "alias": "The short name/acronym (or null)",
  "full_name": "The full spelled-out name of the alias (or null)",
  "evidence": "The exact sentence from the text proving this alias belongs to the proposed method (or null)"
}

# Paper Text:
"""


def _extract_alias(en_pdf: Path) -> tuple:
    """从 PDF 第一页提取论文别名。返回 (alias, alias_full) 或 (None, None)。"""
    if not GENAI_AVAILABLE or not en_pdf.exists():
        return None, None

    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None, None

    try:
        doc = fitz.open(str(en_pdf))
        first_page_text = doc[0].get_text() if len(doc) > 0 else ""
        doc.close()
    except Exception:
        return None, None

    if not first_page_text.strip():
        return None, None

    try:
        rate_limiter = get_rate_limiter()
        client = get_client()
        genai_types = get_types()
        rate_limiter.acquire()

        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=_ALIAS_PROMPT + first_page_text,
            config=genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(thinking_level="minimal"),
            ),
        )
        text = (response.text or "").strip()
        # 清理可能的 markdown 代码块包裹
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        result = json.loads(text)
        alias = result.get("alias")
        full_name = result.get("full_name")
        # 忽略字面量 "null"
        if alias == "null" or alias is None:
            alias = None
        if full_name == "null" or full_name is None:
            full_name = None
        return alias, full_name
    except Exception:
        return None, None


@bp.route("/api/papers/<int:paper_id>/extract-alias", methods=["POST"])
def api_extract_alias(paper_id):
    """手动触发别名提取。"""
    conn = get_connection()
    try:
        paper = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if not paper:
            return jsonify({"error": "论文不存在"}), 404

        en_pdf = PDF_DIR / paper["pdf_path"]
        if not en_pdf.exists():
            return jsonify({"error": "英文 PDF 不存在，无法提取别名"}), 404

        alias, alias_full = _extract_alias(en_pdf)
        conn.execute(
            "UPDATE papers SET alias = ?, alias_full = ? WHERE id = ?",
            (alias, alias_full, paper_id),
        )
        conn.commit()
        status = "ok" if (alias or alias_full) else "empty"
        return jsonify({"status": status, "alias": alias, "alias_full": alias_full})
    finally:
        conn.close()


# ────────── 文件夹管理 ──────────


@bp.route("/api/folders", methods=["POST"])
def api_create_folder():
    """在 pdfs/ 下创建新文件夹。"""
    data = request.get_json() or {}
    parent = data.get("parent", "").strip()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "文件夹名称不能为空"}), 400

    # 安全性检查
    if "/" in name or "\\" in name or name in (".", ".."):
        return jsonify({"error": "文件夹名称非法"}), 400

    folder_path = PDF_DIR / parent / name if parent else PDF_DIR / name
    try:
        folder_path.resolve().relative_to(PDF_DIR.resolve())
    except ValueError:
        abort(403)

    if folder_path.exists():
        return jsonify({"error": f"文件夹已存在: {name}"}), 409

    folder_path.mkdir(parents=True, exist_ok=True)
    rel = folder_path.relative_to(PDF_DIR).as_posix()
    return jsonify({"success": True, "path": rel, "name": name})


@bp.route("/api/folders/rename", methods=["POST"])
def api_rename_folder():
    """重命名文件夹，同步更新所有关联论文的路径。"""
    data = request.get_json() or {}
    old_path = data.get("old_path", "").strip()
    new_name = data.get("new_name", "").strip()

    if not old_path or not new_name:
        return jsonify({"error": "参数缺失"}), 400
    if "/" in new_name or "\\" in new_name or new_name in (".", ".."):
        return jsonify({"error": "文件夹名称非法"}), 400

    old_dir = PDF_DIR / old_path
    try:
        old_dir.resolve().relative_to(PDF_DIR.resolve())
    except ValueError:
        abort(403)
    if not old_dir.is_dir():
        return jsonify({"error": "源文件夹不存在"}), 404

    parent = old_dir.parent
    new_dir = parent / new_name
    if new_dir.exists():
        return jsonify({"error": f"目标已存在: {new_name}"}), 409

    db = get_db()
    old_rel = old_dir.relative_to(PDF_DIR).as_posix()
    new_rel = new_dir.relative_to(PDF_DIR).as_posix()

    try:
        # 重命名物理目录（pdfs, pdfs_zh, notes, images, images_zh）
        for base in [PDF_DIR, PDF_ZH_DIR, NOTE_DIR, IMAGE_EN_DIR, IMAGE_ZH_DIR]:
            src = base / old_path
            if src.is_dir():
                dst = base / new_rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))

        # 更新数据库中所有以 old_rel 开头的论文路径
        papers = db.execute(
            "SELECT * FROM papers WHERE folder = ? OR folder LIKE ?",
            (old_rel, old_rel + "/%"),
        ).fetchall()

        for paper in papers:
            new_folder = new_rel + paper["folder"][len(old_rel):]
            new_pdf = new_rel + paper["pdf_path"][len(old_rel):]
            new_pdf_zh = None
            if paper["pdf_zh_path"]:
                new_pdf_zh = new_rel + paper["pdf_zh_path"][len(old_rel):]

            db.execute(
                'UPDATE papers SET folder = ?, pdf_path = ?, pdf_zh_path = ?, updated_at = datetime("now") WHERE id = ?',
                (new_folder, new_pdf, new_pdf_zh, paper["id"]),
            )

            # 更新笔记路径
            notes = db.execute("SELECT * FROM notes WHERE paper_id = ?", (paper["id"],)).fetchall()
            for note in notes:
                if note["file_path"].startswith(old_rel):
                    new_note_path = new_rel + note["file_path"][len(old_rel):]
                    db.execute("UPDATE notes SET file_path = ? WHERE id = ?", (new_note_path, note["id"]))

            # 更新图片路径
            images = db.execute("SELECT * FROM images WHERE paper_id = ?", (paper["id"],)).fetchall()
            for img in images:
                new_img_path = new_rel + img["file_path"][len(old_rel):] if img["file_path"].startswith(old_rel) else img["file_path"]
                new_img_zh = None
                if img["file_zh_path"] and img["file_zh_path"].startswith(old_rel):
                    new_img_zh = new_rel + img["file_zh_path"][len(old_rel):]
                elif img["file_zh_path"]:
                    new_img_zh = img["file_zh_path"]
                db.execute(
                    "UPDATE images SET file_path = ?, file_zh_path = ? WHERE id = ?",
                    (new_img_path, new_img_zh, img["id"]),
                )

        db.commit()
    except Exception as e:
        return jsonify({"error": f"重命名失败: {e}"}), 500

    return jsonify({"success": True, "old_path": old_rel, "new_path": new_rel})


@bp.route("/api/folders/move", methods=["POST"])
def api_move_folder():
    """移动文件夹到新的父文件夹下，同步更新所有关联论文路径。"""
    data = request.get_json() or {}
    src_path = data.get("src_path", "").strip()       # 例 "Framework/Sub"
    dest_parent = data.get("dest_parent", "").strip()  # 例 "Other" 或 "" (根)

    if not src_path:
        return jsonify({"error": "参数缺失"}), 400

    src_dir = PDF_DIR / src_path
    try:
        src_dir.resolve().relative_to(PDF_DIR.resolve())
    except ValueError:
        abort(403)
    if not src_dir.is_dir():
        return jsonify({"error": "源文件夹不存在"}), 404

    folder_name = src_dir.name
    dest_dir = PDF_DIR / dest_parent / folder_name if dest_parent else PDF_DIR / folder_name

    try:
        dest_dir.resolve().relative_to(PDF_DIR.resolve())
    except ValueError:
        abort(403)

    old_rel = src_dir.relative_to(PDF_DIR).as_posix()
    new_rel = dest_dir.relative_to(PDF_DIR).as_posix()

    if old_rel == new_rel:
        return jsonify({"error": "源路径与目标相同"}), 400

    # 不能把文件夹移到自身内部
    if new_rel.startswith(old_rel + "/"):
        return jsonify({"error": "不能将文件夹移动到自身内部"}), 400

    if dest_dir.exists():
        return jsonify({"error": f"目标已存在: {new_rel}"}), 409

    db = get_db()

    try:
        # 移动物理目录（pdfs, pdfs_zh, notes, images, images_zh）
        for base in [PDF_DIR, PDF_ZH_DIR, NOTE_DIR, IMAGE_EN_DIR, IMAGE_ZH_DIR]:
            src = base / old_rel
            if src.is_dir():
                dst = base / new_rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))

        # 更新数据库中所有以 old_rel 开头的论文路径
        papers = db.execute(
            "SELECT * FROM papers WHERE folder = ? OR folder LIKE ?",
            (old_rel, old_rel + "/%"),
        ).fetchall()

        for paper in papers:
            new_folder = new_rel + paper["folder"][len(old_rel):]
            new_pdf = new_rel + paper["pdf_path"][len(old_rel):]
            new_pdf_zh = None
            if paper["pdf_zh_path"]:
                new_pdf_zh = new_rel + paper["pdf_zh_path"][len(old_rel):]

            db.execute(
                'UPDATE papers SET folder = ?, pdf_path = ?, pdf_zh_path = ?, updated_at = datetime("now") WHERE id = ?',
                (new_folder, new_pdf, new_pdf_zh, paper["id"]),
            )

            # 更新笔记路径
            notes = db.execute("SELECT * FROM notes WHERE paper_id = ?", (paper["id"],)).fetchall()
            for note in notes:
                if note["file_path"].startswith(old_rel):
                    new_note_path = new_rel + note["file_path"][len(old_rel):]
                    db.execute("UPDATE notes SET file_path = ? WHERE id = ?", (new_note_path, note["id"]))

            # 更新图片路径
            images = db.execute("SELECT * FROM images WHERE paper_id = ?", (paper["id"],)).fetchall()
            for img in images:
                new_img_path = new_rel + img["file_path"][len(old_rel):] if img["file_path"].startswith(old_rel) else img["file_path"]
                new_img_zh = None
                if img["file_zh_path"] and img["file_zh_path"].startswith(old_rel):
                    new_img_zh = new_rel + img["file_zh_path"][len(old_rel):]
                elif img["file_zh_path"]:
                    new_img_zh = img["file_zh_path"]
                db.execute(
                    "UPDATE images SET file_path = ?, file_zh_path = ? WHERE id = ?",
                    (new_img_path, new_img_zh, img["id"]),
                )

        db.commit()
    except Exception as e:
        return jsonify({"error": f"移动失败: {e}"}), 500

    return jsonify({"success": True, "old_path": old_rel, "new_path": new_rel})


@bp.route("/api/folders/delete", methods=["POST"])
def api_delete_folder():
    """删除文件夹及其所有内容（论文、笔记、图片等）。"""
    data = request.get_json() or {}
    folder_path = data.get("path", "").strip()

    if not folder_path:
        return jsonify({"error": "路径不能为空"}), 400

    target = PDF_DIR / folder_path
    try:
        target.resolve().relative_to(PDF_DIR.resolve())
    except ValueError:
        abort(403)
    if not target.is_dir():
        return jsonify({"error": "文件夹不存在"}), 404

    db = get_db()

    try:
        # 删除文件夹中的所有论文记录及关联数据
        papers = db.execute(
            "SELECT id FROM papers WHERE folder = ? OR folder LIKE ?",
            (folder_path, folder_path + "/%"),
        ).fetchall()

        for paper in papers:
            pid = paper["id"]
            db.execute("DELETE FROM notes WHERE paper_id = ?", (pid,))
            db.execute("DELETE FROM images WHERE paper_id = ?", (pid,))
            db.execute("DELETE FROM chat_sessions WHERE paper_id = ?", (pid,))
            db.execute("DELETE FROM chat_messages WHERE session_id IN (SELECT id FROM chat_sessions WHERE paper_id = ?)", (pid,))
            db.execute("DELETE FROM papers WHERE id = ?", (pid,))

        # 删除物理文件夹
        for base in [PDF_DIR, PDF_ZH_DIR, NOTE_DIR, IMAGE_EN_DIR, IMAGE_ZH_DIR]:
            d = base / folder_path
            if d.is_dir():
                shutil.rmtree(str(d), ignore_errors=True)

        db.commit()
    except Exception as e:
        return jsonify({"error": f"删除失败: {e}"}), 500

    return jsonify({"success": True})


# ────────── 论文删除与重命名 ──────────


@bp.route("/api/papers/<int:paper_id>", methods=["DELETE"])
def api_delete_paper(paper_id):
    """删除论文及其所有关联文件。"""
    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    try:
        # 删除物理文件
        pdf_path = PDF_DIR / paper["pdf_path"]
        if pdf_path.exists():
            pdf_path.unlink()

        if paper["pdf_zh_path"]:
            pdf_zh = PDF_ZH_DIR / paper["pdf_zh_path"]
            if pdf_zh.exists():
                pdf_zh.unlink()

        # 删除笔记文件
        notes = db.execute("SELECT * FROM notes WHERE paper_id = ?", (paper_id,)).fetchall()
        for note in notes:
            fp = NOTE_DIR / note["file_path"]
            if fp.exists():
                fp.unlink()

        # 删除图片文件
        images = db.execute("SELECT * FROM images WHERE paper_id = ?", (paper_id,)).fetchall()
        for img in images:
            fp = IMAGE_EN_DIR / img["file_path"]
            if fp.exists():
                fp.unlink()
            if img["file_zh_path"]:
                fp_zh = IMAGE_ZH_DIR / img["file_zh_path"]
                if fp_zh.exists():
                    fp_zh.unlink()

        # 删除数据库记录
        db.execute("DELETE FROM chat_messages WHERE session_id IN (SELECT id FROM chat_sessions WHERE paper_id = ?)", (paper_id,))
        db.execute("DELETE FROM chat_sessions WHERE paper_id = ?", (paper_id,))
        db.execute("DELETE FROM notes WHERE paper_id = ?", (paper_id,))
        db.execute("DELETE FROM images WHERE paper_id = ?", (paper_id,))
        db.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
        db.commit()
    except Exception as e:
        return jsonify({"error": f"删除失败: {e}"}), 500

    return jsonify({"success": True})


@bp.route("/api/papers/<int:paper_id>/rename", methods=["POST"])
def api_rename_paper(paper_id):
    """重命名论文 PDF 文件及其关联文件。"""
    db = get_db()
    paper = db.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if not paper:
        return jsonify({"error": "论文不存在"}), 404

    data = request.get_json() or {}
    new_name = data.get("new_name", "").strip()
    if not new_name:
        return jsonify({"error": "名称不能为空"}), 400

    # 去除 .pdf 后缀（如果有的话）
    if new_name.lower().endswith(".pdf"):
        new_name = new_name[:-4]

    old_pdf_path = paper["pdf_path"]
    folder = paper["folder"]
    old_stem = Path(old_pdf_path).stem

    new_pdf_filename = new_name + ".pdf"
    new_pdf_path = f"{folder}/{new_pdf_filename}" if folder else new_pdf_filename

    if old_pdf_path == new_pdf_path:
        return jsonify({"error": "名称未改变"}), 400
    if (PDF_DIR / new_pdf_path).exists():
        return jsonify({"error": f"同名文件已存在: {new_name}"}), 409

    try:
        # 重命名英文 PDF
        src = PDF_DIR / old_pdf_path
        dst = PDF_DIR / new_pdf_path
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)

        # 重命名中文 PDF
        if paper["pdf_zh_path"]:
            src_zh = PDF_ZH_DIR / paper["pdf_zh_path"]
            dst_zh = PDF_ZH_DIR / new_pdf_path
            if src_zh.exists():
                dst_zh.parent.mkdir(parents=True, exist_ok=True)
                src_zh.rename(dst_zh)

        # 重命名笔记文件
        notes = db.execute("SELECT * FROM notes WHERE paper_id = ?", (paper_id,)).fetchall()
        for note in notes:
            old_note = note["file_path"]
            note_filename = Path(old_note).name
            # 替换论文 stem 前缀
            if note_filename.startswith(old_stem):
                new_note_filename = new_name + note_filename[len(old_stem):]
            else:
                new_note_filename = note_filename
            new_note_path = f"{folder}/{new_note_filename}" if folder else new_note_filename
            src_n = NOTE_DIR / old_note
            dst_n = NOTE_DIR / new_note_path
            if src_n.exists():
                dst_n.parent.mkdir(parents=True, exist_ok=True)
                src_n.rename(dst_n)
            db.execute("UPDATE notes SET file_path = ? WHERE id = ?", (new_note_path, note["id"]))

        # 重命名图片文件
        images = db.execute("SELECT * FROM images WHERE paper_id = ?", (paper_id,)).fetchall()
        for img in images:
            old_img = img["file_path"]
            img_filename = Path(old_img).name
            if img_filename.startswith(old_stem):
                new_img_filename = new_name + img_filename[len(old_stem):]
            else:
                new_img_filename = img_filename
            new_img_path = f"{folder}/{new_img_filename}" if folder else new_img_filename
            src_i = IMAGE_EN_DIR / old_img
            dst_i = IMAGE_EN_DIR / new_img_path
            if src_i.exists():
                dst_i.parent.mkdir(parents=True, exist_ok=True)
                src_i.rename(dst_i)

            new_img_zh_path = None
            if img["file_zh_path"]:
                old_zh = img["file_zh_path"]
                zh_filename = Path(old_zh).name
                if zh_filename.startswith(old_stem):
                    new_zh_filename = new_name + zh_filename[len(old_stem):]
                else:
                    new_zh_filename = zh_filename
                new_img_zh_path = f"{folder}/{new_zh_filename}" if folder else new_zh_filename
                src_iz = IMAGE_ZH_DIR / old_zh
                dst_iz = IMAGE_ZH_DIR / new_img_zh_path
                if src_iz.exists():
                    dst_iz.parent.mkdir(parents=True, exist_ok=True)
                    src_iz.rename(dst_iz)

            db.execute(
                "UPDATE images SET file_path = ?, file_zh_path = ? WHERE id = ?",
                (new_img_path, new_img_zh_path, img["id"]),
            )

        # 更新论文记录
        new_pdf_zh = new_pdf_path if paper["pdf_zh_path"] else None
        db.execute(
            'UPDATE papers SET title = ?, pdf_path = ?, pdf_zh_path = ?, updated_at = datetime("now") WHERE id = ?',
            (new_name, new_pdf_path, new_pdf_zh, paper_id),
        )
        db.commit()
    except Exception as e:
        return jsonify({"error": f"重命名失败: {e}"}), 500

    return jsonify({"success": True, "new_name": new_name})
