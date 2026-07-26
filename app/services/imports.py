from __future__ import annotations

import importlib.util
import json
import math
import re
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pymupdf
from fastapi import UploadFile
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app import config, storage
from app.errors import AppError, NotFoundError
from app.math_ocr import detect_formula_items
from app.services import documents, questions


QUESTION_START_RE = re.compile(
    r"(?m)^[ \t]*(?:第[ \t]*)?(?P<number>\d{1,3})[ \t]*(?:题|[.．、)）])[ \t]*"
)
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_OCR_LOCK = threading.Lock()
_OCR_ENGINE: Any = None


def split_numbered_content(text: str) -> list[dict[str, str]]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    matches = list(QUESTION_START_RE.finditer(normalized))
    if not matches:
        return [{"original_number": "", "content": normalized}] if normalized else []
    preamble = normalized[: matches[0].start()].strip()
    chunks: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        content = normalized[match.end() : end].strip()
        if index == 0 and preamble:
            content = f"{preamble}\n\n{content}".strip()
        chunks.append({"original_number": match.group("number"), "content": content})
    return chunks


def _answer_content(content: str) -> tuple[str, str]:
    parsed = documents.parse_question_sections(content)
    if parsed["answer"] or parsed["analysis"]:
        answer = parsed["answer"] or parsed["question"]
        return answer.strip(), parsed["analysis"].strip()
    return content.strip(), ""


def match_answer_segments(
    questions_segments: list[dict[str, str]],
    answer_segments: list[dict[str, str]],
) -> list[dict[str, str]]:
    answers_by_number = {
        item["original_number"]: item
        for item in answer_segments
        if item.get("original_number")
    }
    same_count = len(questions_segments) == len(answer_segments)
    matched: list[dict[str, str]] = []
    for index, question in enumerate(questions_segments):
        answer_item = answers_by_number.get(question.get("original_number", ""))
        match_kind = "exact"
        if not answer_item and same_count:
            answer_item = answer_segments[index]
            match_kind = "position"
        if answer_item:
            answer, analysis = _answer_content(answer_item["content"])
        else:
            answer, analysis, match_kind = "", "", "unmatched"
        matched.append({**question, "answer": answer, "analysis": analysis, "answer_match": match_kind})
    return matched


def preprocess_image(
    source: Path,
    target: Path,
    *,
    rotation: float = 0,
    crop: dict[str, Any] | None = None,
    perspective: list[list[float]] | None = None,
    enhance: bool = False,
) -> dict[str, int]:
    try:
        image = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
    except (OSError, ValueError) as exc:
        raise AppError("图片无法读取或格式不受支持。") from exc
    if rotation:
        image = image.rotate(-float(rotation), expand=True, fillcolor="white")
    if crop:
        values = [float(crop.get(key, default)) for key, default in (
            ("left", 0), ("top", 0), ("right", 1), ("bottom", 1)
        )]
        left, top, right, bottom = values
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            raise AppError("裁剪范围应位于图片内部。")
        image = image.crop(
            (
                round(left * image.width),
                round(top * image.height),
                round(right * image.width),
                round(bottom * image.height),
            )
        )
    if perspective:
        if len(perspective) != 4 or any(len(point) != 2 for point in perspective):
            raise AppError("透视校正需要四个角点。")
        points = [(float(x), float(y)) for x, y in perspective]
        if all(0 <= value <= 1 for point in points for value in point):
            points = [(x * image.width, y * image.height) for x, y in points]
        top_left, top_right, bottom_right, bottom_left = points
        width = max(
            1,
            round(
                max(
                    math.dist(top_left, top_right),
                    math.dist(bottom_left, bottom_right),
                )
            ),
        )
        height = max(
            1,
            round(
                max(
                    math.dist(top_left, bottom_left),
                    math.dist(top_right, bottom_right),
                )
            ),
        )
        image = image.transform(
            (width, height),
            Image.Transform.QUAD,
            data=(
                top_left[0],
                top_left[1],
                bottom_left[0],
                bottom_left[1],
                bottom_right[0],
                bottom_right[1],
                top_right[0],
                top_right[1],
            ),
            resample=Image.Resampling.BICUBIC,
        )
    if enhance:
        grayscale = ImageOps.grayscale(image)
        grayscale = ImageOps.autocontrast(grayscale, cutoff=1)
        grayscale = grayscale.filter(ImageFilter.MedianFilter(size=3))
        grayscale = ImageEnhance.Contrast(grayscale).enhance(1.25)
        image = grayscale.convert("RGB")
    target.parent.mkdir(parents=True, exist_ok=True)
    output_formats = {
        ".png": "PNG",
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".webp": "WEBP",
        ".bmp": "BMP",
        ".tif": "TIFF",
        ".tiff": "TIFF",
    }
    output_format = output_formats.get(target.suffix.lower())
    if output_format is None:
        raise AppError("该图片格式不能执行旋转、裁剪或增强，请先转换为 PNG。")
    temporary = target.with_name(f".{target.stem}.{uuid.uuid4().hex}{target.suffix.lower()}")
    save_options = {"quality": 95} if output_format in {"JPEG", "WEBP"} else {}
    if output_format == "PNG":
        save_options["optimize"] = True
    image.save(temporary, format=output_format, **save_options)
    temporary.replace(target)
    return {"width": image.width, "height": image.height}


def ocr_available() -> bool:
    return importlib.util.find_spec("paddleocr") is not None and importlib.util.find_spec("paddle") is not None


def ocr_status() -> dict[str, Any]:
    return {
        "available": ocr_available(),
        "engine": "PaddleOCR 3" if ocr_available() else "",
        "offline": True,
        "message": (
            "可以识别扫描件和照片"
            if ocr_available()
            else "Word 和文字版 PDF 可正常导入；照片会保留原图，请人工填写文字"
        ),
    }


def _ocr_result_data(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        data = result
    elif hasattr(result, "json"):
        raw = result.json
        raw = raw() if callable(raw) else raw
        data = json.loads(raw) if isinstance(raw, str) else raw
    else:
        try:
            data = dict(result)
        except (TypeError, ValueError):
            data = {}
    if isinstance(data, dict) and isinstance(data.get("res"), dict):
        return data["res"]
    return data if isinstance(data, dict) else {}


def run_local_ocr(path: Path) -> tuple[str, float]:
    global _OCR_ENGINE
    if not ocr_available():
        return "", 0.0
    with _OCR_LOCK:
        if _OCR_ENGINE is None:
            from paddleocr import PaddleOCR

            _OCR_ENGINE = PaddleOCR(
                lang="ch",
                use_doc_orientation_classify=True,
                use_doc_unwarping=True,
                use_textline_orientation=True,
            )
        results = list(_OCR_ENGINE.predict(str(path)))
    texts: list[str] = []
    scores: list[float] = []
    for result in results:
        data = _ocr_result_data(result)
        texts.extend(str(item).strip() for item in data.get("rec_texts", []) if str(item).strip())
        scores.extend(float(item) for item in data.get("rec_scores", []) if item is not None)
    confidence = sum(scores) / len(scores) if scores else 0.0
    return "\n".join(texts), round(confidence, 4)


async def _save_upload(upload: UploadFile, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with target.open("wb") as output:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                output.close()
                target.unlink(missing_ok=True)
                raise AppError("单个导入文件不能超过 100 MB。")
            output.write(chunk)


def _image_markdown(name: str) -> str:
    return f"![](_source_assets/{name})"


def _extract_pdf_pages(path: Path, work_dir: Path) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise AppError("PDF 无法打开，可能已损坏或设置了不支持的加密。") from exc
    if document.page_count > 300:
        document.close()
        raise AppError("单次最多导入 300 页 PDF，请先拆分文件。")
    try:
        for page_index, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True).strip()
            compact_length = len(re.sub(r"\s+", "", text))
            assets: dict[str, Path] = {}
            warnings: list[str] = []
            source_kind = "digital_pdf"
            confidence = 0.97
            if compact_length >= 20:
                for image_index, image_info in enumerate(page.get_images(full=True), start=1):
                    xref = image_info[0]
                    try:
                        extracted = document.extract_image(xref)
                    except Exception:
                        continue
                    extension = str(extracted.get("ext") or "png").lower()
                    if f".{extension}" not in config.IMAGE_EXTENSIONS:
                        warnings.append(f"跳过一个暂不支持的 PDF 内嵌图片格式：{extension}。")
                        continue
                    name = f"page_{page_index:03d}_image_{image_index:02d}.{extension}"
                    image_path = work_dir / name
                    image_path.write_bytes(extracted["image"])
                    assets[name] = image_path
                    text += f"\n\n{_image_markdown(name)}"
            else:
                source_kind = "scanned_pdf"
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                name = f"page_{page_index:03d}.png"
                image_path = work_dir / name
                pixmap.save(image_path)
                assets[name] = image_path
                if ocr_available():
                    text, confidence = run_local_ocr(image_path)
                    warnings.append("扫描页已识别，请重点核对数字、单位、上下标和公式。")
                else:
                    confidence = 0.0
                    warnings.append("该页未识别到文字，已保留原图，请人工填写。")
                text = f"{text.strip()}\n\n{_image_markdown(name)}".strip()
            pages.append(
                {
                    "page": page_index,
                    "markdown": text,
                    "assets": assets,
                    "source_kind": source_kind,
                    "confidence": confidence,
                    "warnings": warnings,
                }
            )
    finally:
        document.close()
    return pages


def _extract_image_page(path: Path, work_dir: Path) -> list[dict[str, Any]]:
    processed = work_dir / "photo_001.png"
    preprocess_image(path, processed)
    text = ""
    confidence = 0.0
    warnings = []
    if ocr_available():
        text, confidence = run_local_ocr(processed)
        warnings.append("照片已识别，请重点核对数字、单位、上下标和公式。")
    else:
        warnings.append("照片已保留，请人工填写题目文字。")
    return [
        {
            "page": 1,
            "markdown": f"{text.strip()}\n\n{_image_markdown(processed.name)}".strip(),
            "assets": {processed.name: processed},
            "source_kind": "image_ocr" if text else "image_manual",
            "confidence": confidence,
            "warnings": warnings,
        }
    ]


def _source_asset(path_or_url: str, source_dir: Path, assets: dict[str, Path]) -> Path | None:
    name = Path(path_or_url.replace("\\", "/")).name
    if name in assets and assets[name].exists():
        return assets[name]
    matches = list(source_dir.rglob(name))
    return matches[0] if matches else None


def _materialize_chunk(
    chunk: str,
    *,
    source_dir: Path,
    assets: dict[str, Path],
    include_all_assets: bool = False,
) -> tuple[str, str, list[dict[str, str]]]:
    urls = [match.group(1) for match in MARKDOWN_IMAGE_RE.finditer(chunk)]
    if include_all_assets:
        for name in assets:
            if not any(Path(url.replace("\\", "/")).name == name for url in urls):
                urls.append(f"_source_assets/{name}")
                chunk = f"{chunk}\n\n{_image_markdown(name)}".strip()
    resolved = [(url, _source_asset(url, source_dir, assets)) for url in urls]
    resolved = [(url, path) for url, path in resolved if path is not None]
    if not resolved:
        return chunk, "", []

    draft_id = str(uuid.uuid4())
    draft_dir = config.DRAFT_ASSETS_DIR / draft_id
    draft_dir.mkdir(parents=True, exist_ok=True)
    images: list[dict[str, str]] = []
    used_names: set[str] = set()
    for url, source in resolved:
        name = source.name
        stem = source.stem
        counter = 2
        while name in used_names:
            name = f"{stem}_{counter}{source.suffix.lower()}"
            counter += 1
        used_names.add(name)
        target = draft_dir / name
        shutil.copy2(source, target)
        new_url = f"/draft-assets/{draft_id}/{name}"
        chunk = chunk.replace(url, new_url)
        images.append({"name": name, "url": new_url})
    return chunk, draft_id, images


def _block_code(value: Any) -> str:
    text = str(value or "")
    for code, name in config.BLOCKS.items():
        if text in {code, name}:
            return code
    return "ZH"


def _type_code(value: Any) -> str:
    text = str(value or "")
    for code, name in config.TYPES.items():
        if text in {code, name}:
            return code
    return "JD"


def _infer_question_type(text: str) -> str:
    if re.search(r"(?m)^[ \t]*[A-H][.．、]", text):
        return "选择题"
    if "实验" in text or "器材" in text or "读数" in text:
        return "实验题"
    if re.search(r"(求|计算|证明|导出)", text):
        return "计算题"
    return "其他"


def _draft_from_chunk(
    chunk_info: dict[str, str],
    *,
    source_name: str,
    source_kind: str,
    confidence: float,
    warnings: list[str],
    source_dir: Path,
    assets: dict[str, Path],
    metadata: dict[str, Any] | None = None,
    include_all_assets: bool = False,
    page: int = 1,
) -> dict[str, Any]:
    chunk, draft_id, images = _materialize_chunk(
        chunk_info["content"],
        source_dir=source_dir,
        assets=assets,
        include_all_assets=include_all_assets,
    )
    parsed = documents.parse_question_sections(chunk)
    metadata = metadata or {}
    question_text = parsed["question"].strip()
    types = storage.normalize_lines(str(metadata.get("类型") or ""))
    question_type = str(metadata.get("题型") or "")
    if question_type not in config.QUESTION_TYPES:
        question_type = _infer_question_type(question_text)
    warning_items = list(warnings)
    if confidence < 0.75:
        warning_items.append("识别结果可能不准，请对照原文检查。")
    formula_items = (
        detect_formula_items(
            "\n\n".join([question_text, parsed["answer"], parsed["analysis"]]),
            config.DRAFT_ASSETS_DIR / draft_id,
            draft_id,
        )
        if draft_id
        else []
    )
    if formula_items:
        warning_items.append(f"发现 {len(formula_items)} 张可能包含公式的图片，批量入库时会保留原图。")
    return {
        "id": str(uuid.uuid4()),
        "original_number": chunk_info.get("original_number", ""),
        "question": question_text,
        "answer": parsed["answer"].strip(),
        "analysis": parsed["analysis"].strip(),
        "remarks": "",
        "block_code": _block_code(metadata.get("板块")),
        "type_code": _type_code(metadata.get("主类型")),
        "question_type": question_type,
        "knowledge_points": storage.normalize_lines(str(metadata.get("知识点") or "")),
        "extra_types": types,
        "difficulty": str(metadata.get("难度系数") or ""),
        "year": str(metadata.get("年份") or ""),
        "source": str(metadata.get("来源") or source_name),
        "source_kind": source_kind,
        "page": page,
        "confidence": round(float(confidence), 4),
        "warnings": list(dict.fromkeys(warning_items)),
        "requires_attention": confidence < 0.75 or not question_text,
        "answer_match": "embedded" if parsed["answer"] else "unmatched",
        "draft_id": draft_id,
        "images": images,
        "formula_image_names": [item["name"] for item in formula_items],
        "confirmed": False,
        "committed_id": "",
    }


def _drafts_from_pages(pages: list[dict[str, Any]], source_name: str, source_dir: Path) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    for page in pages:
        segments = split_numbered_content(page["markdown"])
        if not segments:
            segments = [{"original_number": "", "content": page["markdown"]}]
        for segment in segments:
            drafts.append(
                _draft_from_chunk(
                    segment,
                    source_name=source_name,
                    source_kind=page["source_kind"],
                    confidence=page["confidence"],
                    warnings=page["warnings"],
                    source_dir=source_dir,
                    assets=page["assets"],
                    include_all_assets=page["source_kind"] in {"scanned_pdf", "image_ocr", "image_manual"},
                    page=page["page"],
                )
            )
    return drafts


def _drafts_from_docx(path: Path, source_name: str) -> list[dict[str, Any]]:
    converted = documents.convert_docx_path(path)
    original_draft_id = str(converted.get("draft_id") or "")
    source_dir = config.DRAFT_ASSETS_DIR / original_draft_id if original_draft_id else path.parent
    assets = {
        item["name"]: source_dir / item["relative_path"]
        for item in converted.get("images", [])
    }
    segments = split_numbered_content(converted["markdown"])
    if not segments:
        segments = [{"original_number": "", "content": converted["markdown"]}]
    drafts = [
        _draft_from_chunk(
            segment,
            source_name=source_name,
            source_kind="docx",
            confidence=0.95,
            warnings=list(converted.get("warnings", [])),
            source_dir=source_dir,
            assets=assets,
            metadata=converted.get("metadata") or {},
        )
        for segment in segments
    ]
    if original_draft_id:
        shutil.rmtree(source_dir, ignore_errors=True)
    return drafts


def _plain_segments_from_path(path: Path, work_dir: Path) -> list[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        converted = documents.convert_docx_path(path)
        text = converted["markdown"]
        if converted.get("draft_id"):
            shutil.rmtree(config.DRAFT_ASSETS_DIR / converted["draft_id"], ignore_errors=True)
    elif suffix == ".pdf":
        pages = _extract_pdf_pages(path, work_dir)
        text = "\n\n".join(page["markdown"] for page in pages)
        text = MARKDOWN_IMAGE_RE.sub("", text)
    elif suffix in config.IMAGE_EXTENSIONS or suffix in {".tif", ".tiff"}:
        pages = _extract_image_page(path, work_dir)
        text = MARKDOWN_IMAGE_RE.sub("", pages[0]["markdown"])
    else:
        raise AppError("答案文件格式不受支持。")
    return split_numbered_content(text)


def _apply_answers(drafts: list[dict[str, Any]], segments: list[dict[str, str]]) -> None:
    question_segments = [
        {"original_number": draft["original_number"], "content": draft["question"]}
        for draft in drafts
    ]
    matched = match_answer_segments(question_segments, segments)
    for draft, answer in zip(drafts, matched):
        if answer["answer"]:
            draft["answer"] = answer["answer"]
        if answer["analysis"]:
            draft["analysis"] = answer["analysis"]
        draft["answer_match"] = answer["answer_match"]
        if answer["answer_match"] == "position":
            draft["warnings"].append("答案按顺序匹配，请核对原始题号。")
            draft["requires_attention"] = True
        elif answer["answer_match"] == "unmatched":
            draft["warnings"].append("未找到对应答案。")
            draft["requires_attention"] = True


def task_path(task_id: str) -> Path:
    try:
        normalized = str(uuid.UUID(str(task_id)))
    except (ValueError, AttributeError) as exc:
        raise AppError("导入任务编号无效。") from exc
    return config.IMPORT_TASKS_DIR / f"{normalized}.json"


def save_import_task(task: dict[str, Any]) -> None:
    path = task_path(task["id"])
    storage.atomic_write_text(path, json.dumps(task, ensure_ascii=False, indent=2) + "\n")


def load_import_task(task_id: str) -> dict[str, Any]:
    path = task_path(task_id)
    if not path.exists():
        raise NotFoundError("导入任务不存在。")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise AppError("导入任务文件已损坏。") from exc
    if not isinstance(loaded, dict):
        raise AppError("导入任务格式不正确。")
    return loaded


def list_import_tasks(limit: int = 20) -> list[dict[str, Any]]:
    storage.ensure_dirs()
    items = []
    for path in sorted(config.IMPORT_TASKS_DIR.glob("*.json"), reverse=True)[: max(1, min(limit, 100))]:
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        items.append(
            {
                "id": task.get("id"),
                "source": task.get("source"),
                "created_at": task.get("created_at"),
                "status": task.get("status"),
                "draft_count": len(task.get("drafts", [])),
            }
        )
    return items


async def create_import_task(file: UploadFile, answer_file: UploadFile | None = None) -> dict[str, Any]:
    storage.ensure_dirs()
    if not file.filename:
        raise AppError("请选择要导入的文件。")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in config.IMPORT_EXTENSIONS:
        raise AppError("仅支持 DOCX、PDF、PNG、JPG、WEBP、BMP 或 TIFF。")
    task_id = str(uuid.uuid4())
    task_dir = config.IMPORT_TASKS_DIR / task_id
    input_dir = task_dir / "input"
    work_dir = task_dir / "work"
    input_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / f"questions{suffix}"
    await _save_upload(file, input_path)

    if suffix == ".docx":
        drafts = _drafts_from_docx(input_path, file.filename)
    elif suffix == ".pdf":
        drafts = _drafts_from_pages(_extract_pdf_pages(input_path, work_dir), file.filename, work_dir)
    else:
        drafts = _drafts_from_pages(_extract_image_page(input_path, work_dir), file.filename, work_dir)

    answer_name = ""
    if answer_file and answer_file.filename:
        answer_suffix = Path(answer_file.filename).suffix.lower()
        if answer_suffix not in config.IMPORT_EXTENSIONS:
            raise AppError("答案文件格式不受支持。")
        answer_path = input_dir / f"answers{answer_suffix}"
        await _save_upload(answer_file, answer_path)
        answer_name = answer_file.filename
        answer_segments = _plain_segments_from_path(answer_path, work_dir / "answers")
        _apply_answers(drafts, answer_segments)

    task = {
        "id": task_id,
        "status": "待审核",
        "created_at": datetime.now().astimezone().isoformat(),
        "source": file.filename,
        "answer_source": answer_name,
        "drafts": drafts,
        "ocr": ocr_status(),
    }
    save_import_task(task)
    shutil.rmtree(work_dir, ignore_errors=True)
    return task


EDITABLE_DRAFT_FIELDS = {
    "question",
    "answer",
    "analysis",
    "remarks",
    "block_code",
    "type_code",
    "question_type",
    "knowledge_points",
    "extra_types",
    "difficulty",
    "year",
    "source",
    "confirmed",
}


def update_import_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    task = load_import_task(task_id)
    submitted = payload.get("drafts")
    if not isinstance(submitted, list):
        raise AppError("导入草稿格式不正确。")
    existing = {str(item["id"]): item for item in task.get("drafts", [])}
    updated: list[dict[str, Any]] = []
    for incoming in submitted:
        if not isinstance(incoming, dict):
            raise AppError("导入草稿格式不正确。")
        draft_id = str(incoming.get("id") or "")
        current = existing.get(draft_id)
        if current is None:
            # Frontend split creates a new draft without touching formal data.
            if not draft_id.startswith("new-"):
                raise AppError("导入草稿编号无效。")
            current = {
                "id": draft_id,
                "original_number": "",
                "draft_id": "",
                "images": [],
                "warnings": ["该题由老师在审核界面手动拆分。"],
                "confidence": 1,
                "requires_attention": False,
                "answer_match": "manual",
                "committed_id": "",
            }
        for field in EDITABLE_DRAFT_FIELDS:
            if field in incoming:
                current[field] = incoming[field]
        for field in ("knowledge_points", "extra_types"):
            value = current.get(field, [])
            if isinstance(value, str):
                current[field] = storage.normalize_lines(value)
            elif isinstance(value, list):
                current[field] = [str(item).strip() for item in value if str(item).strip()]
            else:
                raise AppError("知识点和附加类型必须是文本列表。")
        if current.get("block_code") not in config.BLOCKS:
            raise AppError("草稿板块无效。")
        if current.get("type_code") not in config.TYPES:
            raise AppError("草稿主类型无效。")
        if current.get("question_type") not in ("", *config.QUESTION_TYPES):
            raise AppError("草稿题型无效。")
        updated.append(current)
    removed = [item for draft_id, item in existing.items() if draft_id not in {draft["id"] for draft in updated}]
    for item in removed:
        if item.get("draft_id") and not item.get("committed_id"):
            shutil.rmtree(config.DRAFT_ASSETS_DIR / str(item["draft_id"]), ignore_errors=True)
    task["drafts"] = updated
    task["updated_at"] = datetime.now().astimezone().isoformat()
    save_import_task(task)
    return task


async def commit_import_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    task = update_import_task(task_id, payload)
    selected_ids = {str(item) for item in payload.get("selected_ids", [])}
    if not selected_ids:
        raise AppError("请至少确认一道题。")
    created: list[dict[str, Any]] = []
    for draft in task["drafts"]:
        if draft["id"] not in selected_ids:
            continue
        if draft.get("committed_id"):
            continue
        if draft.get("confirmed") is not True:
            raise AppError("所选草稿尚未勾选“已核对”。")
        if not str(draft.get("question") or "").strip():
            raise AppError("所选草稿缺少题目正文。")
        result = await questions.create_question(
            block_code=str(draft["block_code"]),
            type_code=str(draft["type_code"]),
            difficulty_coefficient=str(draft.get("difficulty") or ""),
            year=str(draft.get("year") or ""),
            source=str(draft.get("source") or task.get("source") or ""),
            question_text=str(draft["question"]),
            answer_text=str(draft.get("answer") or ""),
            analysis_text=str(draft.get("analysis") or ""),
            knowledge_points="\n".join(str(item) for item in draft.get("knowledge_points", [])),
            extra_types="\n".join(str(item) for item in draft.get("extra_types", [])),
            question_type=str(draft.get("question_type") or ""),
            remarks=str(draft.get("remarks") or ""),
            draft_id=str(draft.get("draft_id") or ""),
            approved_formula_images=[item.get("name", "") for item in draft.get("images", [])],
            files=[],
        )
        draft["committed_id"] = result["id"]
        created.append({"draft_id": draft["id"], "id": result["id"]})
    committed_count = sum(1 for draft in task["drafts"] if draft.get("committed_id"))
    task["status"] = "已入库" if committed_count == len(task["drafts"]) else "部分入库"
    task["updated_at"] = datetime.now().astimezone().isoformat()
    save_import_task(task)
    return {"task_id": task_id, "status": task["status"], "created": created}


def process_draft_image(
    task_id: str,
    draft_item_id: str,
    image_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    task = load_import_task(task_id)
    draft = next((item for item in task["drafts"] if item["id"] == draft_item_id), None)
    if draft is None:
        raise NotFoundError("导入草稿不存在。")
    image = next((item for item in draft.get("images", []) if item["name"] == Path(image_name).name), None)
    if image is None or not draft.get("draft_id"):
        raise NotFoundError("草稿图片不存在。")
    path = config.DRAFT_ASSETS_DIR / draft["draft_id"] / image["name"]
    if not path.exists():
        raise NotFoundError("草稿图片文件不存在。")
    action = str(payload.get("action") or "enhance")
    if action == "delete":
        raw_url = str(image.get("url") or f"/draft-assets/{draft['draft_id']}/{image['name']}")
        for field in ("question", "answer", "analysis", "remarks"):
            content = str(draft.get(field) or "")
            content = re.sub(
                rf"!\[[^\]]*\]\({re.escape(raw_url.split('?', 1)[0])}(?:\?[^)]*)?\)(?:\{{[^}}\n]*\}})?",
                "",
                content,
            )
            draft[field] = re.sub(r"\n{3,}", "\n\n", content).strip()
        path.unlink(missing_ok=True)
        draft["images"] = [item for item in draft.get("images", []) if item["name"] != image["name"]]
        draft["formula_image_names"] = [
            item for item in draft.get("formula_image_names", []) if item != image["name"]
        ]
        draft["confirmed"] = False
        task["updated_at"] = datetime.now().astimezone().isoformat()
        save_import_task(task)
        return {"deleted": True, "name": image["name"]}
    rotation = {"rotate_left": -90, "rotate_right": 90}.get(action, float(payload.get("rotation") or 0))
    result = preprocess_image(
        path,
        path,
        rotation=rotation,
        crop=payload.get("crop") if action == "crop" else None,
        perspective=payload.get("perspective") if action == "perspective" else None,
        enhance=action == "enhance",
    )
    image["url"] = f"/draft-assets/{draft['draft_id']}/{image['name']}?v={uuid.uuid4().hex[:8]}"
    task["updated_at"] = datetime.now().astimezone().isoformat()
    save_import_task(task)
    return {"image": image, **result}


def merge_import_drafts(task_id: str, first_id: str, second_id: str) -> dict[str, Any]:
    task = load_import_task(task_id)
    drafts = task.get("drafts", [])
    first_index = next((index for index, item in enumerate(drafts) if item["id"] == first_id), -1)
    second_index = next((index for index, item in enumerate(drafts) if item["id"] == second_id), -1)
    if first_index < 0 or second_index != first_index + 1:
        raise AppError("只能合并相邻的两道草稿。")
    first = drafts[first_index]
    second = drafts[second_index]
    if second.get("draft_id"):
        if not first.get("draft_id"):
            first["draft_id"] = str(uuid.uuid4())
        first_dir = config.DRAFT_ASSETS_DIR / first["draft_id"]
        second_dir = config.DRAFT_ASSETS_DIR / second["draft_id"]
        first_dir.mkdir(parents=True, exist_ok=True)
        for image in second.get("images", []):
            source = second_dir / Path(image["name"]).name
            if not source.exists():
                continue
            name = source.name
            counter = 2
            while (first_dir / name).exists():
                name = f"{source.stem}_{counter}{source.suffix.lower()}"
                counter += 1
            shutil.copy2(source, first_dir / name)
            old_url = str(image.get("url") or f"/draft-assets/{second['draft_id']}/{source.name}")
            new_url = f"/draft-assets/{first['draft_id']}/{name}"
            for field in ("question", "answer", "analysis", "remarks"):
                second[field] = str(second.get(field) or "").replace(old_url, new_url)
            first.setdefault("images", []).append({"name": name, "url": new_url})
        shutil.rmtree(second_dir, ignore_errors=True)
    for field in ("question", "answer", "analysis", "remarks"):
        left = str(first.get(field) or "").strip()
        right = str(second.get(field) or "").strip()
        first[field] = "\n\n".join(item for item in (left, right) if item)
    first["warnings"] = list(
        dict.fromkeys([*first.get("warnings", []), *second.get("warnings", []), "该草稿由老师手动合并。"])
    )
    first["confidence"] = min(float(first.get("confidence", 1)), float(second.get("confidence", 1)))
    first["requires_attention"] = True
    first["confirmed"] = False
    drafts.pop(second_index)
    task["drafts"] = drafts
    task["updated_at"] = datetime.now().astimezone().isoformat()
    save_import_task(task)
    return task


def split_import_draft(task_id: str, draft_item_id: str, position: int) -> dict[str, Any]:
    task = load_import_task(task_id)
    drafts = task.get("drafts", [])
    index = next((i for i, item in enumerate(drafts) if item["id"] == draft_item_id), -1)
    if index < 0:
        raise NotFoundError("导入草稿不存在。")
    draft = drafts[index]
    question = str(draft.get("question") or "")
    if position <= 0 or position >= len(question):
        raise AppError("请先把光标放在要拆分的位置。")
    first_text = question[:position].strip()
    second_text = question[position:].strip()
    if not first_text or not second_text:
        raise AppError("拆分位置两侧都需要有题目文字。")
    draft["question"] = first_text
    draft["confirmed"] = False
    draft["requires_attention"] = True
    draft["warnings"] = list(dict.fromkeys([*draft.get("warnings", []), "该草稿由老师手动拆分。"]))

    new_draft = {
        **draft,
        "id": str(uuid.uuid4()),
        "original_number": "",
        "question": second_text,
        "answer": "",
        "analysis": "",
        "remarks": "",
        "draft_id": "",
        "images": [],
        "answer_match": "manual",
        "committed_id": "",
    }
    if draft.get("draft_id"):
        source_dir = config.DRAFT_ASSETS_DIR / draft["draft_id"]
        tail_urls = [match.group(1) for match in MARKDOWN_IMAGE_RE.finditer(second_text)]
        tail_names = {Path(url.replace("\\", "/")).name for url in tail_urls}
        if tail_names:
            new_draft_id = str(uuid.uuid4())
            new_dir = config.DRAFT_ASSETS_DIR / new_draft_id
            new_dir.mkdir(parents=True, exist_ok=True)
            for image in draft.get("images", []):
                if image["name"] not in tail_names:
                    continue
                source = source_dir / image["name"]
                if not source.exists():
                    continue
                shutil.copy2(source, new_dir / source.name)
                old_url = str(image.get("url") or f"/draft-assets/{draft['draft_id']}/{source.name}")
                new_url = f"/draft-assets/{new_draft_id}/{source.name}"
                new_draft["question"] = new_draft["question"].replace(old_url, new_url)
                new_draft["images"].append({"name": source.name, "url": new_url})
            if new_draft["images"]:
                new_draft["draft_id"] = new_draft_id
            else:
                shutil.rmtree(new_dir, ignore_errors=True)
    drafts.insert(index + 1, new_draft)
    task["drafts"] = drafts
    task["updated_at"] = datetime.now().astimezone().isoformat()
    save_import_task(task)
    return task
