"""Flask 应用工厂。"""

import sys
from pathlib import Path

from flask import Flask
from flask_cors import CORS

from .config import APP_DIR, IMAGE_EN_DIR, IMAGE_ZH_DIR, NOTE_DIR, PDF_DIR, PDF_ZH_DIR
from .db import close_db, init_db
from .routes import register_routes


def _get_static_folder() -> str:
    """获取前端静态文件目录。"""
    if getattr(sys, "frozen", False):
        # PyInstaller: 从 _MEIPASS（内部数据）加载
        return str(Path(sys._MEIPASS) / "frontend" / "dist")
    return str(APP_DIR / "frontend" / "dist")


def create_app():
    """创建并配置 Flask 应用。"""
    app = Flask(
        __name__,
        static_folder=_get_static_folder(),
        static_url_path="",
    )

    # 启用 CORS 以支持多设备远程访问
    CORS(app)

    # 确保存储目录存在
    for d in [PDF_DIR, PDF_ZH_DIR, NOTE_DIR, IMAGE_EN_DIR, IMAGE_ZH_DIR]:
        d.mkdir(exist_ok=True)

    # 初始化数据库
    init_db()

    # 注册请求结束时的数据库连接清理
    app.teardown_appcontext(close_db)

    # 注册所有路由蓝图
    register_routes(app)

    # SPA 入口
    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    # SPA 客户端路由回退
    @app.errorhandler(404)
    def fallback(e):
        return app.send_static_file("index.html")

    return app
