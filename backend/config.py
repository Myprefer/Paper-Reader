"""应用配置：路径、常量、API密钥等。"""

import sys
from pathlib import Path
import os

# ── 是否为 PyInstaller 打包模式 ──
FROZEN = getattr(sys, "frozen", False)


def _get_app_dir() -> Path:
    """应用程序文件所在目录（前端构建产物等只读资源）。"""
    if FROZEN:
        # PyInstaller one-folder 模式：exe 所在目录
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def _get_data_dir() -> Path:
    """用户数据目录（PDF、笔记、图片、数据库等可读写数据）。

    打包模式下使用 ~/Documents/PaperReader/，
    开发模式下与项目根目录相同。
    """
    data = Path.home() / "Documents" / "PaperReader"
    data.mkdir(parents=True, exist_ok=True)
    return data


# ── 目录 ──
APP_DIR = _get_app_dir()
DATA_DIR = _get_data_dir()

# ── 文件存储目录（用户数据） ──
PDF_DIR = DATA_DIR / "pdfs"
PDF_ZH_DIR = DATA_DIR / "pdfs_zh"
NOTE_DIR = DATA_DIR / "notes"
IMAGE_EN_DIR = DATA_DIR / "images"
IMAGE_ZH_DIR = DATA_DIR / "images_zh"

# ── 数据库 ──
DB_PATH = DATA_DIR / "data" / "papers.db"

# ── 图片扩展名 ──
IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]

# ── Gemini AI ──
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_RATE_LIMIT = 5  # 每分钟请求次数
