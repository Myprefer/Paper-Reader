import os
import re
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template_string

app = Flask(__name__)

DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

# 单次上传文件大小限制：2GB
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024


def resolve_filename(directory: Path, filename: str) -> str:
    """若目标目录下已存在同名文件，则在文件名后追加序号，返回最终可用文件名。"""
    target = directory / filename
    if not target.exists():
        return filename

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    # 若 stem 末尾已带序号，则提取基础名称
    match = re.match(r"^(.*?)(\((\d+)\))$", stem)
    if match:
        base = match.group(1)
        counter = int(match.group(3)) + 1
    else:
        base = stem
        counter = 1

    while True:
        new_name = f"{base}({counter}){suffix}"
        if not (directory / new_name).exists():
            return new_name
        counter += 1


# ──────────────────────────────────────────────
# 前端页面
# ──────────────────────────────────────────────
with open(Path(__file__).parent / "templates" / "index.html", encoding="utf-8") as _f:
    _HTML = _f.read()


@app.route("/")
def index():
    return render_template_string(_HTML)


# ──────────────────────────────────────────────
# API：上传
# ──────────────────────────────────────────────
@app.route("/upload", methods=["POST"])
def upload():
    if "files" not in request.files:
        return jsonify({"error": "No file part"}), 400

    uploaded = []
    for file in request.files.getlist("files"):
        if file.filename == "":
            continue
        safe_name = Path(file.filename).name  # 去掉路径部分
        final_name = resolve_filename(DOWNLOAD_DIR, safe_name)
        file.save(DOWNLOAD_DIR / final_name)
        uploaded.append({"original": safe_name, "saved": final_name})

    if not uploaded:
        return jsonify({"error": "No valid file uploaded"}), 400

    return jsonify({"uploaded": uploaded}), 200


# ──────────────────────────────────────────────
# API：列出文件
# ──────────────────────────────────────────────
@app.route("/files", methods=["GET"])
def list_files():
    files = []
    for p in sorted(DOWNLOAD_DIR.iterdir()):
        if p.is_file():
            files.append({"name": p.name, "size": p.stat().st_size})
    return jsonify({"files": files})


# ──────────────────────────────────────────────
# API：下载
# ──────────────────────────────────────────────
@app.route("/download/<path:filename>", methods=["GET"])
def download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


# ──────────────────────────────────────────────
# API：删除
# ──────────────────────────────────────────────
@app.route("/delete/<path:filename>", methods=["DELETE"])
def delete_file(filename):
    target = DOWNLOAD_DIR / filename
    if not target.exists() or not target.is_file():
        return jsonify({"error": "File not found"}), 404
    target.unlink()
    return jsonify({"deleted": filename})


if __name__ == "__main__":
    print(f"[INFO] 文件保存目录: {DOWNLOAD_DIR.resolve()}")
    print("[INFO] 访问 http://127.0.0.1:5000 打开界面")
    app.run(host="0.0.0.0", port=5000, debug=False)
