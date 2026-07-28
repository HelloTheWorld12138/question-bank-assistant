from __future__ import annotations

import base64
import html
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app import config
from app.processes import hidden_process_kwargs


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
OFFICE_NS = "urn:schemas-microsoft-com:office:office"
VML_NS = "urn:schemas-microsoft-com:vml"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MATH_MARKER_PREFIX = "QBMATH"
MATHTYPE_PROG_IDS = {
    "Equation.3",
    "Equation.DSMT",
    "Equation.DSMT4",
    "MathType.Equation",
}
OBJECT_XML_RE = re.compile(rb"<w:object\b.*?</w:object>", re.S)
PROG_ID_RE = re.compile(rb"\bProgID=[\"']([^\"']+)[\"']", re.I)
LATEX_FUNCTION_RE = re.compile(
    r"(?<![A-Za-z\\])"
    r"(arcsin|arccos|arctan|sinh|cosh|tanh|sin|cos|tan|cot|sec|csc|log|ln|lim|max|min)"
    r"(?![A-Za-z])"
)
VENDOR_DIR = config.ROOT / "third_party" / "mathtype_to_mathml"
CONVERTER_SCRIPT = VENDOR_DIR / "convert.rb"
VENDOR_GEMS = (
    ("bindata-2.4.15.gem", "bindata"),
    ("ruby-ole-1.2.13.1.gem", "ruby-ole"),
    ("mathtype_to_mathml_plus-0.0.16.gem", "mathtype-plus"),
)


@dataclass(frozen=True)
class MathTypeObject:
    marker: str
    prog_id: str
    object_id: str
    ole_target: str
    preview_target: str
    display: bool


def _relationship_target(target: str) -> str:
    return posixpath.normpath(posixpath.join("word", target.replace("\\", "/")))


def _is_mathtype_prog_id(value: str) -> bool:
    normalized = str(value or "").strip()
    return normalized in MATHTYPE_PROG_IDS or normalized.lower().startswith("mathtype")


def _ancestor(element: ElementTree.Element, parent_map: dict[ElementTree.Element, ElementTree.Element], tag: str):
    current = element
    while current in parent_map:
        current = parent_map[current]
        if current.tag == tag:
            return current
    return None


def inspect_mathtype_objects(path: Path) -> list[MathTypeObject]:
    """Return MathType OLE objects in their exact document order."""
    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
            relationships_xml = archive.read("word/_rels/document.xml.rels")
    except (KeyError, OSError, zipfile.BadZipFile):
        return []

    relationships_root = ElementTree.fromstring(relationships_xml)
    relationships = {
        item.attrib.get("Id", ""): _relationship_target(item.attrib.get("Target", ""))
        for item in relationships_root.findall(f"{{{PACKAGE_REL_NS}}}Relationship")
    }
    document_root = ElementTree.fromstring(document_xml)
    parent_map = {child: parent for parent in document_root.iter() for child in parent}
    objects: list[MathTypeObject] = []
    for element in document_root.iter(f"{{{WORD_NS}}}object"):
        ole = element.find(f".//{{{OFFICE_NS}}}OLEObject")
        if ole is None:
            continue
        prog_id = str(ole.attrib.get("ProgID") or "")
        if not _is_mathtype_prog_id(prog_id):
            continue
        ole_relationship = str(ole.attrib.get(f"{{{REL_NS}}}id") or "")
        ole_target = relationships.get(ole_relationship, "")
        if not ole_target:
            continue
        image = element.find(f".//{{{VML_NS}}}imagedata")
        image_relationship = str(image.attrib.get(f"{{{REL_NS}}}id") or "") if image is not None else ""
        preview_target = relationships.get(image_relationship, "")
        paragraph = _ancestor(element, parent_map, f"{{{WORD_NS}}}p")
        paragraph_text = ""
        if paragraph is not None:
            paragraph_text = "".join(
                str(item.text or "") for item in paragraph.iter(f"{{{WORD_NS}}}t")
            ).strip()
        objects.append(
            MathTypeObject(
                marker=f"{MATH_MARKER_PREFIX}{len(objects) + 1:06d}",
                prog_id=prog_id,
                object_id=str(ole.attrib.get("ObjectID") or ""),
                ole_target=ole_target,
                preview_target=preview_target,
                display=not bool(paragraph_text),
            )
        )
    return objects


def _replace_mathtype_objects(document_xml: bytes, objects: list[MathTypeObject]) -> bytes:
    index = 0

    def replace(match: re.Match[bytes]) -> bytes:
        nonlocal index
        prog_match = PROG_ID_RE.search(match.group(0))
        prog_id = prog_match.group(1).decode("utf-8", errors="replace") if prog_match else ""
        if not _is_mathtype_prog_id(prog_id):
            return match.group(0)
        if index >= len(objects):
            return match.group(0)
        marker = objects[index].marker
        index += 1
        return f'<w:t xml:space="preserve">{marker}</w:t>'.encode("ascii")

    result = OBJECT_XML_RE.sub(replace, document_xml)
    if index != len(objects):
        raise ValueError("MathType object order could not be preserved")
    return result


def prepare_docx_for_pandoc(source: Path, target: Path) -> list[MathTypeObject]:
    """Create a temporary DOCX where each MathType object is a stable text marker."""
    objects = inspect_mathtype_objects(source)
    if not objects:
        shutil.copy2(source, target)
        return []
    with zipfile.ZipFile(source) as input_archive, zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED
    ) as output_archive:
        for info in input_archive.infolist():
            data = input_archive.read(info.filename)
            if info.filename == "word/document.xml":
                data = _replace_mathtype_objects(data, objects)
            output_archive.writestr(info, data)
    return objects


def find_ruby() -> str | None:
    configured = os.getenv("MATHTYPE_RUBY", "").strip()
    if configured and Path(configured).is_file():
        return configured
    if config.BUNDLED_RUBY.is_file():
        return str(config.BUNDLED_RUBY)
    return shutil.which("ruby")


def mathtype_status() -> dict[str, Any]:
    ruby = find_ruby()
    missing = [
        name
        for name, _ in VENDOR_GEMS
        if not (VENDOR_DIR / name).is_file()
    ]
    available = bool(ruby and CONVERTER_SCRIPT.is_file() and not missing)
    return {
        "available": available,
        "offline": True,
        "message": (
            "可读取旧版 MathType 公式"
            if available
            else "旧版公式会保留原图，请人工核对"
        ),
    }


def _safe_extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
    destination_resolved = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != destination_resolved and destination_resolved not in target.parents:
            raise ValueError("Unsafe path in bundled MathType converter")
    archive.extractall(destination)


def _unpack_gem(gem_path: Path, destination: Path) -> None:
    with tarfile.open(gem_path, "r:*") as outer:
        member = outer.getmember("data.tar.gz")
        stream = outer.extractfile(member)
        if stream is None:
            raise ValueError(f"Invalid bundled gem: {gem_path.name}")
        payload = stream.read()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as data_archive:
        _safe_extract_tar(data_archive, destination)


def _vendor_rubylib(runtime_dir: Path) -> str:
    extracted: dict[str, Path] = {}
    for filename, key in VENDOR_GEMS:
        destination = runtime_dir / key
        _unpack_gem(VENDOR_DIR / filename, destination)
        extracted[key] = destination
    mathtype_plus = extracted["mathtype-plus"]
    paths = [
        extracted["bindata"] / "lib",
        extracted["ruby-ole"] / "lib",
        mathtype_plus / "lib",
        mathtype_plus / "lib" / "mathtype-0.0.7.5" / "lib",
    ]
    return os.pathsep.join(str(path) for path in paths)


def _extract_ole_objects(
    source: Path,
    objects: list[MathTypeObject],
    destination: Path,
) -> dict[str, Path]:
    extracted: dict[str, Path] = {}
    with zipfile.ZipFile(source) as archive:
        for item in objects:
            try:
                payload = archive.read(item.ole_target)
            except KeyError:
                continue
            target = destination / f"{item.marker}.bin"
            target.write_bytes(payload)
            extracted[item.marker] = target
    return extracted


def convert_ole_objects_to_mathml(
    source: Path,
    objects: list[MathTypeObject],
    *,
    timeout: int = 180,
) -> tuple[dict[str, str], dict[str, str]]:
    """Convert all MathType OLE objects in one local Ruby process."""
    if not objects:
        return {}, {}
    ruby = find_ruby()
    status = mathtype_status()
    if not ruby or not status["available"]:
        message = str(status["message"])
        return {}, {item.marker: message for item in objects}

    with tempfile.TemporaryDirectory(prefix="question-bank-mathtype-") as temp_dir:
        root = Path(temp_dir)
        ole_dir = root / "objects"
        ole_dir.mkdir(parents=True, exist_ok=True)
        extracted = _extract_ole_objects(source, objects, ole_dir)
        try:
            rubylib = _vendor_rubylib(root / "ruby")
        except (OSError, KeyError, tarfile.TarError, ValueError) as exc:
            message = f"公式转换组件无法准备：{exc}"
            return {}, {item.marker: message for item in objects}
        command = [
            ruby,
            str(CONVERTER_SCRIPT),
            *(f"{marker}={path}" for marker, path in extracted.items()),
        ]
        environment = dict(os.environ)
        environment["RUBYLIB"] = os.pathsep.join(
            item for item in (rubylib, environment.get("RUBYLIB", "")) if item
        )
        environment.setdefault("LANG", "C.UTF-8")
        try:
            completed = subprocess.run(
                command,
                cwd=str(config.ROOT),
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=timeout,
                **hidden_process_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            message = "旧版公式读取超时" if isinstance(exc, subprocess.TimeoutExpired) else "旧版公式读取组件无法启动"
            return {}, {item.marker: message for item in objects}

    converted: dict[str, str] = {}
    failures: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        marker = str(payload.get("id") or "")
        if marker not in extracted:
            continue
        if payload.get("ok"):
            try:
                converted[marker] = base64.b64decode(str(payload.get("mathml") or "")).decode(
                    "utf-8", errors="replace"
                )
            except (ValueError, UnicodeDecodeError):
                failures[marker] = "公式结构数据无法读取"
        else:
            failures[marker] = str(payload.get("error") or "公式结构转换失败")
    for item in objects:
        if item.marker not in extracted:
            failures[item.marker] = "公式对象文件缺失"
        elif item.marker not in converted and item.marker not in failures:
            failures[item.marker] = "公式转换没有返回结果"
    return converted, failures


def mathml_to_latex(
    equations: dict[str, str],
    pandoc_path: str,
    *,
    timeout: int = 120,
) -> tuple[dict[str, str], dict[str, str]]:
    if not equations:
        return {}, {}
    blocks = []
    for marker, mathml in equations.items():
        cleaned = re.sub(r"<\?xml[^>]*\?>", "", str(mathml), flags=re.I).strip()
        blocks.append(f"<p>{html.escape(marker)} {cleaned}</p>")
    source = "<!doctype html><html><body>" + "\n".join(blocks) + "</body></html>"
    try:
        completed = subprocess.run(
            [pandoc_path, "-f", "html", "-t", "json", "--wrap=none"],
            cwd=str(config.ROOT),
            input=source,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
            **hidden_process_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}, {marker: "公式文本转换组件无法启动" for marker in equations}
    if completed.returncode != 0:
        return {}, {marker: "公式文本转换失败" for marker in equations}
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}, {marker: "公式文本转换结果无法读取" for marker in equations}

    converted: dict[str, str] = {}
    for block in document.get("blocks", []):
        if not isinstance(block, dict) or block.get("t") not in {"Para", "Plain"}:
            continue
        content = block.get("c")
        if not isinstance(content, list):
            continue
        marker = next(
            (
                str(item.get("c"))
                for item in content
                if isinstance(item, dict)
                and item.get("t") == "Str"
                and str(item.get("c") or "") in equations
            ),
            "",
        )
        math_node = next(
            (
                item
                for item in content
                if isinstance(item, dict) and item.get("t") == "Math"
            ),
            None,
        )
        if not marker or not math_node:
            continue
        math_content = math_node.get("c")
        if isinstance(math_content, list) and len(math_content) >= 2:
            latex = _normalize_latex(str(math_content[1] or ""))
            if latex:
                converted[marker] = latex
    failures = {
        marker: "公式无法转换为可编辑文本"
        for marker in equations
        if marker not in converted
    }
    return converted, failures


def _normalize_latex(value: str) -> str:
    latex = str(value or "").strip().replace("\u2009", " ").replace("\u00a0", " ")
    return LATEX_FUNCTION_RE.sub(lambda match: f"\\{match.group(1)}", latex)


def _formula_markup(latex: str, display: bool) -> str:
    normalized = str(latex or "").strip()
    return f"$$\n{normalized}\n$$" if display else f"${normalized}$"


def _replace_marker(markdown: str, marker: str, replacement: str) -> str:
    for wrapped in (
        f"***{marker}***",
        f"___{marker}___",
        f"**{marker}**",
        f"__{marker}__",
        f"*{marker}*",
        f"_{marker}_",
        marker,
    ):
        if wrapped in markdown:
            return markdown.replace(wrapped, replacement, 1)
    return markdown


def _copy_preview(
    archive: zipfile.ZipFile,
    item: MathTypeObject,
    draft_dir: Path,
    draft_id: str,
) -> str:
    if not item.preview_target:
        return ""
    try:
        payload = archive.read(item.preview_target)
    except KeyError:
        return ""
    relative = Path("formula-fallback") / f"{item.marker}{Path(item.preview_target).suffix.lower()}"
    target = draft_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return f"/draft-assets/{draft_id}/{relative.as_posix()}"


def restore_mathtype_markers(
    markdown: str,
    source: Path,
    objects: list[MathTypeObject],
    latex: dict[str, str],
    failures: dict[str, str],
    draft_dir: Path,
    draft_id: str,
) -> tuple[str, dict[str, Any]]:
    formula_rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(source) as archive:
        for item in objects:
            if item.marker in latex:
                replacement = _formula_markup(latex[item.marker], item.display)
                status = "converted"
                error = ""
                preview_url = ""
            else:
                preview_url = _copy_preview(archive, item, draft_dir, draft_id)
                replacement = f"![公式]({preview_url})" if preview_url else "【公式读取失败】"
                status = "needs_review"
                error = failures.get(item.marker, "公式读取失败")
            markdown = _replace_marker(markdown, item.marker, replacement)
            formula_rows.append(
                {
                    **asdict(item),
                    "latex": latex.get(item.marker, ""),
                    "status": status,
                    "error": error,
                    "preview_url": preview_url,
                }
            )
    converted_count = sum(item["status"] == "converted" for item in formula_rows)
    failed_count = len(formula_rows) - converted_count
    return markdown, {
        "detected": len(formula_rows),
        "converted": converted_count,
        "failed": failed_count,
        "available": bool(formula_rows and converted_count),
        "formulas": formula_rows,
    }
