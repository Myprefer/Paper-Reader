import os
from pathlib import Path
from flask import Flask, jsonify, send_from_directory, render_template, abort, request

app = Flask(__name__)

BASE_DIR = Path(__file__).parent

GALLERIES = {
    "images": BASE_DIR / "images-t",
    "images_zh": BASE_DIR / "images_zh-t",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def build_tree(directory: Path, base: Path) -> dict:
    """递归构建目录树结构"""
    node = {
        "name": directory.name,
        "type": "dir",
        "path": directory.relative_to(base).as_posix(),
        "children": [],
    }
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return node

    for entry in entries:
        if entry.is_dir():
            sub = build_tree(entry, base)
            if sub["children"]:  # 只保留非空目录
                node["children"].append(sub)
        elif entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
            rel = entry.relative_to(base).as_posix()
            node["children"].append({
                "name": entry.name,
                "type": "file",
                "path": rel,
                "size": entry.stat().st_size,
            })
    return node


# ──────────────────────────────────────────────
# 前端页面
# ──────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("image_manager.html")


# ──────────────────────────────────────────────
# API：获取目录树
# ──────────────────────────────────────────────
@app.route("/api/tree/<gallery>")
def get_tree(gallery: str):
    if gallery not in GALLERIES:
        abort(404)
    root = GALLERIES[gallery]
    root.mkdir(exist_ok=True)
    tree = build_tree(root, root)
    return jsonify(tree)


# ──────────────────────────────────────────────
# API：图片服务（缩略图 / 预览）
# ──────────────────────────────────────────────
@app.route("/img/<gallery>/<path:filepath>")
def serve_image(gallery: str, filepath: str):
    if gallery not in GALLERIES:
        abort(404)
    root = GALLERIES[gallery]
    # 安全校验：防止路径穿越
    target = (root / filepath).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        abort(403)
    return send_from_directory(root, filepath)


# ──────────────────────────────────────────────
# API：下载
# ──────────────────────────────────────────────
@app.route("/download/<gallery>/<path:filepath>")
def download_image(gallery: str, filepath: str):
    if gallery not in GALLERIES:
        abort(404)
    root = GALLERIES[gallery]
    target = (root / filepath).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        abort(403)
    return send_from_directory(root, filepath, as_attachment=True)


# ──────────────────────────────────────────────
# API：删除
# ──────────────────────────────────────────────
@app.route("/delete/<gallery>/<path:filepath>", methods=["DELETE"])
def delete_image(gallery: str, filepath: str):
    if gallery not in GALLERIES:
        abort(404)
    root = GALLERIES[gallery]
    target = (root / filepath).resolve()
    # 安全校验：防止路径穿越
    try:
        target.relative_to(root.resolve())
    except ValueError:
        abort(403)
    if not target.exists() or not target.is_file():
        return jsonify({"error": "File not found"}), 404
    target.unlink()
    # 删除后清理空目录（可选）
    parent = target.parent
    while parent != root and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent
    return jsonify({"deleted": filepath})


if __name__ == "__main__":
    for name, path in GALLERIES.items():
        path.mkdir(exist_ok=True)
        print(f"[INFO] Gallery '{name}': {path.resolve()}")
    print("[INFO] 访问 http://127.0.0.1:5000 打开图片管理界面")
    app.run(host="0.0.0.0", port=5000, debug=True)
