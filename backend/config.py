"""应用配置：路径、常量、API密钥等。"""

import sys
from pathlib import Path
import os

from dotenv import load_dotenv

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

# 开发模式读取项目根目录的 .env；打包后读取 exe 同目录的 .env。
# override=False 保证系统环境变量始终优先。
load_dotenv(APP_DIR / ".env", override=False)

# ── 文件存储目录（用户数据） ──
PDF_DIR = DATA_DIR / "pdfs"
PDF_ZH_DIR = DATA_DIR / "pdfs_zh"
NOTE_DIR = DATA_DIR / "notes"
IMAGE_EN_DIR = DATA_DIR / "images"
IMAGE_ZH_DIR = DATA_DIR / "images_zh"
CHAT_IMAGE_DIR = DATA_DIR / "chat_images"

# ── 数据库 ──
DB_PATH = DATA_DIR / "data" / "papers.db"

# ── 图片扩展名 ──
IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]

# ── OpenAI-compatible AI ──


def _normalize_openai_base_url(value: str) -> str:
    """规范化兼容接口地址，并修正常见的 /v1/v1 重复配置。"""
    url = value.strip().rstrip("/")
    while url.endswith("/v1/v1"):
        url = url[:-3]
    return url


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


OPENAI_BASE_URL = _normalize_openai_base_url(
    os.getenv("OPENAI_BASE_URL", "http://localhost:55696/v1")
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_TEXT_MODELS = _csv_env(
    "OPENAI_TEXT_MODELS",
    "gpt-5.6-sol,gpt-5.6-terra,gpt-5.6-luna,gpt-5.5,gpt-5.4,gpt-5.4-mini",
)
OPENAI_DEFAULT_TEXT_MODEL = os.getenv("OPENAI_DEFAULT_TEXT_MODEL", "gpt-5.4-mini")
OPENAI_IMAGE_MODELS = _csv_env("OPENAI_IMAGE_MODELS", "gpt-image-2")
OPENAI_DEFAULT_IMAGE_MODEL = os.getenv("OPENAI_DEFAULT_IMAGE_MODEL", "gpt-image-2")
OPENAI_RATE_LIMIT = float(os.getenv("OPENAI_RATE_LIMIT", "20"))
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "300"))
OPENAI_STREAM_IDLE_TIMEOUT = float(os.getenv("OPENAI_STREAM_IDLE_TIMEOUT", "120"))
OPENAI_MAX_PDF_CHARS = int(os.getenv("OPENAI_MAX_PDF_CHARS", "300000"))
