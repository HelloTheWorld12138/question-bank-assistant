from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from app import config, storage
from app.errors import AppError
from app.math_ocr import detect_formula_items
from app.services.documents import IMAGE_MARKDOWN_RE, find_pandoc


def next_question_id(block_code: str, type_code: str) -> str:
    if block_code not in config.BLOCKS:
        raise AppError("未知板块代码")
    if type_code not in config.TYPES:
        raise AppError("未知类型代码")
    prefix = f"{block_code}{type_code}"
    index = storage.load_index()
    next_number = index.get(prefix, 0) + 1
    index[prefix] = next_number
    storage.save_index(index)
    return f"{prefix}{next_number:04d}"


async def save_uploads(question_id: str, uploads: list[UploadFile], start_index: int = 1) -> list[str]:
    saved: list[str] = []
    image_count = start_index
    doc_count = 1
    for upload in uploads:
        if not upload.filename:
            continue
        source_name = Path(upload.filename)
        ext = source_name.suffix.lower() or ".bin"
        if ext in config.IMAGE_EXTENSIONS:
            filename = f"{question_id}_{image_count:02d}{ext}"
            image_count += 1
            saved.append(filename)
        else:
            filename = f"{question_id}_附件{doc_count}{ext}"
            doc_count += 1
        target = config.ASSETS_DIR / filename
        with target.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
    return saved


def finalize_draft_images(question_id: str, draft_id: str, start_index: int = 1) -> tuple[list[str], dict[str, str]]:
    if not draft_id or not re.fullmatch(r"[a-f0-9-]{36}", draft_id):
        return [], {}
    draft_dir = config.DRAFT_ASSETS_DIR / draft_id
    if not draft_dir.exists():
        return [], {}

    saved: list[str] = []
    link_map: dict[str, str] = {}
    image_count = start_index
    for source in sorted(draft_dir.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in config.IMAGE_EXTENSIONS:
            continue
        filename = f"{question_id}_{image_count:02d}{source.suffix.lower()}"
        shutil.copy2(source, config.ASSETS_DIR / filename)
        saved.append(filename)
        relative = source.relative_to(draft_dir).as_posix()
        link_map[relative] = filename
        link_map[source.name] = filename
        image_count += 1

    shutil.rmtree(draft_dir, ignore_errors=True)
    return saved, link_map


def rewrite_draft_image_links(markdown: str, draft_id: str, link_map: dict[str, str]) -> str:
    if not markdown or not draft_id or not link_map:
        return markdown

    def replace(match: re.Match[str]) -> str:
        url = match.group(1)
        key = url.split(f"/draft-assets/{draft_id}/", 1)[-1]
        key = key.split("media/", 1)[-1] if "media/" in key else key
        filename = link_map.get(key.strip()) or link_map.get(Path(key).name)
        if not filename:
            return match.group(0)
        return match.group(0).replace(url, f"../assets/{filename}")

    return IMAGE_MARKDOWN_RE.sub(replace, markdown)


async def create_question(
    *,
    block_code: str,
    type_code: str,
    difficulty: str = "",
    difficulty_coefficient: str = "",
    year: str = "",
    source: str = "",
    question_text: str,
    answer_text: str = "",
    analysis_text: str = "",
    knowledge_points: str = "",
    extra_types: str = "",
    remarks: str = "",
    draft_id: str = "",
    files: list[UploadFile] | None = None,
) -> dict[str, Any]:
    storage.ensure_dirs()
    if draft_id and re.fullmatch(r"[a-f0-9-]{36}", draft_id):
        draft_dir = config.DRAFT_ASSETS_DIR / draft_id
        if draft_dir.exists():
            submitted_markdown = "\n\n".join([question_text, answer_text, analysis_text])
            unresolved_formulas = detect_formula_items(submitted_markdown, draft_dir, draft_id)
            if unresolved_formulas:
                names = "、".join(item["name"] for item in unresolved_formulas[:3])
                raise AppError(f"还有疑似公式图片未替换为 LaTeX，不能入库：{names}")

    question_id = next_question_id(block_code, type_code)
    images, draft_image_map = finalize_draft_images(question_id, draft_id)
    images.extend(await save_uploads(question_id, files or [], start_index=len(images) + 1))
    question_text = rewrite_draft_image_links(question_text, draft_id, draft_image_map)
    answer_text = rewrite_draft_image_links(answer_text, draft_id, draft_image_map)
    analysis_text = rewrite_draft_image_links(analysis_text, draft_id, draft_image_map)

    main_type = config.TYPES[type_code]
    type_names = [main_type]
    for item in storage.normalize_lines(extra_types):
        if item not in type_names:
            type_names.append(item)
    metadata = {
        "id": question_id,
        "板块": config.BLOCKS[block_code],
        "主类型": main_type,
        "类型": type_names,
        "知识点": storage.normalize_lines(knowledge_points),
        "难度系数": (difficulty_coefficient or difficulty or "").strip(),
        "年份": (year or "").strip(),
        "来源": source.strip(),
        "解析来源": "教师上传",
        "图片": images,
    }
    sections = {"题目": question_text, "答案": answer_text, "解析": analysis_text, "备注": remarks}
    path = storage.write_question(question_id, metadata, sections)
    try:
        display_path = str(path.relative_to(config.ROOT))
    except ValueError:
        display_path = str(path)
    return {"id": question_id, "file": display_path, "images": images}


def matches(value: Any, expected: str) -> bool:
    if not expected:
        return True
    if isinstance(value, list):
        return any(expected in str(item) for item in value)
    return expected in str(value)


def search_questions(
    *,
    block: str = "",
    main_type: str = "",
    difficulty: str = "",
    year: str = "",
    source: str = "",
    knowledge: str = "",
) -> list[dict[str, Any]]:
    results = []
    for item in storage.read_all_questions():
        if not matches(item["板块"], block):
            continue
        if not matches(item["主类型"], main_type):
            continue
        if not matches(item["难度系数"], difficulty):
            continue
        if not matches(item["年份"], year):
            continue
        if not matches(item["来源"], source):
            continue
        if not matches(item["知识点"], knowledge):
            continue
        results.append(item)
    return results


def export_exam(payload: dict[str, Any]) -> dict[str, Any]:
    ids = payload.get("ids") or []
    mode = payload.get("mode") or "questions"
    if not ids:
        raise AppError("请先选择题目")
    if mode not in {"questions", "answers", "analysis"}:
        raise AppError("未知导出模式")

    parts: list[str] = ["# 试卷\n"]
    missing: list[str] = []
    for question_id in ids:
        try:
            metadata, sections = storage.read_question(str(question_id))
        except AppError:
            missing.append(str(question_id))
            continue
        title = metadata.get("id", question_id)
        parts.append(f"\n## 【{title}】\n")
        parts.append(sections.get("题目", "").strip() + "\n")
        section_blob = "\n".join(sections.values())
        for image in metadata.get("图片", []) or []:
            if str(image) not in section_blob:
                parts.append(f"\n![]({(config.ASSETS_DIR / image).as_posix()})\n")
        if mode in {"answers", "analysis"}:
            parts.extend(["\n### 答案\n", sections.get("答案", "").strip() + "\n"])
        if mode == "analysis":
            parts.extend(["\n### 解析\n", sections.get("解析", "").strip() + "\n"])

    exam_md = config.EXPORT_DIR / "exam.md"
    exam_docx = config.EXPORT_DIR / "exam.docx"
    exam_md.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")

    pandoc_path = find_pandoc()
    docx_created = False
    pandoc_message = ""
    if pandoc_path:
        completed = subprocess.run(
            [pandoc_path, str(exam_md), "-o", str(exam_docx)],
            cwd=str(config.ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            docx_created = True
        else:
            pandoc_message = completed.stderr.strip() or "Pandoc 导出失败"
    else:
        pandoc_message = "未检测到 Pandoc，已生成 exam.md；如需 Word，请先安装 Pandoc。"

    return {
        "exam_md": "exports/exam.md",
        "exam_docx": "exports/exam.docx" if docx_created else "",
        "docx_created": docx_created,
        "pandoc_message": pandoc_message,
        "missing": missing,
    }
