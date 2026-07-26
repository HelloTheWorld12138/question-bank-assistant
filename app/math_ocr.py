from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any


FORMULA_EXTENSIONS = {".wmf", ".emf"}
RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
MATH_RE = re.compile(r"(\$\$.*?\$\$|\$[^$\n]+\$|```math.*?```)", re.S)


def formula_ocr_available() -> bool:
    if os.getenv("FORMULA_OCR_COMMAND", "").strip():
        return True
    return shutil.which("latexocr") is not None or shutil.which("pix2tex") is not None


def image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        data = path.read_bytes()[:32]
    except OSError:
        return None, None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        try:
            content = path.read_bytes()
            index = 2
            while index < len(content) - 9:
                if content[index] != 0xFF:
                    index += 1
                    continue
                marker = content[index + 1]
                index += 2
                if marker in {0xD8, 0xD9}:
                    continue
                length = int.from_bytes(content[index : index + 2], "big")
                if marker in range(0xC0, 0xC4):
                    height = int.from_bytes(content[index + 3 : index + 5], "big")
                    width = int.from_bytes(content[index + 5 : index + 7], "big")
                    return width, height
                index += length
        except OSError:
            return None, None
    return None, None


def local_path_from_markdown_url(url: str, draft_dir: Path, draft_id: str) -> Path | None:
    key = url.split(f"/draft-assets/{draft_id}/", 1)[-1] if draft_id else url
    key = key.replace("\\", "/").strip()
    if not key or key.startswith(("http://", "https://")):
        return None
    candidate = draft_dir / key
    try:
        candidate.relative_to(draft_dir)
    except ValueError:
        return None
    return candidate if candidate.exists() else None


def nearby_text(markdown: str, start: int, end: int, radius: int = 120) -> str:
    return re.sub(r"\s+", " ", markdown[max(0, start - radius) : min(len(markdown), end + radius)]).strip()


def is_formula_like(path: Path, context: str) -> tuple[bool, str]:
    ext = path.suffix.lower()
    if ext in FORMULA_EXTENSIONS:
        return True, "WMF/EMF 常见于旧 MathType 公式"
    width, height = image_size(path)
    if width and height:
        ratio = width / max(height, 1)
        if height <= 120 and width <= 900:
            return True, "图片尺寸接近行内公式"
        if height <= 260 and ratio >= 3:
            return True, "图片比例接近长公式"
    if re.search(r"(公式|表达式|方程|函数|解析式|求|=|≈|≤|≥|∑|√|frac|sin|cos|tan)", context):
        if width is None or height is None or height <= 260:
            return True, "上下文疑似公式"
    return False, ""


def run_formula_ocr(path: Path, timeout: int = 60) -> tuple[str, str]:
    command_template = os.getenv("FORMULA_OCR_COMMAND", "").strip()
    with tempfile.TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "formula.txt"
        try:
            if command_template:
                command = command_template.format(image_file=str(path), output_file=str(output_file))
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=timeout,
                    check=False,
                )
            elif shutil.which("latexocr"):
                completed = subprocess.run(
                    ["latexocr", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            elif shutil.which("pix2tex"):
                completed = subprocess.run(
                    ["pix2tex", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
            else:
                return "", "未检测到本地公式 OCR 工具"
        except subprocess.TimeoutExpired:
            return "", "公式 OCR 超时"

        output = output_file.read_text(encoding="utf-8", errors="replace") if output_file.exists() else completed.stdout
        latex = output.strip().strip("`")
        if completed.returncode != 0:
            return latex, completed.stderr.strip() or "公式 OCR 调用失败"
        return latex, ""


def detect_formula_items(markdown: str, draft_dir: Path, draft_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, match in enumerate(IMAGE_RE.finditer(markdown), start=1):
        url = match.group(1)
        path = local_path_from_markdown_url(url, draft_dir, draft_id)
        if not path:
            continue
        context = nearby_text(markdown, match.start(), match.end())
        formula_like, reason = is_formula_like(path, context)
        if not formula_like:
            continue
        width, height = image_size(path)
        latex = ""
        ocr_error = ""
        if path.suffix.lower() in RASTER_EXTENSIONS:
            latex, ocr_error = run_formula_ocr(path)
        else:
            ocr_error = "该格式无法直接 OCR，请先转成 PNG/JPG 或在 Word 中转为可编辑公式"
        items.append(
            {
                "id": f"formula-{index}",
                "url": url,
                "name": path.name,
                "relative_path": path.relative_to(draft_dir).as_posix(),
                "width": width,
                "height": height,
                "context": context,
                "reason": reason,
                "latex": latex,
                "ocr_error": ocr_error,
                "confirmed": False,
            }
        )
    return items


def has_editable_math(markdown: str) -> bool:
    return bool(MATH_RE.search(markdown))
