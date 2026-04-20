"""
论文阅读器 —— 桌面应用入口

使用 pywebview 将 Flask 应用包装为原生桌面窗口。
启动方式: python desktop.py
"""

import os
import sys
import threading
import socket

# ── PyInstaller 兼容：确保工作目录和 import 路径正确 ──
if getattr(sys, "frozen", False):
    # 打包后 exe 所在目录
    _exe_dir = os.path.dirname(sys.executable)
    os.chdir(_exe_dir)
    # 确保 backend 包可以被发现
    if _exe_dir not in sys.path:
        sys.path.insert(0, _exe_dir)

import webview

from backend.app import create_app
from backend.config import (
    DATA_DIR, FROZEN,
    IMAGE_EN_DIR, IMAGE_ZH_DIR, NOTE_DIR, PDF_DIR, PDF_ZH_DIR,
)

# ── 应用版本 ──
APP_VERSION = "1.1.0"


def _find_free_port(start: int = 5000, end: int = 5099) -> int:
    """在指定范围内找到一个空闲端口。"""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"未找到可用端口 ({start}-{end})")


def _start_flask(app, port: int):
    """在后台线程启动 Flask 服务器（生产模式，无重载）。"""
    import logging

    # 静默 Flask/Werkzeug 日志，避免控制台噪音
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)

    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def main():
    port = _find_free_port()
    app = create_app()
    url = f"http://127.0.0.1:{port}"

    print("=" * 50)
    print(f"  PaperReader v{APP_VERSION}", "(installed)" if FROZEN else "(dev)")
    print("=" * 50)
    print(f"  Data:       {DATA_DIR.resolve()}")
    print(f"  PDF:        {PDF_DIR.resolve()}")
    print(f"  PDF(zh):    {PDF_ZH_DIR.resolve()}")
    print(f"  Notes:      {NOTE_DIR.resolve()}")
    print(f"  Images(en): {IMAGE_EN_DIR.resolve()}")
    print(f"  Images(zh): {IMAGE_ZH_DIR.resolve()}")
    print(f"\n  Window opening... ({url})")
    print("=" * 50)

    # Flask 在守护线程中运行
    server_thread = threading.Thread(target=_start_flask, args=(app, port), daemon=True)
    server_thread.start()

    # 应用图标路径
    icon_path = None
    if FROZEN:
        # PyInstaller 6.x: 数据在 _internal 目录
        ico = os.path.join(sys._MEIPASS, "assets", "app.ico")
        if os.path.exists(ico):
            icon_path = ico
    else:
        ico = os.path.join(os.path.dirname(__file__), "assets", "app.ico")
        if os.path.exists(ico):
            icon_path = ico

    # 创建原生窗口
    window = webview.create_window(
        title=f"PaperReader v{APP_VERSION}",
        url=url,
        width=1400,
        height=900,
        min_size=(900, 600),
        text_select=True,
    )

    # 启动 GUI 主循环（阻塞直到窗口关闭）
    webview.start(
        debug="--debug" in sys.argv,
        private_mode=False,  # 保留 localStorage / sessionStorage
    )


if __name__ == "__main__":
    main()
