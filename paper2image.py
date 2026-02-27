# To run this code you need to install the following dependencies:
# pip install google-genai

import mimetypes
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
import pathlib

def save_binary_file(file_name, data):
    f = open(file_name, "wb")
    f.write(data)
    f.close()
    print(f"File saved to to: {file_name}")

# 项目根目录
BASE_DIR = pathlib.Path("/root/banana")
PDFS_DIR = BASE_DIR / "pdfs"
IMAGES_DIR = BASE_DIR / "images"

RATE_PER_MINUTE = 5      # 每分钟最多发送的请求数
WORKERS = 5              # 并行线程数
_INTERVAL = 60.0 / RATE_PER_MINUTE

client = genai.Client(
    api_key="AIzaSyDeGkPec5WnFWq7HDqZwMbLcnuLZmWL0B4",
)

# 速率限制器
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


MAX_RETRIES = 5


def generate_for_pdf(idx: int, total: int, filepath: pathlib.Path):
    """为单个 PDF 生成配图并保存到 images 目录（保持相对路径一致）。
    若 API 只返回文字未返回图片，则将收到的文字连同原始提示词+PDF 重新发送，最多重试 MAX_RETRIES 次。
    """
    # 计算相对于 pdfs 目录的相对路径，并映射到 images 目录
    rel_path = filepath.relative_to(PDFS_DIR)
    image_stem = rel_path.with_suffix("")  # 去掉 .pdf

    model = "gemini-3-pro-image-preview"
    pdf_bytes = filepath.read_bytes()

    # 初始对话内容
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text="为这篇论文绘制一张清晰易懂的，科研论文配图用来辅助讲解这篇论文的核心创新点"
                ),
                types.Part.from_bytes(
                    data=pdf_bytes,
                    mime_type="application/pdf",
                ),
            ],
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        image_config=types.ImageConfig(
            aspect_ratio="4:3",
            image_size="1K",
        ),
        response_modalities=[
            "IMAGE",
            "TEXT",
        ],
    )

    # 限速：确保每分钟不超过 RATE_PER_MINUTE 次请求
    _rate_limiter.acquire()
    print(f"[{idx}/{total}] 正在处理: {rel_path}")

    for attempt in range(1, MAX_RETRIES + 1):
        file_index = 0
        text_chunks: list[str] = []

        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=generate_content_config,
        ):
            if chunk.parts is None:
                continue
            if chunk.parts[0].inline_data and chunk.parts[0].inline_data.data:
                inline_data = chunk.parts[0].inline_data
                data_buffer = inline_data.data
                file_extension = mimetypes.guess_extension(inline_data.mime_type)

                # 构造输出路径：images/<相对路径>/<pdf同名>[_序号].ext
                if file_index == 0:
                    out_name = f"{image_stem}{file_extension}"
                else:
                    out_name = f"{image_stem}_{file_index}{file_extension}"
                file_index += 1

                out_path = IMAGES_DIR / out_name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                save_binary_file(str(out_path), data_buffer)
            else:
                text_chunks.append(chunk.text)
                print(chunk.text)

        if file_index > 0:
            # 成功获取到图片，结束
            break

        # 未获取到图片，将模型返回的文字追加到对话并重试
        received_text = "".join(text_chunks).strip()
        print(f"  ⚠ 第 {attempt} 次未获得图片，仅收到文字，准备重试...")
        if attempt < MAX_RETRIES:
            # 把模型的文字回复加入对话历史
            if received_text:
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=received_text)],
                    )
                )
            # 再次追加用户提示，要求生成图片
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text="请直接生成图片，不要只回复文字。"
                        ),
                        # types.Part.from_bytes(
                        #     data=pdf_bytes,
                        #     mime_type="application/pdf",
                        # ),
                    ],
                )
            )
        else:
            print(f"  ✗ 已达最大重试次数 ({MAX_RETRIES})，跳过该文件。")


def generate():
    """并行处理 pdfs 目录下所有 PDF 文件，速率限制为每分钟 RATE_PER_MINUTE 张。"""
    pdf_files = sorted(PDFS_DIR.rglob("*.pdf"))
    total = len(pdf_files)
    print(f"共找到 {total} 个 PDF 文件，速率限制 {RATE_PER_MINUTE} 张/分钟，并行线程 {WORKERS}\n")

    # 过滤掉已存在的
    pending = []
    for idx, pdf_path in enumerate(pdf_files, 1):
        rel = pdf_path.relative_to(PDFS_DIR)
        image_stem = rel.with_suffix("")
        existing = list(IMAGES_DIR.glob(f"{image_stem}.*"))
        if existing:
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


