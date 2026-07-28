from __future__ import annotations

import json
import re
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from PIL import Image, ImageOps

from app import config, storage
from app.content import normalize_line_breaks
from app.errors import AppError
from app.math_ocr import detect_formula_items, math_delimiter_issue
from app.processes import hidden_process_kwargs
from app.services import office
from app.services.documents import IMAGE_MARKDOWN_RE, find_pandoc, normalize_html_images


RASTER_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}
IMAGE_WITH_ATTRIBUTES_RE = re.compile(
    r"(!\[[^\]]*\]\([^)]+\))(?P<spacing>[ \t]*)(?P<attributes>\{[^}\n]*\})?"
)


@contextmanager
def reserve_question_id(block_code: str, type_code: str):
    if block_code not in config.BLOCKS:
        raise AppError("未知板块代码")
    if type_code not in config.TYPES:
        raise AppError("未知类型代码")
    prefix = f"{block_code}{type_code}"
    with storage.file_lock(config.INDEX_LOCK_FILE):
        index = storage.load_index()
        next_number = index.get(prefix, 0) + 1
        question_id = f"{prefix}{next_number:04d}"
        while storage.question_path(question_id).exists():
            next_number += 1
            question_id = f"{prefix}{next_number:04d}"
        yield question_id
        index[prefix] = next_number
        storage.save_index(index)


def next_question_id(block_code: str, type_code: str) -> str:
    with reserve_question_id(block_code, type_code) as question_id:
        return question_id


def _save_raster_as_png(source: Any, target: Path) -> None:
    with Image.open(source) as opened:
        opened.seek(0)
        image = ImageOps.exif_transpose(opened)
        if image.mode in {"CMYK", "P"}:
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")
        elif image.mode not in {"1", "L", "LA", "RGB", "RGBA"}:
            image = image.convert("RGB")
        image.save(target, format="PNG", optimize=True, dpi=(150, 150))


def _image_target_name(question_id: str, number: int, source: Path) -> str:
    suffix = ".png" if source.suffix.lower() in RASTER_IMAGE_EXTENSIONS else source.suffix.lower()
    return f"{question_id}_{number:02d}{suffix}"


async def save_uploads(
    question_id: str,
    uploads: list[UploadFile],
    start_index: int = 1,
    upload_tokens: list[str] | None = None,
    referenced_markdown: str = "",
) -> tuple[list[str], dict[str, str]]:
    saved: list[str] = []
    link_map: dict[str, str] = {}
    image_count = start_index
    doc_count = 1
    tokens = upload_tokens or []
    for upload_index, upload in enumerate(uploads):
        if not upload.filename:
            continue
        source_name = Path(upload.filename)
        ext = source_name.suffix.lower() or ".bin"
        token = tokens[upload_index] if upload_index < len(tokens) else ""
        if ext in config.IMAGE_EXTENSIONS:
            if token and token not in referenced_markdown:
                continue
            filename = _image_target_name(question_id, image_count, source_name)
            image_count += 1
            saved.append(filename)
        else:
            filename = f"{question_id}_附件{doc_count}{ext}"
            doc_count += 1
        target = config.ASSETS_DIR / filename
        upload.file.seek(0)
        if ext in RASTER_IMAGE_EXTENSIONS:
            _save_raster_as_png(upload.file, target)
        else:
            with target.open("wb") as buffer:
                shutil.copyfileobj(upload.file, buffer)
        if token and ext in config.IMAGE_EXTENSIONS:
            link_map[token] = filename
    return saved, link_map


def finalize_draft_images(
    question_id: str,
    draft_id: str,
    referenced_markdown: str,
    start_index: int = 1,
) -> tuple[list[str], dict[str, str]]:
    if not draft_id or not re.fullmatch(r"[a-f0-9-]{36}", draft_id):
        return [], {}
    draft_dir = config.DRAFT_ASSETS_DIR / draft_id
    if not draft_dir.exists():
        return [], {}

    saved: list[str] = []
    link_map: dict[str, str] = {}
    image_count = start_index
    referenced_names = {
        Path(match.group(1).split("?", 1)[0].replace("\\", "/")).name
        for match in IMAGE_MARKDOWN_RE.finditer(referenced_markdown)
    }
    for source in sorted(draft_dir.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in config.IMAGE_EXTENSIONS:
            continue
        relative = source.relative_to(draft_dir).as_posix()
        if any(part.startswith(".") for part in source.relative_to(draft_dir).parts):
            continue
        if source.name not in referenced_names and relative not in referenced_names:
            continue
        filename = _image_target_name(question_id, image_count, source)
        target = config.ASSETS_DIR / filename
        if source.suffix.lower() in RASTER_IMAGE_EXTENSIONS:
            _save_raster_as_png(source, target)
        else:
            shutil.copy2(source, target)
        saved.append(filename)
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


def rewrite_upload_image_links(markdown: str, link_map: dict[str, str]) -> str:
    text = markdown
    for token, filename in link_map.items():
        text = text.replace(f"]({token})", f"](../assets/{filename})")
    return text


def normalize_approved_formula_images(value: str | list[str] | None) -> set[str]:
    if isinstance(value, list):
        items = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return set()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [item for item in raw.splitlines() if item.strip()]
        items = parsed if isinstance(parsed, list) else []
    approved: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        approved.add(text)
        approved.add(Path(text.split("?", 1)[0].replace("\\", "/")).name)
    return approved


def ensure_valid_math(*sections: str) -> None:
    for name, content in zip(("题目", "答案", "解析", "备注"), sections):
        issue = math_delimiter_issue(content)
        if issue:
            raise AppError(f"{name}中的公式格式需要检查：{issue}")


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
    question_type: str = "",
    remarks: str = "",
    draft_id: str = "",
    files: list[UploadFile] | None = None,
    approved_formula_images: str | list[str] | None = None,
    upload_image_tokens: str | list[str] | None = None,
) -> dict[str, Any]:
    storage.ensure_dirs()
    if question_type and question_type not in config.QUESTION_TYPES:
        raise AppError("未知题型")
    question_text = normalize_html_images(question_text)
    answer_text = normalize_html_images(answer_text)
    analysis_text = normalize_html_images(analysis_text)
    remarks = normalize_html_images(remarks)
    ensure_valid_math(question_text, answer_text, analysis_text, remarks)
    approved = normalize_approved_formula_images(approved_formula_images)
    if draft_id and re.fullmatch(r"[a-f0-9-]{36}", draft_id):
        draft_dir = config.DRAFT_ASSETS_DIR / draft_id
        if draft_dir.exists():
            submitted_markdown = "\n\n".join([question_text, answer_text, analysis_text])
            unresolved_formulas = [
                item
                for item in detect_formula_items(submitted_markdown, draft_dir, draft_id)
                if item["url"] not in approved and item["name"] not in approved
            ]
            if unresolved_formulas:
                names = "、".join(item["name"] for item in unresolved_formulas[:3])
                raise AppError(f"请先处理这些疑似公式图片：{names}")

    with reserve_question_id(block_code, type_code) as question_id:
        submitted_markdown = "\n\n".join([question_text, answer_text, analysis_text, remarks])
        images, draft_image_map = finalize_draft_images(
            question_id,
            draft_id,
            submitted_markdown,
        )
        if isinstance(upload_image_tokens, str):
            try:
                parsed_tokens = json.loads(upload_image_tokens)
            except json.JSONDecodeError:
                parsed_tokens = []
            tokens = [str(item or "") for item in parsed_tokens] if isinstance(parsed_tokens, list) else []
        elif isinstance(upload_image_tokens, list):
            tokens = [str(item or "") for item in upload_image_tokens]
        else:
            tokens = []
        uploaded_images, upload_image_map = await save_uploads(
            question_id,
            files or [],
            start_index=len(images) + 1,
            upload_tokens=tokens,
            referenced_markdown=submitted_markdown,
        )
        images.extend(uploaded_images)
        question_text = rewrite_draft_image_links(question_text, draft_id, draft_image_map)
        answer_text = rewrite_draft_image_links(answer_text, draft_id, draft_image_map)
        analysis_text = rewrite_draft_image_links(analysis_text, draft_id, draft_image_map)
        remarks = rewrite_draft_image_links(remarks, draft_id, draft_image_map)
        question_text = rewrite_upload_image_links(question_text, upload_image_map)
        answer_text = rewrite_upload_image_links(answer_text, upload_image_map)
        analysis_text = rewrite_upload_image_links(analysis_text, upload_image_map)
        remarks = rewrite_upload_image_links(remarks, upload_image_map)

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
            "题型": question_type,
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
    question_type: str = "",
    query: str = "",
    sort_by: str = "id",
    sort_order: str = "asc",
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
        if not matches(item["题型"], question_type):
            continue
        if query:
            searchable = "\n".join(
                str(item.get(key, ""))
                for key in ("id", "题目", "答案", "解析", "备注", "来源", "知识点", "类型")
            )
            if query.casefold() not in searchable.casefold():
                continue
        results.append(item)

    sort_keys = {
        "id": lambda item: str(item.get("id", "")),
        "year": lambda item: str(item.get("年份", "")),
        "updated": lambda item: str(item.get("更新时间", "")),
        "difficulty": lambda item: _numeric_sort_value(item.get("难度系数", "")),
    }
    key = sort_keys.get(sort_by)
    if key is None:
        raise AppError("未知排序方式")
    if sort_order not in {"asc", "desc"}:
        raise AppError("未知排序方向")
    results.sort(key=key, reverse=sort_order == "desc")
    return results


def _numeric_sort_value(value: Any) -> tuple[int, float | str]:
    try:
        return (0, float(str(value).strip()))
    except (TypeError, ValueError):
        return (1, str(value or ""))


def update_question(question_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    metadata, sections = storage.read_question(question_id)
    previous_images = {Path(str(item)).name for item in metadata.get("图片", []) or []}
    metadata_updates = payload.get("metadata") or {}
    section_updates = payload.get("sections") or {}
    if not isinstance(metadata_updates, dict) or not isinstance(section_updates, dict):
        raise AppError("题目更新格式不正确")
    if metadata_updates.get("id") not in (None, "", question_id):
        raise AppError("题号不能通过普通编辑修改")
    expected_block = config.BLOCKS.get(question_id[:2])
    expected_main_type = config.TYPES.get(question_id[2:4])
    if metadata_updates.get("板块") not in (None, "", expected_block):
        raise AppError("板块与永久题号不一致，不能通过普通编辑修改")
    if metadata_updates.get("主类型") not in (None, "", expected_main_type):
        raise AppError("主类型与永久题号不一致，不能通过普通编辑修改")

    allowed_metadata = {
        "板块",
        "主类型",
        "类型",
        "知识点",
        "难度系数",
        "年份",
        "来源",
        "解析来源",
        "题型",
        "图片",
    }
    for key in allowed_metadata:
        if key in metadata_updates:
            metadata[key] = metadata_updates[key]
    metadata["id"] = question_id

    for key in storage.SECTION_NAMES:
        if key in section_updates:
            sections[key] = normalize_html_images(str(section_updates[key] or ""))
    ensure_valid_math(*(sections.get(key, "") for key in storage.SECTION_NAMES))

    next_images = {Path(str(item)).name for item in metadata_updates.get("图片", previous_images) or []}
    if not next_images.issubset(previous_images):
        raise AppError("不能通过普通编辑添加未知图片")
    path = storage.write_question(question_id, metadata, sections)
    for filename in previous_images - next_images:
        if filename.startswith(f"{question_id}_"):
            (config.ASSETS_DIR / filename).unlink(missing_ok=True)
    return {"id": question_id, "file": str(path), "metadata": storage.read_question(question_id)[0]}


def copy_question(question_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    source_metadata, source_sections = storage.read_question(question_id)
    options = payload or {}
    block_code = str(options.get("block_code") or question_id[:2])
    type_code = str(options.get("type_code") or question_id[2:4])
    if block_code not in config.BLOCKS or type_code not in config.TYPES:
        raise AppError("复制题目的板块或主类型无效")

    created_assets: list[Path] = []
    with reserve_question_id(block_code, type_code) as copied_id:
        try:
            copied_images: list[str] = []
            replacements: dict[str, str] = {}
            for index, raw_name in enumerate(source_metadata.get("图片", []) or [], start=1):
                source_name = Path(str(raw_name)).name
                source = config.ASSETS_DIR / source_name
                if not source.exists():
                    raise AppError(f"原题图片不存在，无法复制：{source_name}")
                copied_name = f"{copied_id}_{index:02d}{source.suffix.lower()}"
                target = config.ASSETS_DIR / copied_name
                shutil.copy2(source, target)
                created_assets.append(target)
                copied_images.append(copied_name)
                replacements[source_name] = copied_name

            sections = dict(source_sections)
            for section_name, content in sections.items():
                for old_name, new_name in replacements.items():
                    content = content.replace(old_name, new_name)
                sections[section_name] = content

            metadata = dict(source_metadata)
            metadata.pop("创建时间", None)
            metadata.pop("更新时间", None)
            metadata.update(
                {
                    "id": copied_id,
                    "板块": config.BLOCKS[block_code],
                    "主类型": config.TYPES[type_code],
                    "图片": copied_images,
                    "复制自": question_id,
                }
            )
            types = [str(item) for item in metadata.get("类型", []) or [] if str(item).strip()]
            main_type = config.TYPES[type_code]
            metadata["类型"] = [main_type, *[item for item in types if item != main_type]]
            path = storage.write_question(copied_id, metadata, sections)
        except Exception:
            for asset in created_assets:
                asset.unlink(missing_ok=True)
            storage.question_path(copied_id).unlink(missing_ok=True)
            raise
    return {"id": copied_id, "source_id": question_id, "file": str(path), "images": copied_images}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[\n,，]+", value) if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise AppError("批量修改的标签格式不正确")


def batch_update_questions(payload: dict[str, Any]) -> dict[str, Any]:
    ids = [storage.validate_question_id(item) for item in payload.get("ids", [])]
    if not ids:
        raise AppError("请先选择要批量修改的题目")
    add_types = _string_list(payload.get("add_types"))
    remove_types = set(_string_list(payload.get("remove_types")))
    add_knowledge = _string_list(payload.get("add_knowledge"))
    remove_knowledge = set(_string_list(payload.get("remove_knowledge")))
    question_type = payload.get("question_type")
    if question_type not in (None, "", *config.QUESTION_TYPES):
        raise AppError("未知题型")

    originals: dict[str, str] = {}
    updated: list[str] = []
    try:
        for question_id in ids:
            path = storage.question_path(question_id)
            if not path.exists():
                raise AppError(f"题目不存在：{question_id}")
            originals[question_id] = path.read_text(encoding="utf-8")
            metadata, sections = storage.read_question(question_id)
            main_type = str(metadata.get("主类型") or config.TYPES.get(question_id[2:4], ""))
            types = [
                item
                for item in _string_list(metadata.get("类型"))
                if item not in remove_types and item != main_type
            ]
            metadata["类型"] = [main_type, *types]
            for item in add_types:
                if item not in metadata["类型"]:
                    metadata["类型"].append(item)

            knowledge = [
                item for item in _string_list(metadata.get("知识点")) if item not in remove_knowledge
            ]
            for item in add_knowledge:
                if item not in knowledge:
                    knowledge.append(item)
            metadata["知识点"] = knowledge
            if question_type not in (None, ""):
                metadata["题型"] = question_type
            storage.write_question(question_id, metadata, sections)
            updated.append(question_id)
    except Exception:
        for question_id, content in originals.items():
            storage.atomic_write_text(storage.question_path(question_id), content)
        raise
    return {"updated": updated, "count": len(updated)}


def rewrite_export_image_links(markdown: str, image_names: list[str]) -> str:
    known_images = {Path(name).name for name in image_names}

    def replace(match: re.Match[str]) -> str:
        raw_url = match.group(1).strip()
        filename = Path(raw_url.replace("\\", "/")).name
        if filename not in known_images:
            return match.group(0)
        return match.group(0).replace(raw_url, (config.ASSETS_DIR / filename).as_posix())

    rewritten = IMAGE_MARKDOWN_RE.sub(replace, markdown)

    def add_default_width(match: re.Match[str]) -> str:
        if match.group("attributes"):
            return match.group(0)
        return f"{match.group(1)}{{width=70%}}"

    return IMAGE_WITH_ATTRIBUTES_RE.sub(add_default_width, rewritten)


def page_break_markdown() -> str:
    return (
        "\n```{=openxml}\n"
        '<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n'
        "```\n"
    )


def resolve_exam_template(template_key: str) -> tuple[Path, dict[str, str]]:
    spec = config.EXAM_TEMPLATES.get(template_key)
    if not spec:
        raise AppError("未知试卷模板")
    path = config.exam_template_path(template_key)
    if not path.is_file():
        raise AppError("试卷模板不存在，请在维护区恢复默认模板")
    return path, spec


def export_exam(payload: dict[str, Any]) -> dict[str, Any]:
    ids = payload.get("ids") or []
    mode = payload.get("mode") or "questions"
    if not ids:
        raise AppError("请先选择题目")
    if mode not in {"questions", "answers", "analysis", "answer_sheet", "analysis_sheet"}:
        raise AppError("未知导出模式")

    exam_title = str(payload.get("title") or "试卷").strip() or "试卷"
    duration = str(payload.get("duration") or "").strip()
    total_score = str(payload.get("total_score") or "").strip()
    template_key = str(payload.get("template") or "a4_single").strip()
    template_path, template_spec = resolve_exam_template(template_key)
    show_ids = payload.get("show_ids", True) is not False
    answers_new_page = payload.get("answers_new_page", True) is not False
    group_by_question_type = payload.get("group_by_question_type", False) is True
    display_labels = payload.get("display_labels") or {}
    if not isinstance(display_labels, dict):
        raise AppError("展示题号格式不正确")
    class_name = str(payload.get("class_name") or "").strip()
    student_fields = payload.get("student_fields", False) is True

    title_yaml = json.dumps(exam_title, ensure_ascii=False)
    parts: list[str] = ["---", f"title: {title_yaml}", "---", ""]
    exam_meta = []
    if duration:
        exam_meta.append(f"考试时间：{duration}")
    if total_score:
        exam_meta.append(f"满分：{total_score}")
    if class_name:
        exam_meta.append(f"班级：{class_name}")
    if exam_meta:
        parts.extend([f"**{'　　'.join(exam_meta)}**", ""])
    if student_fields:
        parts.extend(["**姓名：__________　学号：__________　得分：__________**", ""])
    include_questions = mode in {"questions", "answers", "analysis"}
    include_answers = mode in {"answers", "analysis", "answer_sheet", "analysis_sheet"}
    include_analysis = mode in {"analysis", "analysis_sheet"}
    if include_questions:
        parts.extend(["# 题目", ""])
    elif mode == "answer_sheet":
        parts.extend(["# 参考答案", ""])
    else:
        parts.extend(["# 答案与解析", ""])

    missing: list[str] = []
    exported_questions: list[dict[str, str]] = []
    previous_question_type = ""
    for number, question_id in enumerate(ids, start=1):
        try:
            metadata, sections = storage.read_question(str(question_id))
        except AppError:
            missing.append(str(question_id))
            continue
        question_label = metadata.get("id", question_id)
        image_names = [str(item) for item in metadata.get("图片", []) or []]
        question_text = rewrite_export_image_links(
            normalize_line_breaks(sections.get("题目", "")),
            image_names,
        )
        answer_text = rewrite_export_image_links(
            normalize_line_breaks(sections.get("答案", "")),
            image_names,
        )
        analysis_text = rewrite_export_image_links(
            normalize_line_breaks(sections.get("解析", "")),
            image_names,
        )
        display_label = str(display_labels.get(str(question_id)) or number).strip()[:20]
        label = f"{display_label}. 【{question_label}】" if show_ids else f"{display_label}."
        question_type = str(metadata.get("题型") or "其他")
        if include_questions and group_by_question_type and question_type != previous_question_type:
            parts.extend([f"## {question_type}", ""])
            previous_question_type = question_type
        if include_questions:
            parts.extend([f"### {label}" if group_by_question_type else f"## {label}", "", question_text.strip(), ""])
            section_blob = "\n".join(sections.values())
            for image in image_names:
                if str(image) not in section_blob:
                    parts.extend([f"![]({(config.ASSETS_DIR / image).as_posix()}){{width=70%}}", ""])
        exported_questions.append(
            {
                "label": label,
                "answer": answer_text.strip() or "（未提供答案）",
                "analysis": analysis_text.strip() or "（未提供解析）",
                "question_type": question_type,
            }
        )

    if include_answers and include_questions:
        if answers_new_page:
            parts.append(page_break_markdown())
        parts.extend(["# 参考答案", ""])
        for item in exported_questions:
            parts.extend([f"## {item['label']}", "", item["answer"], ""])
    elif mode in {"answer_sheet", "analysis_sheet"}:
        for item in exported_questions:
            parts.extend([f"## {item['label']}", "", item["answer"], ""])

    if include_analysis:
        if answers_new_page:
            parts.append(page_break_markdown())
        parts.extend(["# 解析", ""])
        for item in exported_questions:
            parts.extend([f"## {item['label']}", "", item["analysis"], ""])

    safe_title = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", exam_title).strip("_") or "试卷"
    mode_name = {
        "questions": "题目",
        "answers": "题目答案",
        "analysis": "题目答案解析",
        "answer_sheet": "答案",
        "analysis_sheet": "解析",
    }[mode]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    stem = f"{timestamp}_{safe_title}_{mode_name}"
    exam_md = config.EXPORT_DIR / f"{stem}.md"
    exam_docx = config.EXPORT_DIR / f"{stem}.docx"
    exam_md.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")

    pandoc_path = find_pandoc()
    docx_created = False
    pandoc_message = ""
    office_message = ""
    validation: dict[str, Any] = {"performed": False, "ok": None, "message": ""}
    issue_report: dict[str, Any] = {"count": 0, "issues": []}
    preview_filename = ""
    office_status = office.officecli_status()
    export_engine = "markdown"
    if pandoc_path:
        completed = subprocess.run(
            [
                pandoc_path,
                str(exam_md),
                "--from=markdown+tex_math_dollars+raw_attribute+link_attributes+hard_line_breaks",
                "--standalone",
                f"--resource-path={config.ASSETS_DIR}",
                f"--reference-doc={template_path}",
                "-o",
                str(exam_docx),
            ],
            cwd=str(config.ROOT),
            capture_output=True,
            text=True,
            check=False,
            **hidden_process_kwargs(),
        )
        if completed.returncode == 0:
            docx_created = True
            export_engine = "pandoc"
        else:
            pandoc_message = "Word 生成失败，请检查题目中的公式和图片。"
    else:
        pandoc_message = "Word 组件不可用，已生成备用文件。请重新启动应用后再试。"

    if docx_created and office_status.get("available"):
        export_engine = "pandoc+officecli"
        try:
            validation = {"performed": True, **office.validate_document(exam_docx)}
            issue_report = office.inspect_issues(exam_docx)
            # Reading the root once verifies that OfficeCLI can parse the
            # generated structure, not only that the ZIP package is valid.
            office.read_document_structure(exam_docx, depth=1)
            preview_path = config.EXPORT_DIR / f"{stem}_预览.html"
            office.render_html(exam_docx, preview_path)
            preview_filename = preview_path.name
        except AppError as exc:
            office_message = f"Word 已生成，但自动排版检查未完成：{exc.message}"
    elif docx_created:
        office_message = "Word 已生成；本次未执行自动排版检查。"

    return {
        "exam_md": f"exports/{exam_md.name}",
        "exam_docx": f"exports/{exam_docx.name}" if docx_created else "",
        "exam_md_filename": exam_md.name,
        "exam_docx_filename": exam_docx.name if docx_created else "",
        "docx_created": docx_created,
        "pandoc_message": pandoc_message,
        "office_message": office_message,
        "officecli": office_status,
        "validation": validation,
        "issues": issue_report,
        "preview_filename": preview_filename,
        "template": template_key,
        "template_name": template_spec["name"],
        "engine": export_engine,
        "missing": missing,
        "kind": {
            "questions": "questions",
            "answers": "combined_answers",
            "analysis": "combined_analysis",
            "answer_sheet": "answers",
            "analysis_sheet": "analysis",
        }[mode],
    }


def export_exam_set(payload: dict[str, Any]) -> dict[str, Any]:
    files = []
    for mode in ("questions", "answer_sheet", "analysis_sheet"):
        item_payload = dict(payload)
        item_payload["mode"] = mode
        exported = export_exam(item_payload)
        files.append(exported)
    return {"files": files, "count": len(files)}
