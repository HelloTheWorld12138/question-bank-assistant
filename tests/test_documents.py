import asyncio
import io
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

from starlette.datastructures import UploadFile

from app.services import documents


def build_minimal_docx() -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<document />")
    buffer.seek(0)
    return buffer


def test_docx_conversion_falls_back_without_agent_or_formula_ocr(isolated_data, monkeypatch):
    monkeypatch.setattr(documents, "find_pandoc", lambda: "/fake/pandoc")
    monkeypatch.setattr(documents, "opencode_available", lambda: False)
    monkeypatch.setattr(documents, "formula_ocr_available", lambda: False)
    monkeypatch.setattr(documents, "detect_formula_items", lambda *args: [])
    monkeypatch.setattr(documents, "has_editable_math", lambda markdown: False)

    def fake_run(command, **kwargs):
        output_path = Path(command[command.index("-o") + 1])
        output_path.write_text(
            "一物体做匀加速运动。\n\n# 答案\n\nA\n\n# 解析\n\n由运动学公式可得。",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(documents.subprocess, "run", fake_run)
    upload = UploadFile(file=build_minimal_docx(), filename="测试题.docx")

    result = asyncio.run(documents.convert_docx(upload))

    assert result["sections"]["question"] == "一物体做匀加速运动。"
    assert result["sections"]["answer"] == "A"
    assert result["agent_used"] is False
    assert any("按原文读取" in warning for warning in result["warnings"])


def test_docx_conversion_falls_back_when_agent_crashes(isolated_data, monkeypatch):
    monkeypatch.setattr(documents, "find_pandoc", lambda: "/fake/pandoc")
    monkeypatch.setattr(documents, "opencode_available", lambda: True)
    monkeypatch.setattr(
        documents,
        "run_opencode",
        lambda *args: (_ for _ in ()).throw(TimeoutError("离线")),
    )
    monkeypatch.setattr(documents, "formula_ocr_available", lambda: False)
    monkeypatch.setattr(documents, "detect_formula_items", lambda *args: [])
    monkeypatch.setattr(documents, "has_editable_math", lambda markdown: False)

    def fake_run(command, **kwargs):
        output_path = Path(command[command.index("-o") + 1])
        output_path.write_text("题目正文\n\n# 答案\n\nB", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(documents.subprocess, "run", fake_run)
    upload = UploadFile(file=build_minimal_docx(), filename="智能整理失败.docx")

    result = asyncio.run(documents.convert_docx(upload))

    assert result["sections"]["question"] == "题目正文"
    assert result["sections"]["answer"] == "B"
    assert result["agent_used"] is False
    assert any("按原文读取" in warning for warning in result["warnings"])


def test_pandoc_keeps_editable_word_equation_as_latex(isolated_data, tmp_path, monkeypatch):
    pandoc = shutil.which("pandoc")
    if not pandoc:
        return
    source = tmp_path / "formula.md"
    word = tmp_path / "formula.docx"
    source.write_text("由 $F=ma$ 可得 $a=\\frac{F}{m}$。", encoding="utf-8")
    subprocess.run([pandoc, str(source), "-o", str(word)], check=True)
    monkeypatch.setattr(documents, "opencode_available", lambda: False)

    result = documents.convert_docx_path(word)

    compact = result["markdown"].replace(" ", "")
    assert "$F=ma$" in compact
    assert "\\frac{F}{m}" in compact
    assert any("可编辑" in warning for warning in result["warnings"])


def test_normalize_converted_markdown_keeps_emphasis_and_converts_html_image():
    markdown = (
        '万有引力的大小为 *F*。\n\n'
        '<img src="/tmp/media/image2.png" '
        'style="width:5.77in;height:1.17in" alt="@@@DRAWING-ID" />'
    )

    normalized = documents.normalize_converted_markdown(markdown, "")

    assert "*F*" in normalized
    assert '<img src=' not in normalized
    assert "![题图](/tmp/media/image2.png){width=5.77in height=1.17in}" in normalized
