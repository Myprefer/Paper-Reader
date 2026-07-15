"""End-to-end usefulness test for the configured OpenAI-compatible API.

This script intentionally exercises the same helpers used by PaperReader while
keeping all generated artifacts outside the application database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import (  # noqa: E402
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_DEFAULT_IMAGE_MODEL,
    OPENAI_DEFAULT_TEXT_MODEL,
    OPENAI_TIMEOUT,
)
from backend.services.openai_compatible import (  # noqa: E402
    chat_complete,
    chat_stream,
    edit_image,
    extract_pdf_text,
    generate_image,
    multimodal_content,
    paper_illustration_prompt,
)


def png_info(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("响应不是有效 PNG")
    return struct.unpack(">II", data[16:24])


def timed(name: str, fn, results: list[dict]):
    print(f"[START] {name}", flush=True)
    started = time.perf_counter()
    try:
        value = fn()
        duration = time.perf_counter() - started
        results.append({"name": name, "ok": True, "seconds": duration})
        print(f"[PASS ] {name} ({duration:.1f}s)", flush=True)
        return value
    except Exception as exc:
        duration = time.perf_counter() - started
        results.append(
            {"name": name, "ok": False, "seconds": duration, "error": str(exc)}
        )
        print(f"[FAIL ] {name} ({duration:.1f}s): {exc}", flush=True)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path, help="用于测试的真实论文 PDF")
    parser.add_argument(
        "--expected-term",
        default="",
        help="事实问答中应出现的论文核心术语；默认取文件名第一个单词",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "tmp" / "openai-api-test",
    )
    parser.add_argument(
        "--max-ai-chars",
        type=int,
        default=30000,
        help="最多发送给模型的论文字数；PDF 仍会完整执行本地提取",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    expected_term = args.expected_term or re.split(r"\s+", args.pdf.stem, maxsplit=1)[0]

    results: list[dict] = []
    evidence: dict[str, str] = {}

    def list_models():
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}
        response = requests.get(
            f"{OPENAI_BASE_URL}/models", headers=headers, timeout=OPENAI_TIMEOUT
        )
        response.raise_for_status()
        models = [item["id"] for item in response.json().get("data", [])]
        if OPENAI_DEFAULT_TEXT_MODEL not in models:
            raise AssertionError(f"默认文本模型不在 /models 中：{OPENAI_DEFAULT_TEXT_MODEL}")
        if OPENAI_DEFAULT_IMAGE_MODEL not in models:
            raise AssertionError(f"默认图片模型不在 /models 中：{OPENAI_DEFAULT_IMAGE_MODEL}")
        evidence["models"] = ", ".join(models)
        return models

    timed("模型发现与默认模型检查", list_models, results)

    pdf_text = timed(
        "真实 PDF 本地文本提取", lambda: extract_pdf_text(args.pdf), results
    )
    if pdf_text:
        extracted_chars = len(pdf_text)
        pdf_text = pdf_text[: args.max_ai_chars]
        evidence["pdf"] = (
            f"{args.pdf.name}: extracted={extracted_chars:,}, sent={len(pdf_text):,} characters"
        )

    note_text = None
    if pdf_text:
        def make_note():
            chunks = list(
                chat_stream(
                    [
                        {
                            "role": "user",
                            "content": (
                                "请基于下面论文生成中文 Markdown 讲解笔记。至少包含：研究问题、"
                                "核心方法、关键技术、实验结论、局限性五个章节；保留关键参数和"
                                "公式信息；不少于 300 个中文字符。不要编造论文中没有的数据。\n\n"
                                + pdf_text
                            ),
                        }
                    ],
                    model=OPENAI_DEFAULT_TEXT_MODEL,
                )
            )
            text = "".join(chunks).strip()
            chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
            headings = len(re.findall(r"^#{1,6}\s+", text, flags=re.MULTILINE))
            if len(chunks) < 2:
                raise AssertionError("流式接口只返回了一个数据块")
            if chinese < 180 or headings < 4:
                raise AssertionError(
                    f"笔记质量门槛未达标：中文字符={chinese}, Markdown 标题={headings}"
                )
            (args.output_dir / "generated-note.md").write_text(text, encoding="utf-8")
            evidence["note"] = (
                f"chunks={len(chunks)}, chars={len(text)}, Chinese={chinese}, headings={headings}"
            )
            return text

        note_text = timed("长论文流式中文笔记", make_note, results)

    if pdf_text:
        def grounded_qa():
            answer = chat_complete(
                [
                    {
                        "role": "user",
                        "content": (
                            "只根据所给论文回答：论文提出的主要系统/方法叫什么、解决什么问题，"
                            "并列出两个关键模块或设计。"
                            "答案控制在 250 字内；若论文没有说明则明确说没有。\n\n"
                            + pdf_text
                        ),
                    }
                ],
                model=OPENAI_DEFAULT_TEXT_MODEL,
            ).strip()
            if expected_term.lower() not in answer.lower() or len(answer) < 80:
                raise AssertionError(f"回答缺少论文核心术语 {expected_term} 或内容过短：{answer}")
            evidence["qa"] = answer
            return answer

        timed("基于论文的事实问答", grounded_qa, results)

        def structured_output():
            text = chat_complete(
                [
                    {
                        "role": "user",
                        "content": (
                            "提取论文提出的主要模型别名。只返回 JSON，不要 Markdown："
                            '{"alias": string|null, "evidence": string|null}\n\n'
                            + pdf_text[:25000]
                        ),
                    }
                ],
                model=OPENAI_DEFAULT_TEXT_MODEL,
            ).strip()
            text = re.sub(r"^```\w*\s*|\s*```$", "", text)
            parsed = json.loads(text)
            if not parsed.get("alias") or not parsed.get("evidence"):
                raise AssertionError(f"结构化提取内容不完整：{parsed}")
            evidence["json"] = json.dumps(parsed, ensure_ascii=False)
            return parsed

        timed("结构化 JSON 提取", structured_output, results)

    illustration_prompt = None
    if pdf_text:
        illustration_prompt = timed(
            "论文到绘图提示词",
            lambda: paper_illustration_prompt(
                pdf_text, model=OPENAI_DEFAULT_TEXT_MODEL
            ),
            results,
        )
        if illustration_prompt:
            evidence["image_prompt"] = illustration_prompt[:600]

    generated = None
    if illustration_prompt:
        def make_image():
            image_bytes, mime = generate_image(
                illustration_prompt, model=OPENAI_DEFAULT_IMAGE_MODEL
            )
            width, height = png_info(image_bytes)
            if width < 1000 or height < 600:
                raise AssertionError(f"图片分辨率过低：{width}x{height}")
            path = args.output_dir / "paper-illustration.png"
            path.write_bytes(image_bytes)
            evidence["generated_image"] = (
                f"{mime}, {width}x{height}, {len(image_bytes):,} bytes"
            )
            return image_bytes, mime

        generated = timed("论文插图生成", make_image, results)

    if generated:
        def understand_image():
            image_bytes, mime = generated
            answer = chat_complete(
                [
                    {
                        "role": "user",
                        "content": multimodal_content(
                            "用中文概括这张科研图表达的流程，并列出你能读到的三个图中文字标签。",
                            [{"bytes": image_bytes, "mime": mime}],
                        ),
                    }
                ],
                model=OPENAI_DEFAULT_TEXT_MODEL,
            ).strip()
            if len(answer) < 80 or len(re.findall(r"[\u4e00-\u9fff]", answer)) < 30:
                raise AssertionError(f"图片理解回答过短：{answer}")
            evidence["vision"] = answer[:800]
            return answer

        timed("生成图片的视觉理解", understand_image, results)

        def translate_image():
            image_bytes, mime = generated
            edited_bytes, edited_mime = edit_image(
                image_bytes,
                mime,
                "保持构图、颜色、箭头和图形不变，把图内所有英文标签准确翻译为简体中文。",
                model=OPENAI_DEFAULT_IMAGE_MODEL,
            )
            width, height = png_info(edited_bytes)
            if hashlib.sha256(edited_bytes).digest() == hashlib.sha256(image_bytes).digest():
                raise AssertionError("编辑接口返回了与原图完全相同的内容")
            path = args.output_dir / "paper-illustration-zh.png"
            path.write_bytes(edited_bytes)
            evidence["edited_image"] = (
                f"{edited_mime}, {width}x{height}, {len(edited_bytes):,} bytes"
            )
            return edited_bytes, edited_mime

        edited = timed("图片中文翻译/编辑", translate_image, results)

        if edited:
            def verify_edit():
                edited_bytes, edited_mime = edited
                answer = chat_complete(
                    [
                        {
                            "role": "user",
                            "content": multimodal_content(
                                "检查这张图：主要标签是否已经是中文？列出你能读到的中文标签。",
                                [{"bytes": edited_bytes, "mime": edited_mime}],
                            ),
                        }
                    ],
                    model=OPENAI_DEFAULT_TEXT_MODEL,
                ).strip()
                if len(re.findall(r"[\u4e00-\u9fff]", answer)) < 10:
                    raise AssertionError(f"无法确认图中文字已转换为中文：{answer}")
                evidence["edit_verification"] = answer[:800]
                return answer

            timed("编辑结果视觉复核", verify_edit, results)

    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    lines = [
        "# OpenAI-compatible API 端到端测试报告",
        "",
        f"- 时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- Base URL：`{OPENAI_BASE_URL}`",
        f"- 文本模型：`{OPENAI_DEFAULT_TEXT_MODEL}`",
        f"- 图片模型：`{OPENAI_DEFAULT_IMAGE_MODEL}`",
        f"- 结果：{passed} 通过，{failed} 失败",
        "",
        "## 检查项",
        "",
        "| 检查 | 结果 | 耗时 | 错误 |",
        "|---|---:|---:|---|",
    ]
    for item in results:
        error = str(item.get("error", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {item['name']} | {'通过' if item['ok'] else '失败'} | "
            f"{item['seconds']:.1f}s | {error} |"
        )
    lines.extend(["", "## 输出证据", ""])
    for key, value in evidence.items():
        lines.extend([f"### {key}", "", str(value), ""])

    report_path = args.output_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[DONE ] {passed}/{len(results)} passed; report={report_path}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
