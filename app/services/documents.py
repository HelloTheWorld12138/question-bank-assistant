from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app import config
from app.agent import opencode_available, run_opencode
from app.errors import AppError
from app.math_ocr import detect_formula_items, formula_ocr_available, has_editable_math
from app.storage import ensure_dirs


IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def find_pandoc() -> str | None:
    system_pandoc = shutil.which("pandoc")
    if system_pandoc:
        return system_pandoc
    if config.LOCAL_PANDOC.exists():
        return str(config.LOCAL_PANDOC)
    return None


def strip_markdown_images(markdown: str) -> str:
    text = IMAGE_MARKDOWN_RE.sub("", markdown)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def normalize_converted_markdown(markdown: str, draft_id: str) -> str:
    markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
    # Pandoc's GFM writer wraps Word/OMML inline equations as $`...`$ and
    # display equations as fenced `math` blocks. Normalize both forms so the
    # browser preview, Markdown source and DOCX export share one syntax.
    markdown = re.sub(r"\$`([^`\n]+)`\$", r"$\1$", markdown)
    markdown = re.sub(
        r"```[ \t]*math[ \t]*\n(.*?)\n```",
        lambda match: f"$$\n{match.group(1).strip()}\n$$",
        markdown,
        flags=re.S,
    )
    if draft_id:
        markdown = markdown.replace(
            f"{config.DRAFT_ASSETS_DIR.as_posix()}/{draft_id}/",
            f"/draft-assets/{draft_id}/",
        )
        markdown = markdown.replace(
            f"{config.DRAFT_ASSETS_DIR}\\{draft_id}\\",
            f"/draft-assets/{draft_id}/",
        )
    return re.sub(r"\n{3,}", "\n\n", markdown).strip()


def marker_name(line: str) -> str | None:
    compact = re.sub(r"\s+", "", line.strip().lstrip("#").strip())
    compact = compact.strip("[]【】（）()：:")
    if re.fullmatch(r"(参考)?答案|正确答案|标准答案", compact):
        return "answer"
    if re.fullmatch(r"(答案)?解析|详解|解题过程|思路点拨|解", compact):
        return "analysis"
    return None


def strip_inline_marker(line: str, kind: str) -> str:
    if kind == "answer":
        return re.sub(
            r"^\s*(?:#+\s*)?(?:【?\s*(?:参考)?答案|正确答案|标准答案\s*】?)\s*[:：]?\s*",
            "",
            line,
        ).strip()
    return re.sub(
        r"^\s*(?:#+\s*)?(?:【?\s*(?:答案)?解析|详解|解题过程|思路点拨|解\s*】?)\s*[:：]?\s*",
        "",
        line,
    ).strip()


def extract_inline_answers(text: str) -> str:
    answers: list[str] = []
    for match in re.finditer(r"(?:答案(?:是|为)?|选)\s*[:：]?\s*[（(]\s*([A-H]+)\s*[）)]", text):
        answers.append(match.group(1))
    for match in re.finditer(r"[（(]\s*([A-H])\s*[）)]", text):
        if match.group(1) not in answers:
            answers.append(match.group(1))
    return "、".join(answers)


def parse_question_sections(markdown: str) -> dict[str, str]:
    lines = markdown.splitlines()
    markers: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        kind = marker_name(line)
        if kind:
            markers.append((index, kind))
            continue
        if re.match(r"^\s*(?:#+\s*)?(?:【?\s*(?:参考)?答案|正确答案|标准答案\s*】?)\s*[:：]", line):
            markers.append((index, "answer"))
        elif re.match(r"^\s*(?:#+\s*)?(?:【?\s*(?:答案)?解析|详解|解题过程|思路点拨|解\s*】?)\s*[:：]", line):
            markers.append((index, "analysis"))

    sections = {"question": markdown.strip(), "answer": "", "analysis": ""}
    if markers:
        first_answer = next((item for item in markers if item[1] == "answer"), None)
        first_analysis = next((item for item in markers if item[1] == "analysis"), None)
        first_split = min(item[0] for item in markers)
        sections["question"] = "\n".join(lines[:first_split]).strip()

        if first_answer:
            answer_start = first_answer[0]
            answer_end = first_analysis[0] if first_analysis and first_analysis[0] > answer_start else len(lines)
            answer_lines = lines[answer_start:answer_end]
            if answer_lines:
                answer_lines[0] = strip_inline_marker(answer_lines[0], "answer")
            sections["answer"] = "\n".join(answer_lines).strip()

        if first_analysis:
            analysis_lines = lines[first_analysis[0]:]
            if analysis_lines:
                analysis_lines[0] = strip_inline_marker(analysis_lines[0], "analysis")
            sections["analysis"] = "\n".join(analysis_lines).strip()
    else:
        sections["answer"] = extract_inline_answers(markdown)

    if not sections["answer"] and sections["question"]:
        sections["answer"] = extract_inline_answers(sections["question"])
    return sections


def normalize_agent_metadata(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    def first_value(*keys: str) -> Any:
        for key in keys:
            value = raw.get(key)
            if value not in (None, "", []):
                return value
        return ""

    def text_value(*keys: str) -> str:
        value = first_value(*keys)
        if isinstance(value, list):
            return "\n".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "").strip()

    return {
        "板块": text_value("板块", "模块", "学科板块"),
        "主类型": text_value("主类型", "题型", "类型"),
        "类型": text_value("类型", "附加类型", "标签"),
        "知识点": text_value("知识点", "考点", "知识模块"),
        "难度系数": text_value("难度系数", "难度", "难度值"),
        "年份": text_value("年份", "年级", "年度"),
        "来源": text_value("来源", "出处"),
        "解析来源": text_value("解析来源"),
        "备注": text_value("备注", "说明"),
    }


def inspect_docx_payload(path: Path) -> dict[str, int]:
    counts = {"embedded_objects": 0, "wmf_or_emf": 0}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            lower = name.lower()
            if lower.startswith("word/embeddings/"):
                counts["embedded_objects"] += 1
            if lower.startswith("word/media/") and lower.endswith((".wmf", ".emf")):
                counts["wmf_or_emf"] += 1
    return counts


def convert_docx_path(input_path: Path) -> dict[str, Any]:
    ensure_dirs()
    pandoc_path = find_pandoc()
    if not pandoc_path:
        raise AppError("Word 读取组件不可用，请重新启动应用后再试。")
    if input_path.suffix.lower() != ".docx" or not input_path.is_file():
        raise AppError("请上传 .docx 格式的 Word 文件。")

    draft_id = str(uuid.uuid4())
    draft_dir = config.DRAFT_ASSETS_DIR / draft_id
    draft_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        output_path = temp_path / "output.md"
        docx_payload = inspect_docx_payload(input_path)

        completed = subprocess.run(
            [
                pandoc_path,
                str(input_path),
                "-t",
                "gfm+tex_math_dollars",
                "--wrap=none",
                "--extract-media",
                str(draft_dir),
                "-o",
                str(output_path),
            ],
            cwd=str(config.ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AppError("读取 Word 失败，请确认文件可以正常打开。", status_code=500, code="pandoc_failed")
        markdown = normalize_converted_markdown(output_path.read_text(encoding="utf-8"), draft_id)

    images = []
    for image in sorted(draft_dir.rglob("*")):
        if image.is_file() and image.suffix.lower() in config.IMAGE_EXTENSIONS:
            relative = image.relative_to(draft_dir).as_posix()
            images.append(
                {
                    "name": image.name,
                    "relative_path": relative,
                    "url": f"/draft-assets/{draft_id}/{relative}",
                }
            )

    if not images:
        shutil.rmtree(draft_dir, ignore_errors=True)
        draft_id = ""

    formula_items = detect_formula_items(markdown, draft_dir, draft_id) if draft_id else []
    parsed = parse_question_sections(markdown)
    metadata: dict[str, Any] = {}
    agent_used = False
    warnings = []
    if opencode_available():
        try:
            agent_sections, agent_error = run_opencode(markdown, config.ROOT)
        except Exception:
            agent_sections, agent_error = None, "连接超时或本地智能整理进程异常"
        if agent_sections:
            parsed = {
                "question": agent_sections.get("question") or parsed.get("question", ""),
                "answer": agent_sections.get("answer") or parsed.get("answer", ""),
                "analysis": agent_sections.get("analysis") or parsed.get("analysis", ""),
            }
            metadata = normalize_agent_metadata(agent_sections.get("metadata"))
            agent_used = True
        elif agent_error:
            warnings.append("自动整理暂时不可用，已按原文读取；请检查题目、答案和解析的分段。")
    else:
        warnings.append("内容已按原文读取，请检查题目、答案和解析的分段。")
    if formula_items and not formula_ocr_available():
        warnings.append("发现疑似公式图片，请选择“转为公式”或“保留原图”。")
    if has_editable_math(markdown):
        warnings.append("可编辑公式已保留，请核对显示效果。")
    if docx_payload["embedded_objects"]:
        warnings.append("发现旧版公式或内嵌内容，请在公式图片区逐项检查。")
    if docx_payload["wmf_or_emf"]:
        warnings.append("发现旧格式图片，网页可能无法预览；可保留原图，或在 Word 中另存为 PNG 后重新添加。")

    return {
        "markdown": markdown,
        "text_markdown": strip_markdown_images(markdown),
        "sections": parsed,
        "metadata": metadata,
        "raw_markdown": markdown,
        "draft_id": draft_id,
        "images": images,
        "formula_items": formula_items,
        "formula_ocr_available": formula_ocr_available(),
        "agent_used": agent_used,
        "warnings": warnings,
    }


async def convert_docx(file: UploadFile) -> dict[str, Any]:
    if not file.filename or Path(file.filename).suffix.lower() != ".docx":
        raise AppError("请上传 .docx 格式的 Word 文件。")
    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / "input.docx"
        with input_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return convert_docx_path(input_path)
