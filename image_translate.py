# To run this code you need to install the following dependencies:
# pip install google-genai Pillow

import mimetypes
import pathlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
from PIL import Image

BASE_DIR = pathlib.Path(r"D:\ML\pythonProjects\banana")
IMAGES_DIR = BASE_DIR / "images-t"
IMAGES_ZH_DIR = BASE_DIR / "images_zh-t"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

RATE_PER_MINUTE = 5          # 每分钟最多发送的请求数
WORKERS = 5                  # 并行线程数
_INTERVAL = 60.0 / RATE_PER_MINUTE  # 两次请求之间的最小间隔（秒）

client = genai.Client(
    api_key="AIzaSyDeGkPec5WnFWq7HDqZwMbLcnuLZmWL0B4",
)

# 速率限制器：保证相邻两次 API 调用之间至少间隔 _INTERVAL 秒
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


def save_binary_file(file_name, data):
    f = open(file_name, "wb")
    f.write(data)
    f.close()
    print(f"File saved to: {file_name}")


def translate_image(idx: int, total: int, src_path: pathlib.Path):
    """将单张图片汉化后保存到 images_zh，保持相对路径一致。"""
    rel_path = src_path.relative_to(IMAGES_DIR)
    image_stem = rel_path.with_suffix("")

    model = "gemini-3-pro-image-preview"
    image = Image.open(src_path)
    contents = [
        image,
        "将图改为中文版本，Memory指的是记忆",
    ]
    generate_content_config = types.GenerateContentConfig(
        image_config=types.ImageConfig(
            aspect_ratio="4:3",
            image_size="2K",
        ),
        response_modalities=[
            "IMAGE",
            "TEXT",
        ],
    )

    # 限速：确保每分钟不超过 RATE_PER_MINUTE 次请求
    _rate_limiter.acquire()
    print(f"[{idx}/{total}] 正在处理: {rel_path}")

    file_index = 0
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

            if file_index == 0:
                out_name = f"{image_stem}{file_extension}"
            else:
                out_name = f"{image_stem}_{file_index}{file_extension}"
            file_index += 1

            out_path = IMAGES_ZH_DIR / out_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            save_binary_file(str(out_path), data_buffer)
        else:
            print(chunk.text)


def generate():
    """并行汉化 images 目录下所有图片，速率限制为每分钟 RATE_PER_MINUTE 张。"""
    image_files = sorted(
        p for p in IMAGES_DIR.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES
    )
    total = len(image_files)
    print(f"共找到 {total} 张图片，速率限制 {RATE_PER_MINUTE} 张/分钟，并行线程 {WORKERS}\n")

    # 过滤掉已存在的
    pending = []
    for idx, img_path in enumerate(image_files, 1):
        rel = img_path.relative_to(IMAGES_DIR)
        image_stem = rel.with_suffix("")
        existing = list(IMAGES_ZH_DIR.glob(f"{image_stem}.*"))
        if existing:
            print(f"[{idx}/{total}] 跳过（已存在）: {rel}")
        else:
            pending.append((idx, img_path))

    print(f"\n待处理 {len(pending)} 张\n")

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(translate_image, idx, total, img_path): (idx, img_path)
            for idx, img_path in pending
        }
        for future in as_completed(futures):
            idx, img_path = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"  ✗ [{idx}/{total}] 处理失败 {img_path.name}: {e}")


if __name__ == "__main__":
    generate()


