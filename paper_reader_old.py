"""
论文阅读器 —— 集成 PDF 查看、Markdown 笔记编辑、中英双语插图查看、AI 生成笔记/插图
"""

import json
import mimetypes
import os
import re
import shutil
import threading
import time
from pathlib import Path

import requests
from flask import (
    Flask, jsonify, send_from_directory,
    abort, request, Response, stream_with_context,
)

# ========== AI 生成依赖（可选） ==========
try:
    from google import genai
    from google.genai import types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
# =========================================

app = Flask(__name__,
            static_folder='frontend/dist',
            static_url_path='')
BASE_DIR = Path(__file__).parent

# ========== 可配置：文件夹路径 ==========
PDF_DIR = BASE_DIR / "pdfs"            # PDF 论文目录
PDF_ZH_DIR = BASE_DIR / "pdfs_zh"      # 中文 PDF 目录
NOTE_DIR = BASE_DIR / "notes"          # Markdown 笔记目录
IMAGE_EN_DIR = BASE_DIR / "images"     # 英文插图目录
IMAGE_ZH_DIR = BASE_DIR / "images_zh"  # 中文插图目录
# =======================================

IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]

# ========== Gemini AI 客户端 ==========
if GENAI_AVAILABLE:
    _genai_client = genai.Client(
        api_key="AIzaSyDeGkPec5WnFWq7HDqZwMbLcnuLZmWL0B4",
    )

    class _RateLimiter:
        """简单的令牌桶限速器，保证每分钟不超过指定数量请求。"""
        def __init__(self, interval: float):
            self._interval = interval
            self._lock = threading.Lock()
            self._last = 0.0

        def acquire(self):
            with self._lock:
                now = time.monotonic()
                wait = self._interval - (now - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()

    _rate_limiter = _RateLimiter(60.0 / 5)  # 5 次/分钟
# ======================================


def find_image(img_dir: Path, stem_path: str):
    """尝试不同扩展名，返回第一个存在的图片文件的完整相对路径，否则返回 None"""
    for ext in IMAGE_EXTENSIONS:
        candidate = img_dir / (stem_path + ext)
        if candidate.exists():
            return stem_path + ext
    return None


def build_paper_tree(directory: Path, base: Path) -> dict:
    """递归构建论文目录树"""
    node = {
        "name": directory.name if directory != base else "论文库",
        "type": "dir",
        "path": directory.relative_to(base).as_posix() if directory != base else "",
        "children": [],
    }
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return node

    for entry in entries:
        if entry.is_dir():
            sub = build_paper_tree(entry, base)
            if sub["children"]:
                node["children"].append(sub)
        elif entry.is_file() and entry.suffix.lower() == ".pdf":
            rel = entry.relative_to(base).as_posix()
            stem_rel = rel.rsplit(".", 1)[0]  # 去掉 .pdf

            has_note = (NOTE_DIR / (stem_rel + ".md")).exists()
            has_pdf_zh = (PDF_ZH_DIR / rel).exists()
            has_image_en = find_image(IMAGE_EN_DIR, stem_rel) is not None
            has_image_zh = find_image(IMAGE_ZH_DIR, stem_rel) is not None

            node["children"].append({
                "name": entry.stem,
                "type": "file",
                "path": rel,
                "stem": stem_rel,
                "hasNote": has_note,
                "hasPdfZh": has_pdf_zh,
                "hasImageEn": has_image_en,
                "hasImageZh": has_image_zh,
            })
    return node


# ────────── 页面 ──────────

@app.route("/")
def index():
    return app.send_static_file("index.html")

# 对于 SPA 客户端路由，捕获未匹配的路径
@app.errorhandler(404)
def fallback(e):
    return app.send_static_file("index.html")


# ────────── API ──────────

@app.route("/api/tree")
def api_tree():
    PDF_DIR.mkdir(exist_ok=True)
    tree = build_paper_tree(PDF_DIR, PDF_DIR)
    return jsonify(tree)


@app.route("/api/pdf/<lang>/<path:filepath>")
def api_pdf(lang, filepath):
    if lang not in {"en", "zh"}:
        abort(404)

    pdf_root = PDF_ZH_DIR if lang == "zh" else PDF_DIR
    target = (pdf_root / filepath).resolve()
    try:
        target.relative_to(pdf_root.resolve())
    except ValueError:
        abort(403)
    if not target.exists():
        abort(404)
    return send_from_directory(pdf_root, filepath)


@app.route("/api/pdf-exists/<lang>/<path:filepath>")
def api_pdf_exists(lang, filepath):
    if lang not in {"en", "zh"}:
        return jsonify({"exists": False})

    pdf_root = PDF_ZH_DIR if lang == "zh" else PDF_DIR
    target = (pdf_root / filepath).resolve()
    try:
        target.relative_to(pdf_root.resolve())
    except ValueError:
        return jsonify({"exists": False})
    return jsonify({"exists": target.exists() and target.is_file()})


@app.route("/api/note/<path:filepath>", methods=["GET"])
def api_get_note(filepath):
    """获取笔记内容。filepath 为不含扩展名的相对路径"""
    note_path = NOTE_DIR / (filepath + ".md")
    if not note_path.exists():
        return jsonify({"content": "", "exists": False})
    try:
        content = note_path.read_text(encoding="utf-8")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"content": content, "exists": True})


@app.route("/api/note/<path:filepath>", methods=["POST"])
def api_save_note(filepath):
    """保存笔记内容。filepath 为不含扩展名的相对路径"""
    note_path = NOTE_DIR / (filepath + ".md")
    note_path.parent.mkdir(parents=True, exist_ok=True)
    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"error": "Missing content"}), 400
    try:
        note_path.write_text(data["content"], encoding="utf-8")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"success": True})


@app.route("/api/image/<lang>/<path:filepath>")
def api_image(lang, filepath):
    """服务图片文件。lang 为 zh/en，filepath 为不含扩展名的相对路径"""
    img_dir = IMAGE_ZH_DIR if lang == "zh" else IMAGE_EN_DIR
    actual_file = find_image(img_dir, filepath)
    if actual_file is None:
        abort(404)
    target = (img_dir / actual_file).resolve()
    try:
        target.relative_to(img_dir.resolve())
    except ValueError:
        abort(403)
    return send_from_directory(img_dir, actual_file)


# ────────── AI 生成 & 删除 API ──────────

@app.route("/api/generate-note/<path:filepath>", methods=["POST"])
def api_generate_note(filepath):
    """使用 Gemini 为 PDF 生成讲解笔记，以 SSE 流式返回文本片段。"""
    if not GENAI_AVAILABLE:
        return jsonify({"error": "google-genai 未安装，请 pip install google-genai"}), 500

    pdf_path = PDF_DIR / (filepath + ".pdf")
    if not pdf_path.exists():
        return jsonify({"error": "PDF 文件不存在"}), 404

    note_path = NOTE_DIR / (filepath + ".md")
    if note_path.exists():
        return jsonify({"error": "笔记已存在，请先删除再重新生成"}), 409

    def stream():
        try:
            _rate_limiter.acquire()
            pdf_bytes = pdf_path.read_bytes()
            contents = [
                genai_types.Content(role="user", parts=[
                    genai_types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    genai_types.Part.from_text(text="讲解这篇论文，用中文，附必要的公式或例子"),
                ]),
            ]
            config = genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(thinking_level="HIGH"),
            )

            chunks = []
            for chunk in _genai_client.models.generate_content_stream(
                model="gemini-3-pro-preview",
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    chunks.append(chunk.text)
                    yield f"data: {json.dumps({'type': 'chunk', 'text': chunk.text})}\n\n"

            full_text = "".join(chunks)
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(full_text, encoding="utf-8")
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/generate-image/<path:filepath>", methods=["POST"])
def api_generate_image(filepath):
    """使用 Gemini 为 PDF 生成论文插图，含自动重试。"""
    if not GENAI_AVAILABLE:
        return jsonify({"error": "google-genai 未安装，请 pip install google-genai"}), 500

    pdf_path = PDF_DIR / (filepath + ".pdf")
    if not pdf_path.exists():
        return jsonify({"error": "PDF 文件不存在"}), 404

    if find_image(IMAGE_EN_DIR, filepath) is not None:
        return jsonify({"error": "插图已存在，请先删除再重新生成"}), 409

    MAX_RETRIES = 5
    try:
        _rate_limiter.acquire()
        pdf_bytes = pdf_path.read_bytes()

        contents = [
            genai_types.Content(role="user", parts=[
                genai_types.Part.from_text(
                    text="为这篇论文绘制一张清晰易懂的，科研论文配图用来辅助讲解这篇论文的核心创新点"
                ),
                genai_types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            ]),
        ]
        config = genai_types.GenerateContentConfig(
            image_config=genai_types.ImageConfig(aspect_ratio="4:3", image_size="1K"),
            response_modalities=["IMAGE", "TEXT"],
        )

        for attempt in range(1, MAX_RETRIES + 1):
            text_chunks = []
            image_saved = False

            for chunk in _genai_client.models.generate_content_stream(
                model="gemini-3-pro-image-preview",
                contents=contents,
                config=config,
            ):
                if chunk.parts is None:
                    continue
                part = chunk.parts[0]
                if part.inline_data and part.inline_data.data:
                    inline_data = part.inline_data
                    file_ext = mimetypes.guess_extension(inline_data.mime_type) or ".png"
                    out_path = IMAGE_EN_DIR / (filepath + file_ext)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(inline_data.data)
                    image_saved = True
                elif chunk.text:
                    text_chunks.append(chunk.text)

            if image_saved:
                return jsonify({"success": True})

            # 未获得图片 → 重试
            if attempt < MAX_RETRIES:
                received_text = "".join(text_chunks).strip()
                if received_text:
                    contents.append(genai_types.Content(role="model", parts=[
                        genai_types.Part.from_text(text=received_text),
                    ]))
                contents.append(genai_types.Content(role="user", parts=[
                    genai_types.Part.from_text(text="请直接生成图片，不要只回复文字。"),
                ]))

        return jsonify({"error": f"重试 {MAX_RETRIES} 次后仍未生成图片"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete-note/<path:filepath>", methods=["POST"])
def api_delete_note(filepath):
    """删除指定笔记文件。"""
    note_path = NOTE_DIR / (filepath + ".md")
    if not note_path.exists():
        return jsonify({"error": "笔记不存在"}), 404
    try:
        note_path.unlink()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fetch-zh-pdf/<path:filepath>", methods=["POST"])
def api_fetch_zh_pdf(filepath):
    """通过 arXiv ID 从 hjfy.top 下载中文翻译 PDF。
    请求 body: {"arxiv_id": "2406.12345"} 或 {"arxiv_id": "https://arxiv.org/abs/2406.12345"}
    """
    pdf_rel = filepath + ".pdf"
    dest_path = PDF_ZH_DIR / pdf_rel
    if dest_path.exists():
        return jsonify({"error": "中文 PDF 已存在"}), 409

    data = request.get_json()
    raw = (data or {}).get("arxiv_id", "").strip()
    if not raw:
        return jsonify({"error": "请提供 arXiv ID"}), 400

    # 从 URL 或纯文本中提取 arXiv ID
    m = re.search(r'(\d{4}\.\d{4,5})(v\d+)?', raw)
    if not m:
        return jsonify({"error": f"无法解析 arXiv ID: {raw}"}), 400
    arxiv_id = m.group(1)  # 不带版本号

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': f'https://hjfy.top/arxiv/{arxiv_id}',
    }
    try:
        resp = requests.get(
            f'https://hjfy.top/api/arxivFiles/{arxiv_id}',
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        api_data = resp.json()
        zh_url = api_data.get('data', {}).get('zhCN')
        if not zh_url:
            return jsonify({"error": "该论文暂无中文翻译（hjfy.top 未收录）"}), 404

        pdf_resp = requests.get(zh_url, headers=headers, timeout=120)
        pdf_resp.raise_for_status()

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(pdf_resp.content)
        return jsonify({"success": True, "size": len(pdf_resp.content)})
    except requests.RequestException as e:
        return jsonify({"error": f"下载失败: {e}"}), 500


@app.route("/api/translate-image/<path:filepath>", methods=["POST"])
def api_translate_image(filepath):
    """将英文插图翻译为中文版本，使用 Gemini 图像生成。"""
    if not GENAI_AVAILABLE:
        return jsonify({"error": "google-genai 未安装"}), 500

    # 找到英文原图
    en_file = find_image(IMAGE_EN_DIR, filepath)
    if en_file is None:
        return jsonify({"error": "英文插图不存在，请先生成英文版"}), 404

    # 检查中文版是否已存在
    if find_image(IMAGE_ZH_DIR, filepath) is not None:
        return jsonify({"error": "中文插图已存在，请先删除再翻译"}), 409

    MAX_RETRIES = 5
    try:
        _rate_limiter.acquire()
        en_path = IMAGE_EN_DIR / en_file
        img_bytes = en_path.read_bytes()
        mime = mimetypes.guess_type(str(en_path))[0] or "image/png"

        contents = [
            genai_types.Content(role="user", parts=[
                genai_types.Part.from_bytes(data=img_bytes, mime_type=mime),
                genai_types.Part.from_text(text="将图改为中文版本，Memory指的是记忆"),
            ]),
        ]
        config = genai_types.GenerateContentConfig(
            image_config=genai_types.ImageConfig(aspect_ratio="4:3", image_size="2K"),
            response_modalities=["IMAGE", "TEXT"],
        )

        for attempt in range(1, MAX_RETRIES + 1):
            text_chunks = []
            image_saved = False

            for chunk in _genai_client.models.generate_content_stream(
                model="gemini-3-pro-image-preview",
                contents=contents,
                config=config,
            ):
                if chunk.parts is None:
                    continue
                part = chunk.parts[0]
                if part.inline_data and part.inline_data.data:
                    inline_data = part.inline_data
                    file_ext = mimetypes.guess_extension(inline_data.mime_type) or ".png"
                    out_path = IMAGE_ZH_DIR / (filepath + file_ext)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(inline_data.data)
                    image_saved = True
                elif chunk.text:
                    text_chunks.append(chunk.text)

            if image_saved:
                return jsonify({"success": True})

            if attempt < MAX_RETRIES:
                received_text = "".join(text_chunks).strip()
                if received_text:
                    contents.append(genai_types.Content(role="model", parts=[
                        genai_types.Part.from_text(text=received_text),
                    ]))
                contents.append(genai_types.Content(role="user", parts=[
                    genai_types.Part.from_text(text="请直接生成中文版图片，不要只回复文字。"),
                ]))

        return jsonify({"error": f"重试 {MAX_RETRIES} 次后仍未生成图片"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete-image/<path:filepath>", methods=["POST"])
def api_delete_image(filepath):
    """删除指定论文的所有语言版本插图。"""
    deleted = []
    for img_dir in [IMAGE_EN_DIR, IMAGE_ZH_DIR]:
        for ext in IMAGE_EXTENSIONS:
            candidate = img_dir / (filepath + ext)
            if candidate.exists():
                try:
                    candidate.unlink()
                    deleted.append(str(candidate.relative_to(BASE_DIR)))
                except Exception:
                    pass
    if not deleted:
        return jsonify({"error": "未找到可删除的图片"}), 404
    return jsonify({"success": True, "deleted": deleted})


# ────────── 导入论文 & 移动论文 API ──────────

@app.route("/api/folders")
def api_folders():
    """列出 pdfs/ 下指定父目录的直接子文件夹。
    Query param: parent (默认为空 = 根目录)
    返回: [{"name": "Framework", "path": "memory/Framework", "hasChildren": true}, ...]
    """
    parent = request.args.get("parent", "").strip()
    target = (PDF_DIR / parent).resolve()
    # 安全检查
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
                children.append({"name": entry.name, "path": rel, "hasChildren": has_sub})
    except PermissionError:
        pass
    return jsonify(children)


@app.route("/api/import-paper", methods=["POST"])
def api_import_paper():
    """通过 arXiv ID 导入论文，使用 SSE 流式返回每步进度。
    body: {"arxiv_id": "2406.12345", "folder": "memory/Framework"}
    """
    data = request.get_json()
    raw = (data or {}).get("arxiv_id", "").strip()
    folder = (data or {}).get("folder", "").strip()

    if not raw:
        return jsonify({"error": "请提供 arXiv ID"}), 400

    # 提取 arXiv ID
    m = re.search(r'(\d{4}\.\d{4,5})(v\d+)?', raw)
    if not m:
        return jsonify({"error": f"无法解析 arXiv ID: {raw}"}), 400
    arxiv_id = m.group(1)

    def stream():
        paper_title = None
        pdf_rel = None  # 相对于 PDF_DIR 的路径 (不含 .pdf)
        stem_rel = None  # 用于 note/image 的相对路径

        # ── Step 1: 获取论文标题（通过 arxiv API） ──
        yield f"data: {json.dumps({'step': 'title', 'status': 'working', 'msg': '正在获取论文信息…'})}\n\n"
        try:
            resp = requests.get(f"http://export.arxiv.org/api/query?id_list={arxiv_id}", timeout=15)
            resp.raise_for_status()
            # 简单解析 XML 标题
            title_match = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.DOTALL)
            if title_match:
                raw_title = title_match.group(1).strip()
                # arxiv API 第一个 <title> 是 "ArXiv Query"，取最后一个
                all_titles = re.findall(r'<title[^>]*>(.*?)</title>', resp.text, re.DOTALL)
                for t in all_titles:
                    t = t.strip()
                    if t and t.lower() != "arxiv query:":
                        raw_title = t
                # 清理标题做文件名
                paper_title = re.sub(r'[\n\r]+', ' ', raw_title).strip()
                paper_title = re.sub(r'\s+', ' ', paper_title)

            if not paper_title:
                paper_title = arxiv_id

            # 清理文件名中的非法字符
            safe_name = re.sub(r'[<>:"/\\|?*]', '', paper_title)[:150].strip()
            if not safe_name:
                safe_name = arxiv_id

            stem_rel = (Path(folder) / safe_name).as_posix() if folder else safe_name
            pdf_rel = stem_rel + ".pdf"

            yield f"data: {json.dumps({'step': 'title', 'status': 'done', 'msg': f'标题: {paper_title}', 'stem': stem_rel})}\n\n"
        except Exception as e:
            safe_name = arxiv_id
            stem_rel = (Path(folder) / safe_name).as_posix() if folder else safe_name
            pdf_rel = stem_rel + ".pdf"
            yield f"data: {json.dumps({'step': 'title', 'status': 'warn', 'msg': f'获取标题失败，使用 ID: {arxiv_id}'})}\n\n"

        # ── Step 2: 下载原文 PDF ──
        en_pdf_path = PDF_DIR / pdf_rel
        if en_pdf_path.exists():
            yield f"data: {json.dumps({'step': 'pdf_en', 'status': 'skip', 'msg': '原文 PDF 已存在，跳过'})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 'pdf_en', 'status': 'working', 'msg': '正在下载原文 PDF…'})}\n\n"
            try:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                r = requests.get(pdf_url, timeout=120, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                })
                r.raise_for_status()
                en_pdf_path.parent.mkdir(parents=True, exist_ok=True)
                en_pdf_path.write_bytes(r.content)
                yield f"data: {json.dumps({'step': 'pdf_en', 'status': 'done', 'msg': f'原文 PDF 下载完成 ({len(r.content)//1024}KB)'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'step': 'pdf_en', 'status': 'error', 'msg': f'原文 PDF 下载失败: {e}'})}\n\n"
                yield f"data: {json.dumps({'step': 'finish', 'status': 'error', 'msg': '无法下载原文 PDF，导入终止'})}\n\n"
                return

        # ── Step 3: 下载中文翻译 PDF ──
        zh_pdf_path = PDF_ZH_DIR / pdf_rel
        if zh_pdf_path.exists():
            yield f"data: {json.dumps({'step': 'pdf_zh', 'status': 'skip', 'msg': '中文 PDF 已存在，跳过'})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 'pdf_zh', 'status': 'working', 'msg': '正在获取中文翻译 PDF…'})}\n\n"
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                    'Referer': f'https://hjfy.top/arxiv/{arxiv_id}',
                }
                resp = requests.get(
                    f'https://hjfy.top/api/arxivFiles/{arxiv_id}',
                    headers=headers, timeout=30,
                )
                resp.raise_for_status()
                api_data = resp.json()
                zh_url = api_data.get('data', {}).get('zhCN')
                if zh_url:
                    pdf_resp = requests.get(zh_url, headers=headers, timeout=120)
                    pdf_resp.raise_for_status()
                    zh_pdf_path.parent.mkdir(parents=True, exist_ok=True)
                    zh_pdf_path.write_bytes(pdf_resp.content)
                    yield f"data: {json.dumps({'step': 'pdf_zh', 'status': 'done', 'msg': f'中文 PDF 下载完成 ({len(pdf_resp.content)//1024}KB)'})}\n\n"
                else:
                    yield f"data: {json.dumps({'step': 'pdf_zh', 'status': 'warn', 'msg': '该论文暂无中文翻译（hjfy.top 未收录）'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'step': 'pdf_zh', 'status': 'warn', 'msg': f'中文 PDF 获取失败: {e}'})}\n\n"

        # ── Step 4: 生成笔记 ──
        note_path = NOTE_DIR / (stem_rel + ".md")
        if note_path.exists():
            yield f"data: {json.dumps({'step': 'note', 'status': 'skip', 'msg': '笔记已存在，跳过'})}\n\n"
        elif not GENAI_AVAILABLE:
            yield f"data: {json.dumps({'step': 'note', 'status': 'warn', 'msg': 'google-genai 未安装，跳过笔记生成'})}\n\n"
        elif not en_pdf_path.exists():
            yield f"data: {json.dumps({'step': 'note', 'status': 'warn', 'msg': '原文 PDF 不存在，跳过笔记生成'})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 'note', 'status': 'working', 'msg': '正在生成笔记…（AI 生成中）'})}\n\n"
            try:
                _rate_limiter.acquire()
                pdf_bytes = en_pdf_path.read_bytes()
                contents = [
                    genai_types.Content(role="user", parts=[
                        genai_types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                        genai_types.Part.from_text(text="讲解这篇论文，用中文，附必要的公式或例子"),
                    ]),
                ]
                config = genai_types.GenerateContentConfig(
                    thinking_config=genai_types.ThinkingConfig(thinking_level="HIGH"),
                )
                chunks = []
                for chunk in _genai_client.models.generate_content_stream(
                    model="gemini-3-pro-preview",
                    contents=contents,
                    config=config,
                ):
                    if chunk.text:
                        chunks.append(chunk.text)
                        # 定期发送进度
                        if len(chunks) % 10 == 0:
                            yield f"data: {json.dumps({'step': 'note', 'status': 'working', 'msg': f'正在生成笔记…（已生成 {sum(len(c) for c in chunks)} 字符）'})}\n\n"

                full_text = "".join(chunks)
                note_path.parent.mkdir(parents=True, exist_ok=True)
                note_path.write_text(full_text, encoding="utf-8")
                yield f"data: {json.dumps({'step': 'note', 'status': 'done', 'msg': f'笔记生成完成（{len(full_text)} 字符）'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'step': 'note', 'status': 'warn', 'msg': f'笔记生成失败: {e}'})}\n\n"

        # ── Step 5: 生成插图 ──
        if find_image(IMAGE_EN_DIR, stem_rel) is not None:
            yield f"data: {json.dumps({'step': 'image', 'status': 'skip', 'msg': '插图已存在，跳过'})}\n\n"
        elif not GENAI_AVAILABLE:
            yield f"data: {json.dumps({'step': 'image', 'status': 'warn', 'msg': 'google-genai 未安装，跳过插图生成'})}\n\n"
        elif not en_pdf_path.exists():
            yield f"data: {json.dumps({'step': 'image', 'status': 'warn', 'msg': '原文 PDF 不存在，跳过插图生成'})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 'image', 'status': 'working', 'msg': '正在生成插图…（AI 生成中）'})}\n\n"
            try:
                _rate_limiter.acquire()
                pdf_bytes = en_pdf_path.read_bytes()
                img_contents = [
                    genai_types.Content(role="user", parts=[
                        genai_types.Part.from_text(
                            text="为这篇论文绘制一张清晰易懂的，科研论文配图用来辅助讲解这篇论文的核心创新点"
                        ),
                        genai_types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                    ]),
                ]
                img_config = genai_types.GenerateContentConfig(
                    image_config=genai_types.ImageConfig(aspect_ratio="4:3", image_size="1K"),
                    response_modalities=["IMAGE", "TEXT"],
                )
                image_saved = False
                MAX_RETRIES = 3
                for attempt in range(1, MAX_RETRIES + 1):
                    text_chunks = []
                    for chunk in _genai_client.models.generate_content_stream(
                        model="gemini-3-pro-image-preview",
                        contents=img_contents,
                        config=img_config,
                    ):
                        if chunk.parts is None:
                            continue
                        part = chunk.parts[0]
                        if part.inline_data and part.inline_data.data:
                            inline_data = part.inline_data
                            file_ext = mimetypes.guess_extension(inline_data.mime_type) or ".png"
                            out_path = IMAGE_EN_DIR / (stem_rel + file_ext)
                            out_path.parent.mkdir(parents=True, exist_ok=True)
                            out_path.write_bytes(inline_data.data)
                            image_saved = True
                            break
                        elif chunk.text:
                            text_chunks.append(chunk.text)
                    if image_saved:
                        break
                    if attempt < MAX_RETRIES:
                        received_text = "".join(text_chunks).strip()
                        if received_text:
                            img_contents.append(genai_types.Content(role="model", parts=[
                                genai_types.Part.from_text(text=received_text),
                            ]))
                        img_contents.append(genai_types.Content(role="user", parts=[
                            genai_types.Part.from_text(text="请直接生成图片，不要只回复文字。"),
                        ]))
                        yield f"data: {json.dumps({'step': 'image', 'status': 'working', 'msg': f'插图生成重试 ({attempt}/{MAX_RETRIES})…'})}\n\n"

                if image_saved:
                    yield f"data: {json.dumps({'step': 'image', 'status': 'done', 'msg': '插图生成完成'})}\n\n"
                else:
                    yield f"data: {json.dumps({'step': 'image', 'status': 'warn', 'msg': f'重试 {MAX_RETRIES} 次后仍未生成插图'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'step': 'image', 'status': 'warn', 'msg': f'插图生成失败: {e}'})}\n\n"

        yield f"data: {json.dumps({'step': 'finish', 'status': 'done', 'msg': '导入完成！', 'stem': stem_rel})}\n\n"

    return Response(
        stream_with_context(stream()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/move-paper", methods=["POST"])
def api_move_paper():
    """移动论文及其关联文件（PDF/笔记/图片）到指定目录。
    body: {"stem": "Framework/SomeTitle", "dest_folder": "memory/Survey"}
    """
    data = request.get_json()
    stem = (data or {}).get("stem", "").strip()
    dest_folder = (data or {}).get("dest_folder", "").strip()

    if not stem:
        return jsonify({"error": "缺少 stem 参数"}), 400

    filename = Path(stem).name  # 提取文件名（不含目录）
    new_stem = (Path(dest_folder) / filename).as_posix() if dest_folder else filename

    if stem == new_stem:
        return jsonify({"error": "源路径与目标相同"}), 400

    # 定义需要移动的文件对
    file_pairs = [
        (PDF_DIR / (stem + ".pdf"), PDF_DIR / (new_stem + ".pdf")),
        (PDF_ZH_DIR / (stem + ".pdf"), PDF_ZH_DIR / (new_stem + ".pdf")),
        (NOTE_DIR / (stem + ".md"), NOTE_DIR / (new_stem + ".md")),
    ]
    # 图片可能有多种扩展名
    for img_dir in [IMAGE_EN_DIR, IMAGE_ZH_DIR]:
        for ext in IMAGE_EXTENSIONS:
            src = img_dir / (stem + ext)
            dst = img_dir / (new_stem + ext)
            if src.exists():
                file_pairs.append((src, dst))

    # 检查英文 PDF 是否存在（至少要有原文）
    en_pdf = PDF_DIR / (stem + ".pdf")
    if not en_pdf.exists():
        return jsonify({"error": "原文 PDF 不存在"}), 404

    # 检查目标是否冲突
    for src, dst in file_pairs:
        if src.exists() and dst.exists() and src != dst:
            return jsonify({"error": f"目标已存在: {dst.relative_to(BASE_DIR)}"}), 409

    moved = []
    try:
        for src, dst in file_pairs:
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved.append(str(dst.relative_to(BASE_DIR)))
    except Exception as e:
        return jsonify({"error": f"移动失败: {e}", "moved": moved}), 500

    return jsonify({"success": True, "new_stem": new_stem, "moved": moved})


if __name__ == "__main__":
    for d in [PDF_DIR, PDF_ZH_DIR, NOTE_DIR, IMAGE_EN_DIR, IMAGE_ZH_DIR]:
        d.mkdir(exist_ok=True)
    print("=" * 50)
    print("  📚 论文阅读器")
    print("=" * 50)
    print(f"  PDF目录:      {PDF_DIR.resolve()}")
    print(f"  中文PDF目录:  {PDF_ZH_DIR.resolve()}")
    print(f"  笔记目录:     {NOTE_DIR.resolve()}")
    print(f"  英文图片目录: {IMAGE_EN_DIR.resolve()}")
    print(f"  中文图片目录: {IMAGE_ZH_DIR.resolve()}")
    print(f"\n  🌐 访问 http://127.0.0.1:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
