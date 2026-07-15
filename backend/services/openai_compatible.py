"""OpenAI-compatible API client and paper/image helpers."""

from __future__ import annotations

import base64
import json
import mimetypes
import threading
import time
from pathlib import Path
from typing import Iterable

import fitz
import requests

from ..config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_DEFAULT_IMAGE_MODEL,
    OPENAI_DEFAULT_TEXT_MODEL,
    OPENAI_IMAGE_MODELS,
    OPENAI_MAX_PDF_CHARS,
    OPENAI_RATE_LIMIT,
    OPENAI_STREAM_IDLE_TIMEOUT,
    OPENAI_TEXT_MODELS,
    OPENAI_TIMEOUT,
)

AI_AVAILABLE = bool(OPENAI_BASE_URL)


class AIServiceError(RuntimeError):
    """A sanitized error returned by the compatible API."""


class _RateLimiter:
    def __init__(self, rate_per_minute: float):
        self._interval = 60.0 / max(rate_per_minute, 0.1)
        self._lock = threading.Lock()
        self._last = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


_rate_limiter = _RateLimiter(OPENAI_RATE_LIMIT)
_session = requests.Session()


def text_models() -> tuple[str, ...]:
    return tuple(dict.fromkeys((OPENAI_DEFAULT_TEXT_MODEL, *OPENAI_TEXT_MODELS)))


def image_models() -> tuple[str, ...]:
    return tuple(dict.fromkeys((OPENAI_DEFAULT_IMAGE_MODEL, *OPENAI_IMAGE_MODELS)))


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
    return headers


def _url(path: str) -> str:
    return f"{OPENAI_BASE_URL}/{path.lstrip('/')}"


def _error_message(response: requests.Response) -> str:
    try:
        body = response.json()
        error = body.get("error", body)
        if isinstance(error, dict):
            return str(error.get("message") or error.get("detail") or error)
        return str(error)
    except Exception:
        return (response.text or response.reason or "未知错误")[:1000]


def _raise_for_status(response: requests.Response) -> None:
    if response.ok:
        return
    raise AIServiceError(
        f"AI API 请求失败（HTTP {response.status_code}）：{_error_message(response)}"
    )


def _content_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        chunks = []
        for item in value:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                chunks.append(str(item.get("text") or item.get("content") or ""))
        return "".join(chunks)
    return ""


def chat_stream(
    messages: list[dict],
    model: str = OPENAI_DEFAULT_TEXT_MODEL,
) -> Iterable[str]:
    """Stream text from the Chat Completions compatible endpoint."""
    _rate_limiter.acquire()
    try:
        response = _session.post(
            _url("chat/completions"),
            headers=_headers(),
            json={"model": model, "messages": messages, "stream": True},
            timeout=(10, min(OPENAI_TIMEOUT, OPENAI_STREAM_IDLE_TIMEOUT)),
            stream=True,
        )
    except requests.RequestException as exc:
        raise AIServiceError(f"无法连接 AI API：{exc}") from exc

    try:
        _raise_for_status(response)
        last_content_at = time.monotonic()
        for raw_line in response.iter_lines(decode_unicode=True):
            if time.monotonic() - last_content_at > OPENAI_STREAM_IDLE_TIMEOUT:
                raise AIServiceError(
                    f"AI 流式响应超过 {OPENAI_STREAM_IDLE_TIMEOUT:g} 秒没有产生文本"
                )
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            if not choices:
                continue
            text = _content_text((choices[0].get("delta") or {}).get("content"))
            if text:
                last_content_at = time.monotonic()
                yield text
    finally:
        response.close()


def chat_complete(
    messages: list[dict],
    model: str = OPENAI_DEFAULT_TEXT_MODEL,
) -> str:
    """Return one non-streaming Chat Completions response."""
    _rate_limiter.acquire()
    try:
        response = _session.post(
            _url("chat/completions"),
            headers=_headers(),
            json={"model": model, "messages": messages, "stream": False},
            timeout=OPENAI_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AIServiceError(f"无法连接 AI API：{exc}") from exc
    _raise_for_status(response)
    try:
        return _content_text(response.json()["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIServiceError("AI API 返回了无法识别的文本响应") from exc


def extract_pdf_text(pdf_path: Path, max_chars: int = OPENAI_MAX_PDF_CHARS) -> str:
    """Extract readable, page-delimited text locally instead of uploading a PDF."""
    chunks: list[str] = []
    total = 0
    with fitz.open(str(pdf_path)) as document:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text").strip()
            if not text:
                continue
            chunk = f"\n\n--- Page {page_number} ---\n{text}"
            remaining = max_chars - total
            if remaining <= 0:
                break
            chunks.append(chunk[:remaining])
            total += min(len(chunk), remaining)
    result = "".join(chunks).strip()
    if not result:
        raise AIServiceError("无法从 PDF 提取文本；该文件可能是扫描版 PDF")
    return result


def image_data_url(image_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def multimodal_content(text: str, images: list[dict] | None = None) -> list[dict]:
    content: list[dict] = []
    for image in images or []:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_data_url(image["bytes"], image["mime"]),
                },
            }
        )
    if text:
        content.append({"type": "text", "text": text})
    return content


def _decode_image_response(response: requests.Response) -> tuple[bytes, str]:
    _raise_for_status(response)
    try:
        item = response.json()["data"][0]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIServiceError("AI API 返回了无法识别的图片响应") from exc

    encoded = item.get("b64_json") or item.get("b64")
    if encoded:
        return base64.b64decode(encoded), "image/png"

    image_url = item.get("url")
    if image_url:
        try:
            downloaded = _session.get(image_url, timeout=OPENAI_TIMEOUT)
        except requests.RequestException as exc:
            raise AIServiceError(f"生成图片下载失败：{exc}") from exc
        _raise_for_status(downloaded)
        mime = downloaded.headers.get("Content-Type", "image/png").split(";", 1)[0]
        return downloaded.content, mime

    raise AIServiceError("图片响应中没有 b64_json 或 url")


def generate_image(
    prompt: str,
    model: str = OPENAI_DEFAULT_IMAGE_MODEL,
    size: str = "1536x1024",
) -> tuple[bytes, str]:
    _rate_limiter.acquire()
    try:
        response = _session.post(
            _url("images/generations"),
            headers=_headers(),
            json={"model": model, "prompt": prompt, "size": size, "n": 1},
            timeout=OPENAI_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AIServiceError(f"图片生成请求失败：{exc}") from exc
    return _decode_image_response(response)


def edit_image(
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    model: str = OPENAI_DEFAULT_IMAGE_MODEL,
    size: str = "1536x1024",
) -> tuple[bytes, str]:
    _rate_limiter.acquire()
    extension = mimetypes.guess_extension(mime_type) or ".png"
    headers = {}
    if OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {OPENAI_API_KEY}"
    try:
        response = _session.post(
            _url("images/edits"),
            headers=headers,
            data={"model": model, "prompt": prompt, "size": size, "n": "1"},
            files={"image": (f"source{extension}", image_bytes, mime_type)},
            timeout=OPENAI_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AIServiceError(f"图片编辑请求失败：{exc}") from exc
    return _decode_image_response(response)


def paper_illustration_prompt(pdf_text: str, model: str = OPENAI_DEFAULT_TEXT_MODEL) -> str:
    """Ask the text model for a concise prompt accepted by image APIs."""
    instruction = (
        "阅读下面论文内容，提炼核心方法与创新，输出一段可直接交给图片生成模型的中文绘图提示词。"
        "目标是清晰、专业的科研论文概念图，使用 3:2 横版构图；突出数据流、关键模块和创新点；"
        "图内标签使用简洁英文；不要输出解释、Markdown 或前后缀，只输出绘图提示词。\n\n"
        f"论文内容：\n{pdf_text}"
    )
    return chat_complete([{"role": "user", "content": instruction}], model=model).strip()
