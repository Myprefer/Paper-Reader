import fitz
import re
import pathlib
import requests
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = pathlib.Path(r"D:\ML\pythonProjects\banana")
PDFS_DIR = BASE_DIR / "pdfs"
PDFS_ZH_DIR = BASE_DIR / "pdfs_zh"

WORKERS = 5
RATE_PER_MINUTE = 20          # 爬虫无严格限速，保守设 20/min
_INTERVAL = 60.0 / RATE_PER_MINUTE

HEADERS = {
    'sec-ch-ua-platform': '"Windows"',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0',
    'sec-ch-ua': '"Not:A-Brand";v="99", "Microsoft Edge";v="145", "Chromium";v="145"',
    'sec-ch-ua-mobile': '?0',
}


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


def extract_main_arxiv_id(pdf_path: str) -> str | None:
    arxiv_pattern = re.compile(
        r'arXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?|[a-z\-]+(?:\.[a-zA-Z]{2})?/\d{7}(?:v[0-9]+)?)',
        re.IGNORECASE,
    )
    try:
        with fitz.open(pdf_path) as doc:
            if len(doc) == 0:
                return None
            page_1_ids = set(arxiv_pattern.findall(doc[0].get_text()))
            if len(doc) == 1:
                return list(page_1_ids)[0] if page_1_ids else None
            page_2_ids = set(arxiv_pattern.findall(doc[1].get_text()))
            main_id = page_1_ids.intersection(page_2_ids)
            if main_id:
                return list(main_id)[0]
            return list(page_1_ids)[0] if page_1_ids else None
    except Exception as e:
        print(f"  读取文件出错: {e}")
    return None


def download_translated_pdf(arxiv_id: str) -> bytes | None:
    """通过 hjfy.top 爬取翻译后的 PDF 内容，返回原始字节。"""
    headers = {**HEADERS, 'Referer': f'https://hjfy.top/arxiv/{arxiv_id}'}
    try:
        resp = requests.get(
            f'https://hjfy.top/api/arxivFiles/{arxiv_id}',
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = json.loads(resp.text)
        zh_url = data['data']['zhCN']
        if not zh_url:
            return None
        pdf_resp = requests.get(zh_url, headers=headers, timeout=60)
        pdf_resp.raise_for_status()
        return pdf_resp.content
    except Exception as e:
        print(f"  下载失败 ({arxiv_id}): {e}")
    return None


def process_pdf(idx: int, total: int, pdf_path: pathlib.Path):
    rel = pdf_path.relative_to(PDFS_DIR)
    dest_path = PDFS_ZH_DIR / rel  # 保持原文件名和路径

    arxiv_id = extract_main_arxiv_id(str(pdf_path))
    if not arxiv_id:
        raise ValueError("未找到 arXiv ID")

    # 去除可能的版本号后缀（如 v2），API 通常用不带版本的 ID
    arxiv_id_clean = re.sub(r'v\d+$', '', arxiv_id)

    _rate_limiter.acquire()
    print(f"[{idx}/{total}] 正在处理: {rel}  (arXiv: {arxiv_id_clean})")

    pdf_bytes = download_translated_pdf(arxiv_id_clean)
    if not pdf_bytes:
        raise RuntimeError("未获取到翻译 PDF")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(pdf_bytes)
    print(f"  ✓ 已保存: {dest_path.relative_to(PDFS_ZH_DIR)}")


def generate():
    pdf_files = sorted(PDFS_DIR.rglob("*.pdf"))
    total = len(pdf_files)
    print(f"共找到 {total} 个 PDF 文件，并行线程 {WORKERS}\n")

    pending = []
    skipped = []
    for idx, pdf_path in enumerate(pdf_files, 1):
        rel = pdf_path.relative_to(PDFS_DIR)
        dest_path = PDFS_ZH_DIR / rel
        if dest_path.exists():
            print(f"[{idx}/{total}] 跳过（已存在）: {rel}")
            skipped.append(str(rel))
        else:
            pending.append((idx, pdf_path))

    print(f"\n待处理 {len(pending)} 个\n")

    succeeded = []
    failed = []

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(process_pdf, idx, total, pdf_path): (idx, pdf_path)
            for idx, pdf_path in pending
        }
        for future in as_completed(futures):
            idx, pdf_path = futures[future]
            rel = pdf_path.relative_to(PDFS_DIR)
            try:
                future.result()
                succeeded.append(str(rel))
            except Exception as e:
                print(f"  ✗ [{idx}/{total}] 处理失败 {rel}: {e}")
                failed.append(str(rel))

    print("\n" + "=" * 60)
    print(f"处理完毕：共 {total} 个，成功 {len(succeeded)} 个，跳过 {len(skipped)} 个，失败 {len(failed)} 个")
    if failed:
        print("\n【失败列表】")
        for f in failed:
            print(f"  ✗ {f}")
    print("=" * 60)


if __name__ == "__main__":
    generate()
