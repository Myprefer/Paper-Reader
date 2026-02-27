"""注册所有路由蓝图。"""

from .chat import bp as chat_bp
from .images import bp as images_bp
from .notes import bp as notes_bp
from .papers import bp as papers_bp
from .tree import bp as tree_bp


def register_routes(app):
    """将所有蓝图注册到 Flask 应用。"""
    app.register_blueprint(tree_bp)
    app.register_blueprint(papers_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(chat_bp)
