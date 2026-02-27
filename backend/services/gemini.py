"""Gemini AI 服务封装：客户端初始化、速率限制。"""

import threading
import time

from ..config import GEMINI_API_KEY, GEMINI_RATE_LIMIT

# ── 可选依赖导入 ──
try:
    from google import genai
    from google.genai import types as genai_types

    GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore
    genai_types = None  # type: ignore
    GENAI_AVAILABLE = False


class _RateLimiter:
    """简单的令牌桶限速器，保证每分钟不超过指定数量请求。"""

    def __init__(self, rate_per_minute: float):
        self._interval = 60.0 / rate_per_minute
        self._lock = threading.Lock()
        self._last = 0.0

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


# ── 模块级单例 ──
_client = None
_rate_limiter = None

if GENAI_AVAILABLE:
    _client = genai.Client(api_key=GEMINI_API_KEY)
    _rate_limiter = _RateLimiter(GEMINI_RATE_LIMIT)


def get_client():
    """获取 Gemini 客户端实例。"""
    return _client


def get_rate_limiter():
    """获取速率限制器实例。"""
    return _rate_limiter


def get_types():
    """获取 genai types 模块。"""
    return genai_types
