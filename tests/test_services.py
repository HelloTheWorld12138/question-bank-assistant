import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import config, storage
from app.errors import AppError
from app.services import questions


def test_question_ids_increment_per_prefix(isolated_data):
    assert questions.next_question_id("LX", "CX") == "LXCX0001"
    assert questions.next_question_id("LX", "CX") == "LXCX0002"
    assert questions.next_question_id("DX", "JD") == "DXJD0001"


def test_failed_reservation_does_not_advance_index(isolated_data):
    with pytest.raises(RuntimeError):
        with questions.reserve_question_id("LX", "CX") as question_id:
            assert question_id == "LXCX0001"
            raise RuntimeError("模拟入库失败")

    assert storage.load_index() == {}
    assert questions.next_question_id("LX", "CX") == "LXCX0001"


def test_concurrent_question_ids_are_unique(isolated_data):
    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(lambda _: questions.next_question_id("LX", "CX"), range(20)))

    assert len(ids) == len(set(ids)) == 20
    assert set(ids) == {f"LXCX{number:04d}" for number in range(1, 21)}


def test_create_search_and_export_question(isolated_data, monkeypatch):
    created = asyncio.run(
        questions.create_question(
            block_code="LX",
            type_code="CX",
            difficulty="3",
            year="2026",
            source="教师自编",
            question_text="质量为 2 kg 的物体受 6 N 合力，求加速度。",
            answer_text="3 m/s²",
            analysis_text="由 F=ma。",
            knowledge_points="牛顿第二定律\n匀加速直线运动",
            extra_types="计算量大",
        )
    )

    assert created["id"] == "LXCX0001"
    results = questions.search_questions(block="力学", knowledge="牛顿第二定律")
    assert [item["id"] for item in results] == ["LXCX0001"]

    monkeypatch.setattr(questions, "find_pandoc", lambda: None)
    exported = questions.export_exam(
        {"ids": ["LXCX0001"], "mode": "analysis", "title": "高二力学周测"}
    )
    exam = (config.EXPORT_DIR / exported["exam_md_filename"]).read_text(encoding="utf-8")
    assert exported["docx_created"] is False
    assert "高二力学周测" in exported["exam_md_filename"]
    assert "【LXCX0001】" in exam
    assert "3 m/s²" in exam
    assert "由 F=ma" in exam

    second = questions.export_exam(
        {"ids": ["LXCX0001"], "mode": "questions", "title": "高二力学周测"}
    )
    assert second["exam_md_filename"] != exported["exam_md_filename"]


def test_export_rewrites_question_image_to_absolute_path(isolated_data):
    image_path = config.ASSETS_DIR / "LXJD0001_01.png"
    image_path.write_bytes(b"image")
    storage.write_question(
        "LXJD0001",
        {"id": "LXJD0001", "图片": [image_path.name]},
        {
            "题目": "![](../assets/LXJD0001_01.png)",
            "答案": "",
            "解析": "",
            "备注": "",
        },
    )

    rewritten = questions.rewrite_export_image_links(
        "![](../assets/LXJD0001_01.png)",
        ["LXJD0001_01.png"],
    )
    assert image_path.as_posix() in rewritten


def test_formal_export_uses_template_and_officecli_review(isolated_data, monkeypatch):
    storage.write_question(
        "LXJD0001",
        {
            "id": "LXJD0001",
            "板块": "力学",
            "主类型": "经典题",
            "图片": [],
        },
        {
            "题目": "由 $F=ma$ 求物体的加速度。",
            "答案": "$a=F/m$",
            "解析": "代入牛顿第二定律。",
            "备注": "",
        },
    )
    pandoc = isolated_data.parent / "pandoc"
    pandoc.write_text("test", encoding="utf-8")
    captured_command = []

    def fake_pandoc(command, **kwargs):
        captured_command.extend(command)
        output = Path(command[command.index("-o") + 1])
        output.write_bytes(b"docx")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(questions, "find_pandoc", lambda: str(pandoc))
    monkeypatch.setattr(questions.subprocess, "run", fake_pandoc)
    monkeypatch.setattr(
        questions.office,
        "officecli_status",
        lambda: {"available": True, "version": config.OFFICECLI_VERSION},
    )
    monkeypatch.setattr(
        questions.office,
        "validate_document",
        lambda path: {"ok": True, "message": "Validation passed"},
    )
    monkeypatch.setattr(
        questions.office,
        "inspect_issues",
        lambda path: {"count": 0, "issues": []},
    )
    monkeypatch.setattr(
        questions.office,
        "read_document_structure",
        lambda path, depth=1: {"type": "document"},
    )

    def fake_preview(path, output):
        output.write_text("<html>preview</html>", encoding="utf-8")
        return output

    monkeypatch.setattr(questions.office, "render_html", fake_preview)

    exported = questions.export_exam(
        {
            "ids": ["LXJD0001"],
            "mode": "analysis",
            "title": "牛顿定律练习",
            "template": "formal_exam",
            "duration": "45 分钟",
            "total_score": "100 分",
            "show_ids": False,
            "answers_new_page": True,
        }
    )

    markdown = (config.EXPORT_DIR / exported["exam_md_filename"]).read_text(encoding="utf-8")
    assert exported["docx_created"] is True
    assert exported["engine"] == "pandoc+officecli"
    assert exported["validation"]["ok"] is True
    assert exported["preview_filename"].endswith("_预览.html")
    assert (config.EXPORT_DIR / exported["preview_filename"]).exists()
    assert any(argument.startswith("--reference-doc=") for argument in captured_command)
    assert "formal_exam.docx" in " ".join(captured_command)
    assert "# 参考答案" in markdown
    assert "# 解析" in markdown
    assert 'w:type="page"' in markdown
    assert "【LXJD0001】" not in markdown


def test_update_question_keeps_id_and_changes_content(isolated_data):
    storage.write_question(
        "LXJC0001",
        {
            "id": "LXJC0001",
            "板块": "力学",
            "主类型": "基础题",
            "类型": ["基础题"],
            "知识点": ["速度"],
        },
        {"题目": "原题", "答案": "A", "解析": "", "备注": ""},
    )

    result = questions.update_question(
        "LXJC0001",
        {
            "metadata": {"id": "LXJC0001", "知识点": ["速度", "加速度"], "年份": "2026"},
            "sections": {"题目": "修改后的题目", "答案": "B"},
        },
    )

    metadata, sections = storage.read_question("LXJC0001")
    assert result["id"] == "LXJC0001"
    assert metadata["知识点"] == ["速度", "加速度"]
    assert sections["题目"] == "修改后的题目"
    assert sections["答案"] == "B"

    with pytest.raises(AppError, match="永久题号"):
        questions.update_question("LXJC0001", {"metadata": {"板块": "电学"}})

    with pytest.raises(AppError, match="题号格式"):
        storage.question_path("../../secrets")


def test_rebuild_index_uses_existing_question_files(isolated_data):
    storage.write_question(
        "LXCX0008",
        {"id": "LXCX0008"},
        {"题目": "题目 8", "答案": "", "解析": "", "备注": ""},
    )
    storage.write_question(
        "LXCX0012",
        {"id": "LXCX0012"},
        {"题目": "题目 12", "答案": "", "解析": "", "备注": ""},
    )
    storage.save_index({"LXCX": 1})

    assert storage.rebuild_index() == {"LXCX": 12}
    assert questions.next_question_id("LX", "CX") == "LXCX0013"
