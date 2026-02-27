import fitz  # 导入 PyMuPDF
import re
import shutil
import pathlib

BASE_DIR = pathlib.Path(r"D:\ML\pythonProjects\banana")
PDFS_DIR = BASE_DIR / "pdfs"
PDFS_ZH_DIR = BASE_DIR / "pdfs_arxiv"


def extract_main_arxiv_id(pdf_path):
    # 基础的 arXiv ID 正则表达式
    arxiv_pattern = re.compile(r'arXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?|[a-z\-]+(?:\.[a-zA-Z]{2})?/\d{7}(?:v[0-9]+)?)', re.IGNORECASE)
    
    try:
        with fitz.open(pdf_path) as doc:
            if len(doc) == 0:
                return None
                
            # 获取第一页的所有 arXiv ID (使用 set 去重)
            page_1_ids = set(arxiv_pattern.findall(doc[0].get_text()))
            
            # 如果只有一页的极特殊情况，直接返回第一页找到的第一个
            if len(doc) == 1:
                return list(page_1_ids)[0] if page_1_ids else None
                
            # 获取第二页的所有 arXiv ID
            page_2_ids = set(arxiv_pattern.findall(doc[1].get_text()))
            
            # 【核心逻辑】：求第一页和第二页的交集！
            # 真正的水印必定同时存在于两页，而脚注引用绝不会正好跨页重复
            main_id = page_1_ids.intersection(page_2_ids)
            
            if main_id:
                return list(main_id)[0]
            else:
                return list(page_1_ids)[0] if page_1_ids else None
                
    except Exception as e:
        print(f"读取文件出错: {e}")
        
    return None


def generate():
    pdf_files = sorted(PDFS_DIR.rglob("*.pdf"))
    total = len(pdf_files)
    print(f"共找到 {total} 个 PDF 文件\n")

    succeeded = []
    skipped = []
    failed = []

    for idx, pdf_path in enumerate(pdf_files, 1):
        rel = pdf_path.relative_to(PDFS_DIR)
        dest_dir = PDFS_ZH_DIR / rel.parent

        arxiv_id = extract_main_arxiv_id(str(pdf_path))
        if not arxiv_id:
            print(f"[{idx}/{total}] ✗ 未找到 arXiv ID，跳过: {rel}")
            failed.append(str(rel))
            continue

        # arXiv ID 中的 '/' 不能作为文件名（旧格式如 cs.AI/0701001）
        safe_id = arxiv_id.replace("/", "_")
        dest_path = dest_dir / f"{safe_id}.pdf"

        if dest_path.exists():
            print(f"[{idx}/{total}] 跳过（已存在）: {dest_path.relative_to(PDFS_ZH_DIR)}")
            skipped.append(str(rel))
            continue

        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(pdf_path), str(dest_path))
        print(f"[{idx}/{total}] ✓ {rel.name}  →  {dest_path.relative_to(PDFS_ZH_DIR)}")
        succeeded.append(str(rel))

    print("\n" + "=" * 60)
    print(f"处理完毕：共 {total} 个，成功 {len(succeeded)} 个，跳过 {len(skipped)} 个，失败 {len(failed)} 个")
    if failed:
        print("\n【失败列表】")
        for f in failed:
            print(f"  ✗ {f}")
    print("=" * 60)


if __name__ == "__main__":
    generate()
