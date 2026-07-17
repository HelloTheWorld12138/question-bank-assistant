import json
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent import opencode_available, run_opencode
from app.math_ocr import detect_formula_items, formula_ocr_available, has_editable_math


ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault"
QUESTIONS_DIR = VAULT / "题目"
ASSETS_DIR = VAULT / "assets"
DRAFT_ASSETS_DIR = ASSETS_DIR / "_drafts"
INDEX_FILE = VAULT / "index.json"
EXPORT_DIR = ROOT / "exports"
STATIC_DIR = ROOT / "static"
LOCAL_PANDOC = ROOT / "tools" / "pandoc" / "pandoc.exe"

BLOCKS = {
    "LX": "力学",
    "DX": "电学",
    "CD": "磁场与电磁感应",
    "GX": "光学",
    "RX": "热学",
    "XD": "近代物理",
    "SY": "实验",
    "ZH": "综合",
}

TYPES = {
    "JD": "经典题",
    "CX": "创新题",
    "JS": "计算量大",
    "YC": "易错题",
    "YZ": "压轴题",
    "JC": "基础题",
    "MX": "模型题",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".wmf", ".emf"}
IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

app = FastAPI(title="高中物理题库助手")


def ensure_dirs() -> None:
    QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    DRAFT_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("{}", encoding="utf-8")


def load_index() -> dict[str, int]:
    ensure_dirs()
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    return {str(k): int(v) for k, v in data.items()}


def save_index(index: dict[str, int]) -> None:
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def find_pandoc() -> str | None:
    system_pandoc = shutil.which("pandoc")
    if system_pandoc:
        return system_pandoc
    if LOCAL_PANDOC.exists():
        return str(LOCAL_PANDOC)
    return None


def next_question_id(block_code: str, type_code: str) -> str:
    if block_code not in BLOCKS:
        raise HTTPException(status_code=400, detail="未知板块代码")
    if type_code not in TYPES:
        raise HTTPException(status_code=400, detail="未知类型代码")
    prefix = f"{block_code}{type_code}"
    index = load_index()
    next_number = index.get(prefix, 0) + 1
    index[prefix] = next_number
    save_index(index)
    return f"{prefix}{next_number:04d}"


def normalize_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


def safe_year(value: str | None) -> str:
    return (value or "").strip()


def split_markdown_sections(text: str) -> tuple[dict[str, Any], dict[str, str]]:
    metadata: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                metadata = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                metadata = {}
            body = parts[2]

    sections = {"题目": "", "答案": "", "解析": "", "备注": ""}
    current = "题目"
    collected: dict[str, list[str]] = {key: [] for key in sections}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        heading = line.lstrip("#").strip()
        if heading in sections:
            current = heading
            continue
        collected[current].append(raw_line)

    for key, lines in collected.items():
        sections[key] = "\n".join(lines).strip()
    return metadata, sections


def question_preview(text: str, length: int = 120) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:length] + ("..." if len(compact) > length else "")


async def save_uploads(question_id: str, uploads: list[UploadFile], start_index: int = 1) -> list[str]:
    saved: list[str] = []
    image_count = start_index
    doc_count = 1
    for upload in uploads:
        if not upload.filename:
            continue
        source_name = Path(upload.filename)
        ext = source_name.suffix.lower() or ".bin"
        if ext in IMAGE_EXTENSIONS:
            filename = f"{question_id}_{image_count:02d}{ext}"
            image_count += 1
            saved.append(filename)
        else:
            filename = f"{question_id}_附件{doc_count}{ext}"
            doc_count += 1
        target = ASSETS_DIR / filename
        with target.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
    return saved


def strip_markdown_images(markdown: str) -> str:
    text = IMAGE_MARKDOWN_RE.sub("", markdown)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def finalize_draft_images(question_id: str, draft_id: str, start_index: int = 1) -> tuple[list[str], dict[str, str]]:
    if not draft_id or not re.fullmatch(r"[a-f0-9-]{36}", draft_id):
        return [], {}

    draft_dir = DRAFT_ASSETS_DIR / draft_id
    if not draft_dir.exists():
        return [], {}

    saved: list[str] = []
    link_map: dict[str, str] = {}
    image_count = start_index
    for source in sorted(draft_dir.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        filename = f"{question_id}_{image_count:02d}{source.suffix.lower()}"
        shutil.copy2(source, ASSETS_DIR / filename)
        saved.append(filename)
        relative = image.relative_to(draft_dir).as_posix() if (image := source) else source.name
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
        key = key.strip()
        filename = link_map.get(key) or link_map.get(Path(key).name)
        if not filename:
            return match.group(0)
        return match.group(0).replace(url, (ASSETS_DIR / filename).as_posix())

    return IMAGE_MARKDOWN_RE.sub(replace, markdown)


def normalize_converted_markdown(markdown: str, draft_id: str) -> str:
    markdown = markdown.replace("\r\n", "\n").replace("\r", "\n")
    if draft_id:
        markdown = markdown.replace(f"{DRAFT_ASSETS_DIR.as_posix()}/{draft_id}/", f"/draft-assets/{draft_id}/")
        markdown = markdown.replace(f"{DRAFT_ASSETS_DIR}\\{draft_id}\\", f"/draft-assets/{draft_id}/")
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


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
        return re.sub(r"^\s*(?:#+\s*)?(?:【?\s*(?:参考)?答案|正确答案|标准答案\s*】?)\s*[:：]?\s*", "", line).strip()
    return re.sub(r"^\s*(?:#+\s*)?(?:【?\s*(?:答案)?解析|详解|解题过程|思路点拨|解\s*】?)\s*[:：]?\s*", "", line).strip()


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
        first_split = min([m[0] for m in markers])
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


def build_markdown(metadata: dict[str, Any], sections: dict[str, str]) -> str:
    frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    return (
        f"---\n{frontmatter}\n---\n\n"
        f"# 题目\n\n{sections.get('题目', '').strip()}\n\n"
        f"# 答案\n\n{sections.get('答案', '').strip()}\n\n"
        f"# 解析\n\n{sections.get('解析', '').strip()}\n\n"
        f"# 备注\n\n{sections.get('备注', '').strip()}\n"
    )


def read_all_questions() -> list[dict[str, Any]]:
    ensure_dirs()
    questions: list[dict[str, Any]] = []
    for path in sorted(QUESTIONS_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        metadata, sections = split_markdown_sections(raw)
        questions.append(
            {
                "id": metadata.get("id", path.stem),
                "板块": metadata.get("板块", ""),
                "主类型": metadata.get("主类型", ""),
                "类型": metadata.get("类型", []),
                "知识点": metadata.get("知识点", []),
                "难度": metadata.get("难度系数", metadata.get("难度", "")),
                "难度系数": metadata.get("难度系数", ""),
                "年份": metadata.get("年份", ""),
                "来源": metadata.get("来源", ""),
                "解析来源": metadata.get("解析来源", ""),
                "图片": metadata.get("图片", []),
                "题目": sections.get("题目", ""),
                "答案": sections.get("答案", ""),
                "解析": sections.get("解析", ""),
                "备注": sections.get("备注", ""),
                "preview": question_preview(sections.get("题目", "")),
            }
        )
    return questions


def matches(value: Any, expected: str) -> bool:
    if not expected:
        return True
    if isinstance(value, list):
        return any(expected in str(item) for item in value)
    return expected in str(value)


@app.on_event("startup")
def startup() -> None:
    ensure_dirs()


@app.get("/api/options")
def options() -> dict[str, Any]:
    return {
        "blocks": [{"code": code, "name": name} for code, name in BLOCKS.items()],
        "types": [{"code": code, "name": name} for code, name in TYPES.items()],
        "pandoc": find_pandoc() is not None,
        "agent": opencode_available(),
        "formula_ocr": formula_ocr_available(),
    }


@app.post("/api/questions")
async def create_question(
    block_code: str = Form(...),
    type_code: str = Form(...),
    difficulty: str = Form(""),
    difficulty_coefficient: str = Form(""),
    year: str = Form(""),
    source: str = Form(""),
    question_text: str = Form(...),
    answer_text: str = Form(""),
    analysis_text: str = Form(""),
    knowledge_points: str = Form(""),
    extra_types: str = Form(""),
    remarks: str = Form(""),
    draft_id: str = Form(""),
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    if draft_id and re.fullmatch(r"[a-f0-9-]{36}", draft_id):
        draft_dir = DRAFT_ASSETS_DIR / draft_id
        if draft_dir.exists():
            submitted_markdown = "\n\n".join([question_text, answer_text, analysis_text])
            unresolved_formulas = detect_formula_items(submitted_markdown, draft_dir, draft_id)
            if unresolved_formulas:
                names = "、".join(item["name"] for item in unresolved_formulas[:3])
                raise HTTPException(
                    status_code=400,
                    detail=f"还有疑似公式图片未替换为 LaTeX，不能入库：{names}",
                )
    question_id = next_question_id(block_code, type_code)
    images, draft_image_map = finalize_draft_images(question_id, draft_id)
    images.extend(await save_uploads(question_id, files, start_index=len(images) + 1))
    question_text = rewrite_draft_image_links(question_text, draft_id, draft_image_map)
    answer_text = rewrite_draft_image_links(answer_text, draft_id, draft_image_map)
    analysis_text = rewrite_draft_image_links(analysis_text, draft_id, draft_image_map)
    main_type = TYPES[type_code]
    type_names = [main_type]
    for item in normalize_lines(extra_types):
        if item not in type_names:
            type_names.append(item)
    metadata = {
        "id": question_id,
        "板块": BLOCKS[block_code],
        "主类型": main_type,
        "类型": type_names,
        "知识点": normalize_lines(knowledge_points),
        "难度系数": (difficulty_coefficient or difficulty or "").strip(),
        "年份": safe_year(year),
        "来源": source.strip(),
        "解析来源": "教师上传",
        "图片": images,
    }
    sections = {
        "题目": question_text,
        "答案": answer_text,
        "解析": analysis_text,
        "备注": remarks,
    }
    markdown = build_markdown(metadata, sections)
    path = QUESTIONS_DIR / f"{question_id}.md"
    path.write_text(markdown, encoding="utf-8")
    return {"id": question_id, "file": str(path.relative_to(ROOT)), "images": images}


@app.post("/api/convert-docx")
async def convert_docx(file: UploadFile = File(...)) -> dict[str, Any]:
    pandoc_path = find_pandoc()
    if not pandoc_path:
        raise HTTPException(status_code=400, detail="未检测到 Pandoc，无法转换 Word。")
    if not opencode_available():
        raise HTTPException(status_code=400, detail="未检测到本地 opencode agent，Word 单题导入不可用。请先接入本地 agent。")
    if not formula_ocr_available():
        raise HTTPException(status_code=400, detail="未检测到本地公式 OCR，Word 单题导入不可用。请先配置 FORMULA_OCR_COMMAND、latexocr 或 pix2tex。")
    if not file.filename or Path(file.filename).suffix.lower() != ".docx":
        raise HTTPException(status_code=400, detail="请上传 .docx 格式的 Word 文件。")

    draft_id = str(uuid.uuid4())
    draft_dir = DRAFT_ASSETS_DIR / draft_id
    draft_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_path = temp_path / "input.docx"
        output_path = temp_path / "output.md"
        with input_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
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
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=completed.stderr.strip() or "Word 转 Markdown 失败。",
            )
        markdown = normalize_converted_markdown(output_path.read_text(encoding="utf-8"), draft_id)

    images = []
    for image in sorted(draft_dir.rglob("*")):
        if image.is_file() and image.suffix.lower() in IMAGE_EXTENSIONS:
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
    metadata = {}
    agent_used = False
    agent_message = ""
    agent_sections, agent_error = run_opencode(markdown, ROOT)
    if agent_sections:
        parsed = {
            "question": agent_sections.get("question") or parsed.get("question", ""),
            "answer": agent_sections.get("answer") or parsed.get("answer", ""),
            "analysis": agent_sections.get("analysis") or parsed.get("analysis", ""),
        }
        metadata = normalize_agent_metadata(agent_sections.get("metadata"))
        agent_used = True
    else:
        agent_message = agent_error
    warnings = []
    if not agent_used and agent_message:
        raise HTTPException(status_code=500, detail=f"本地 agent 解析失败，Word 单题导入已中止：{agent_message}")
    if has_editable_math(markdown):
        warnings.append("检测到可编辑 Markdown/LaTeX 公式，已保留。")
    if docx_payload["embedded_objects"]:
        warnings.append(
            "检测到 Word 内嵌对象。若它是旧版 MathType/OLE 公式，请确认 OCR 面板或手动改成 LaTeX 后再入库。"
        )
    if docx_payload["wmf_or_emf"]:
        warnings.append("检测到 WMF/EMF 图片；浏览器可能无法预览，入库前建议检查是否需要手动另存为 PNG。")

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


@app.get("/api/questions")
def search_questions(
    block: str = "",
    main_type: str = "",
    difficulty: str = "",
    year: str = "",
    source: str = "",
    knowledge: str = "",
) -> dict[str, Any]:
    results = []
    for item in read_all_questions():
        if not matches(item["板块"], block):
            continue
        if not matches(item["主类型"], main_type):
            continue
        if not matches(item["难度"], difficulty):
            continue
        if not matches(item["年份"], year):
            continue
        if not matches(item["来源"], source):
            continue
        if not matches(item["知识点"], knowledge):
            continue
        results.append(item)
    return {"items": results}


@app.get("/api/questions/{question_id}")
def get_question(question_id: str) -> dict[str, Any]:
    path = QUESTIONS_DIR / f"{question_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="题目不存在")
    raw = path.read_text(encoding="utf-8")
    metadata, sections = split_markdown_sections(raw)
    return {"metadata": metadata, "sections": sections}


@app.post("/api/export")
def export_exam(payload: dict[str, Any]) -> dict[str, Any]:
    ids = payload.get("ids") or []
    mode = payload.get("mode") or "questions"
    if not ids:
        raise HTTPException(status_code=400, detail="请先选择题目")
    if mode not in {"questions", "answers", "analysis"}:
        raise HTTPException(status_code=400, detail="未知导出模式")

    parts: list[str] = ["# 试卷\n"]
    missing: list[str] = []
    for question_id in ids:
        path = QUESTIONS_DIR / f"{question_id}.md"
        if not path.exists():
            missing.append(question_id)
            continue
        metadata, sections = split_markdown_sections(path.read_text(encoding="utf-8"))
        title = metadata.get("id", question_id)
        parts.append(f"\n## 【{title}】\n")
        question_body = sections.get("题目", "").strip()
        parts.append(question_body + "\n")
        section_blob = "\n".join(sections.values())
        images = metadata.get("图片", []) or []
        for image in images:
            if str(image) in section_blob:
                continue
            parts.append(f"\n![]({(ASSETS_DIR / image).as_posix()})\n")
        if mode in {"answers", "analysis"}:
            parts.append("\n### 答案\n")
            parts.append(sections.get("答案", "").strip() + "\n")
        if mode == "analysis":
            parts.append("\n### 解析\n")
            parts.append(sections.get("解析", "").strip() + "\n")

    exam_md = EXPORT_DIR / "exam.md"
    exam_docx = EXPORT_DIR / "exam.docx"
    exam_md.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")

    pandoc_path = find_pandoc()
    docx_created = False
    pandoc_message = ""
    if pandoc_path:
        completed = subprocess.run(
            [pandoc_path, str(exam_md), "-o", str(exam_docx)],
            cwd=str(ROOT),
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


@app.get("/download/{filename}")
def download(filename: str) -> FileResponse:
    if filename not in {"exam.md", "exam.docx"}:
        raise HTTPException(status_code=400, detail="不允许下载该文件")
    path = EXPORT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=filename)


ensure_dirs()
app.mount("/draft-assets", StaticFiles(directory=str(DRAFT_ASSETS_DIR)), name="draft-assets")
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
