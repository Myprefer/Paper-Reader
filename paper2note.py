# To run this code you need to install the following dependencies:
# pip install google-genai

import pathlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types

BASE_DIR = pathlib.Path("/root/banana")
PDFS_DIR = BASE_DIR / "pdfs"
NOTES_DIR = BASE_DIR / "notes"

RATE_PER_MINUTE = 5
WORKERS = 5
_INTERVAL = 60.0 / RATE_PER_MINUTE

client = genai.Client(
    api_key="AIzaSyDeGkPec5WnFWq7HDqZwMbLcnuLZmWL0B4",
)


class _RateLimiter:
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

_rate_limiter = _RateLimiter(_INTERVAL)


def generate_for_pdf(idx: int, total: int, filepath: pathlib.Path):
    """为单个 PDF 生成讲解笔记并保存为 notes 目录下的同名 .md 文件。"""
    rel_path = filepath.relative_to(PDFS_DIR)
    note_path = NOTES_DIR / rel_path.with_suffix(".md")

    model = "gemini-3-pro-preview"
    pdf_bytes = filepath.read_bytes()
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(
                    data=pdf_bytes,
                    mime_type="application/pdf",
                ),
                types.Part.from_text(text="讲解这篇论文，用中文，附必要的公式或例子"),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level="HIGH",
        ),
    )

    _rate_limiter.acquire()
    print(f"[{idx}/{total}] 正在处理: {rel_path}")

    chunks: list[str] = []
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=generate_content_config,
    ):
        if chunk.text:
            # print(chunk.text, end="", flush=True)
            chunks.append(chunk.text)

    full_text = "".join(chunks)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"\n  ✓ 已保存: {note_path}")


def generate():
    """并行处理 pdfs 目录下所有 PDF 文件，速率限制为每分钟 RATE_PER_MINUTE 个。"""
    pdf_files = sorted(PDFS_DIR.rglob("*.pdf"))
    total = len(pdf_files)
    print(f"共找到 {total} 个 PDF 文件，速率限制 {RATE_PER_MINUTE} 个/分钟，并行线程 {WORKERS}\n")

    pending = []
    for idx, pdf_path in enumerate(pdf_files, 1):
        rel = pdf_path.relative_to(PDFS_DIR)
        note_path = NOTES_DIR / rel.with_suffix(".md")
        if note_path.exists():
            print(f"[{idx}/{total}] 跳过（已存在）: {rel}")
        else:
            pending.append((idx, pdf_path))

    print(f"\n待处理 {len(pending)} 个\n")

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(generate_for_pdf, idx, total, pdf_path): (idx, pdf_path)
            for idx, pdf_path in pending
        }
        for future in as_completed(futures):
            idx, pdf_path = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"  ✗ [{idx}/{total}] 处理失败 {pdf_path.name}: {e}")


if __name__ == "__main__":
    generate()



