import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

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


def test_formula_image_can_be_kept_and_unused_draft_image_is_discarded(isolated_data):
    draft_id = "276a6876-3a0e-4fb2-b018-c161d33ebaa7"
    draft_dir = config.DRAFT_ASSETS_DIR / draft_id
    draft_dir.mkdir(parents=True)
    formula = draft_dir / "formula.png"
    unused = draft_dir / "unused.png"
    Image.new("RGB", (120, 40), "white").save(formula)
    Image.new("RGB", (800, 600), "white").save(unused)
    formula_url = f"/draft-assets/{draft_id}/{formula.name}"
    question_text = f"求加速度。\n\n![公式]({formula_url})"

    with pytest.raises(AppError, match="请先处理"):
        asyncio.run(
            questions.create_question(
                block_code="LX",
                type_code="JC",
                question_text=question_text,
                draft_id=draft_id,
            )
        )

    created = asyncio.run(
        questions.create_question(
            block_code="LX",
            type_code="JC",
            question_text=question_text,
            draft_id=draft_id,
            approved_formula_images=[formula.name],
        )
    )

    metadata, sections = storage.read_question(created["id"])
    assert metadata["图片"] == ["LXJC0001_01.png"]
    assert "LXJC0001_01.png" in sections["题目"]
    assert (config.ASSETS_DIR / "LXJC0001_01.png").exists()
    assert not any(path.name.endswith("_02.png") for path in config.ASSETS_DIR.iterdir())


def test_uploaded_image_token_is_placed_and_normalized_to_png(isolated_data):
    image_buffer = BytesIO()
    Image.new("RGB", (320, 180), "#ddeeff").save(image_buffer, format="JPEG")
    image_buffer.seek(0)
    upload = UploadFile(filename="diagram.jpg", file=image_buffer)
    token = "upload-image://diagram-1"

    created = asyncio.run(
        questions.create_question(
            block_code="LX",
            type_code="JC",
            question_text=f"如图所示。\n\n![题图]({token}){{width=70%}}",
            files=[upload],
            upload_image_tokens=[token],
        )
    )

    metadata, sections = storage.read_question(created["id"])
    assert metadata["图片"] == ["LXJC0001_01.png"]
    assert "../assets/LXJC0001_01.png" in sections["题目"]
    assert (config.ASSETS_DIR / "LXJC0001_01.png").read_bytes().startswith(b"\x89PNG")


def test_multiple_uploaded_images_are_placed_and_saved_in_order(isolated_data):
    first_buffer = BytesIO()
    second_buffer = BytesIO()
    Image.new("RGB", (320, 180), "#ddeeff").save(first_buffer, format="JPEG")
    Image.new("RGB", (240, 160), "#ffeedd").save(second_buffer, format="PNG")
    first_buffer.seek(0)
    second_buffer.seek(0)
    uploads = [
        UploadFile(filename="diagram-a.jpg", file=first_buffer),
        UploadFile(filename="diagram-b.png", file=second_buffer),
    ]
    tokens = ["upload-image://diagram-a", "upload-image://diagram-b"]
    question_text = (
        f"观察两幅图。\n\n![题图一]({tokens[0]})\n\n![题图二]({tokens[1]})"
    )

    created = asyncio.run(
        questions.create_question(
            block_code="LX",
            type_code="JC",
            question_text=question_text,
            files=uploads,
            upload_image_tokens=tokens,
        )
    )

    metadata, sections = storage.read_question(created["id"])
    assert metadata["图片"] == ["LXJC0001_01.png", "LXJC0001_02.png"]
    assert "../assets/LXJC0001_01.png" in sections["题目"]
    assert "../assets/LXJC0001_02.png" in sections["题目"]
    assert (config.ASSETS_DIR / "LXJC0001_01.png").read_bytes().startswith(b"\x89PNG")
    assert (config.ASSETS_DIR / "LXJC0001_02.png").read_bytes().startswith(b"\x89PNG")


def test_non_image_question_attachment_is_rejected(isolated_data):
    upload = UploadFile(filename="source.docx", file=BytesIO(b"not-an-image"))

    with pytest.raises(AppError, match="只能上传题目图片"):
        asyncio.run(
            questions.create_question(
                block_code="LX",
                type_code="JC",
                question_text="测试题目",
                files=[upload],
            )
        )

    assert not list(config.QUESTIONS_DIR.glob("*.md"))


def test_raw_word_html_image_is_materialized_from_draft(isolated_data):
    draft_id = "88825861-b762-4c69-aa6b-d1f536a9f879"
    draft_dir = config.DRAFT_ASSETS_DIR / draft_id / "media"
    draft_dir.mkdir(parents=True)
    source = draft_dir / "diagram.png"
    Image.new("RGB", (640, 300), "#eef3f7").save(source)
    raw_html = (
        f'<img src="/draft-assets/{draft_id}/media/diagram.png" '
        'style="width:5.5in;height:1.5in" alt="@@@WORD-DRAWING" />'
    )

    created = asyncio.run(
        questions.create_question(
            block_code="LX",
            type_code="JC",
            question_text=f"如图所示。\n\n{raw_html}",
            draft_id=draft_id,
        )
    )

    metadata, sections = storage.read_question(created["id"])
    assert metadata["图片"] == ["LXJC0001_01.png"]
    assert '<img src=' not in sections["题目"]
    assert "![题图](../assets/LXJC0001_01.png){width=5.5in height=1.5in}" in sections["题目"]
    assert (config.ASSETS_DIR / "LXJC0001_01.png").is_file()


def test_unbalanced_formula_is_rejected_before_saving(isolated_data):
    with pytest.raises(AppError, match="公式格式需要检查"):
        asyncio.run(
            questions.create_question(
                block_code="LX",
                type_code="JC",
                question_text="由 $F=ma 求加速度。",
            )
        )


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
    assert (
        "--from=markdown+tex_math_dollars+raw_attribute+link_attributes+hard_line_breaks"
        in captured_command
    )
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


def test_update_question_removes_unreferenced_bound_image(isolated_data):
    image = config.ASSETS_DIR / "LXJC0001_01.png"
    Image.new("RGB", (120, 80), "white").save(image)
    storage.write_question(
        "LXJC0001",
        {
            "id": "LXJC0001",
            "板块": "力学",
            "主类型": "基础题",
            "类型": ["基础题"],
            "图片": [image.name],
        },
        {
            "题目": f"如图所示。\n\n![](../assets/{image.name})",
            "答案": "",
            "解析": "",
            "备注": "",
        },
    )

    questions.update_question(
        "LXJC0001",
        {
            "metadata": {"图片": []},
            "sections": {"题目": "图片已移除。"},
        },
    )

    metadata, sections = storage.read_question("LXJC0001")
    assert metadata["图片"] == []
    assert "LXJC0001_01.png" not in sections["题目"]
    assert not image.exists()


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


def test_copy_question_gets_new_id_and_copies_bound_images(isolated_data):
    image = config.ASSETS_DIR / "LXJC0001_01.png"
    image.write_bytes(b"image")
    storage.write_question(
        "LXJC0001",
        {
            "id": "LXJC0001",
            "板块": "力学",
            "主类型": "基础题",
            "类型": ["基础题"],
            "知识点": ["速度"],
            "题型": "选择题",
            "图片": [image.name],
        },
        {
            "题目": "![](../assets/LXJC0001_01.png)\n原题",
            "答案": "A",
            "解析": "解析",
            "备注": "",
        },
    )

    copied = questions.copy_question("LXJC0001")

    assert copied["id"] == "LXJC0002"
    metadata, sections = storage.read_question("LXJC0002")
    assert metadata["复制自"] == "LXJC0001"
    assert metadata["图片"] == ["LXJC0002_01.png"]
    assert "LXJC0002_01.png" in sections["题目"]
    assert (config.ASSETS_DIR / "LXJC0002_01.png").read_bytes() == b"image"


def test_batch_update_and_sorted_search(isolated_data):
    for question_id, year, difficulty in (
        ("LXJC0001", "2025", "0.72"),
        ("LXJC0002", "2026", "0.45"),
    ):
        storage.write_question(
            question_id,
            {
                "id": question_id,
                "板块": "力学",
                "主类型": "基础题",
                "类型": ["基础题"],
                "知识点": ["速度"],
                "难度系数": difficulty,
                "年份": year,
                "题型": "选择题",
                "图片": [],
            },
            {"题目": f"{year} 年题目", "答案": "", "解析": "", "备注": ""},
        )

    result = questions.batch_update_questions(
        {
            "ids": ["LXJC0001", "LXJC0002"],
            "add_types": ["易错题"],
            "add_knowledge": ["匀变速直线运动"],
            "question_type": "计算题",
        }
    )
    assert result["updated"] == ["LXJC0001", "LXJC0002"]
    metadata, _ = storage.read_question("LXJC0001")
    assert metadata["类型"] == ["基础题", "易错题"]
    assert metadata["知识点"] == ["速度", "匀变速直线运动"]
    assert metadata["题型"] == "计算题"

    items = questions.search_questions(
        query="年题目",
        question_type="计算题",
        sort_by="difficulty",
        sort_order="asc",
    )
    assert [item["id"] for item in items] == ["LXJC0002", "LXJC0001"]


def test_export_set_keeps_custom_order_labels_and_separate_files(isolated_data, monkeypatch):
    for question_id, question_type in (("LXJC0001", "选择题"), ("LXJC0002", "计算题")):
        storage.write_question(
            question_id,
            {
                "id": question_id,
                "板块": "力学",
                "主类型": "基础题",
                "类型": ["基础题"],
                "知识点": [],
                "题型": question_type,
                "图片": [],
            },
            {
                "题目": f"{question_id} 的题目",
                "答案": f"{question_id} 的答案",
                "解析": f"{question_id} 的解析",
                "备注": "",
            },
        )
    monkeypatch.setattr(questions, "find_pandoc", lambda: None)

    exported = questions.export_exam_set(
        {
            "ids": ["LXJC0002", "LXJC0001"],
            "title": "分卷测试",
            "display_labels": {"LXJC0002": "A1", "LXJC0001": "A2"},
            "show_ids": False,
            "group_by_question_type": True,
            "class_name": "高二（1）班",
            "student_fields": True,
        }
    )

    assert [item["kind"] for item in exported["files"]] == ["questions", "answers", "analysis"]
    question_file = config.EXPORT_DIR / exported["files"][0]["exam_md_filename"]
    answer_file = config.EXPORT_DIR / exported["files"][1]["exam_md_filename"]
    analysis_file = config.EXPORT_DIR / exported["files"][2]["exam_md_filename"]
    question_markdown = question_file.read_text(encoding="utf-8")
    assert question_markdown.index("LXJC0002 的题目") < question_markdown.index("LXJC0001 的题目")
    assert "## A1." in question_markdown
    assert "高二（1）班" in question_markdown
    assert "姓名：__________" in question_markdown
    assert "LXJC0002 的答案" not in question_markdown
    assert "LXJC0002 的答案" in answer_file.read_text(encoding="utf-8")
    assert "LXJC0002 的解析" in analysis_file.read_text(encoding="utf-8")
