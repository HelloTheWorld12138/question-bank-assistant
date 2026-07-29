import asyncio
import json
from io import BytesIO

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from app import config, storage
from app.errors import AppError
from app.services import imports


def upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


def test_split_numbered_questions_and_match_answers():
    chunks = imports.split_numbered_content(
        "试卷标题\n\n1. 第一题内容\nA. 选项\n\n2．第二题内容\n（1）小问"
    )
    assert [item["original_number"] for item in chunks] == ["1", "2"]
    assert "试卷标题" in chunks[0]["content"]

    answers = imports.split_numbered_content("1. A\n2. B，解析如下")
    matched = imports.match_answer_segments(chunks, answers)
    assert matched[0]["answer"] == "A"
    assert matched[1]["answer"].startswith("B")
    assert all(item["answer_match"] == "exact" for item in matched)


def test_teacher_answer_sections_remove_repeated_question_and_read_metadata():
    questions = imports.split_numbered_content("1. 原题正文\nA. 选项一\nB. 选项二")
    answers = imports.split_numbered_content(
        "1. 原题正文\nA. 选项一\nB. 选项二\n\n"
        "【答案】B\n\n"
        "【难度】0.65\n\n"
        "【来源】高三联考\n\n"
        "【知识点】圆锥摆问题、牛顿第二定律\n\n"
        "【详解】只保留这一段解析。"
    )

    matched = imports.match_answer_segments(questions, answers)

    assert matched[0]["answer"] == "B"
    assert matched[0]["analysis"] == "只保留这一段解析。"
    assert "原题正文" not in matched[0]["answer"]
    assert "原题正文" not in matched[0]["analysis"]
    assert matched[0]["difficulty"] == "0.65"
    assert matched[0]["source"] == "高三联考"
    assert matched[0]["knowledge_points"] == ["圆锥摆问题", "牛顿第二定律"]


def test_unrecognized_long_answer_layout_is_left_for_manual_review():
    questions = imports.split_numbered_content("1. 原题正文")
    answers = imports.split_numbered_content("1. " + "未标明栏目且结构不确定。" * 20)

    matched = imports.match_answer_segments(questions, answers)

    assert matched[0]["answer"] == ""
    assert matched[0]["analysis"] == ""
    assert matched[0]["answer_format_recognized"] is False


def test_apply_teacher_answer_metadata_and_analysis_image(isolated_data, tmp_path):
    answer_assets = tmp_path / "answer-assets"
    answer_assets.mkdir()
    analysis_image = answer_assets / "analysis.png"
    Image.new("RGB", (60, 40), "white").save(analysis_image)
    drafts = [
        {
            "id": "draft-1",
            "original_number": "1",
            "question": "原题正文",
            "answer": "",
            "analysis": "",
            "difficulty": "",
            "year": "",
            "source": "题目文件.docx",
            "knowledge_points": [],
            "extra_types": [],
            "question_type": "选择题",
            "block_code": "ZH",
            "type_code": "JD",
            "warnings": [],
            "requires_attention": False,
            "draft_id": "",
            "images": [],
        }
    ]
    segments = imports.split_numbered_content(
        "1. 原题正文\n"
        "【答案】A\n"
        "【难度】0.7\n"
        "【来源】教师版试卷\n"
        "【知识点】向心力、圆锥摆\n"
        "【详解】受力图如下：![](/draft-assets/source/media/analysis.png)"
    )

    imports._apply_answers(
        drafts,
        segments,
        source_dir=answer_assets,
        assets={"analysis.png": analysis_image},
    )

    draft = drafts[0]
    assert draft["answer"] == "A"
    assert draft["difficulty"] == "0.7"
    assert draft["source"] == "教师版试卷"
    assert draft["knowledge_points"] == ["向心力", "圆锥摆"]
    assert "/draft-assets/source/" not in draft["analysis"]
    assert draft["images"][0]["name"] == "analysis.png"
    assert (config.DRAFT_ASSETS_DIR / draft["draft_id"] / "analysis.png").is_file()
    draft.update({"confirmed": True, "remarks": ""})
    task = {
        "id": "a7e7e03f-e1d4-46a0-9864-4c1088ec4ed7",
        "status": "待审核",
        "source": "题目文件.docx",
        "drafts": drafts,
    }
    imports.save_import_task(task)

    result = asyncio.run(
        imports.commit_import_task(
            task["id"],
            {"drafts": drafts, "selected_ids": ["draft-1"]},
        )
    )

    metadata, sections = storage.read_question(result["created"][0]["id"])
    assert metadata["难度系数"] == "0.7"
    assert metadata["知识点"] == ["向心力", "圆锥摆"]
    assert sections["答案"] == "A"
    assert "../assets/" in sections["解析"]
    assert (config.ASSETS_DIR / metadata["图片"][0]).is_file()


def test_image_preprocessing_rotation_crop_and_enhance(tmp_path):
    source = tmp_path / "source.png"
    target = tmp_path / "target.png"
    Image.new("RGB", (100, 60), "white").save(source)

    result = imports.preprocess_image(
        source,
        target,
        rotation=90,
        crop={"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.9},
        enhance=True,
    )

    assert target.exists()
    assert result["width"] == 48
    assert result["height"] == 80


def test_draft_image_enhancement_can_be_cancelled(isolated_data):
    task_id = "3e759d70-ebc7-460d-b126-af0aa6dfdc20"
    draft_asset_id = "4d25d712-229d-4ced-9911-d8551f4efb3d"
    draft_dir = config.DRAFT_ASSETS_DIR / draft_asset_id
    draft_dir.mkdir(parents=True)
    image_path = draft_dir / "photo.png"
    image = Image.new("RGB", (80, 50), "#b9b9b9")
    for x in range(20, 60):
        for y in range(15, 35):
            image.putpixel((x, y), (30, 30, 30))
    image.save(image_path, format="PNG")
    original = image_path.read_bytes()
    task = {
        "id": task_id,
        "status": "待审核",
        "drafts": [
            {
                "id": "draft-1",
                "question": f"题图 ![](/draft-assets/{draft_asset_id}/photo.png)",
                "answer": "",
                "analysis": "",
                "remarks": "",
                "draft_id": draft_asset_id,
                "images": [{"name": "photo.png", "url": f"/draft-assets/{draft_asset_id}/photo.png"}],
                "formula_image_names": [],
                "confirmed": True,
            }
        ],
    }
    imports.save_import_task(task)

    imports.process_draft_image(task_id, "draft-1", "photo.png", {"action": "enhance"})
    enhanced = imports.load_import_task(task_id)["drafts"][0]["images"][0]
    assert enhanced["enhanced"] is True
    assert image_path.read_bytes() != original

    imports.process_draft_image(task_id, "draft-1", "photo.png", {"action": "enhance"})
    restored = imports.load_import_task(task_id)["drafts"][0]["images"][0]
    assert restored["enhanced"] is False
    assert image_path.read_bytes() == original


@pytest.mark.parametrize("filename", ["questions.pdf", "photo.png", "legacy.doc"])
def test_batch_import_rejects_non_docx_files(isolated_data, filename):
    with pytest.raises(AppError, match="仅支持 .docx Word 文件"):
        asyncio.run(imports.create_import_task(upload(filename, b"unsupported")))


def test_batch_import_rejects_non_docx_answer_file(isolated_data):
    with pytest.raises(AppError, match="不支持 PDF"):
        asyncio.run(
            imports.create_import_task(
                upload("questions.docx", b"docx"),
                upload("answers.pdf", b"pdf"),
            )
        )


def test_batch_import_combines_question_and_answer_mathtype_summaries(
    isolated_data,
    monkeypatch,
):
    question_summary = {
        "detected": 163,
        "converted": 163,
        "failed": 0,
        "formulas": [{"marker": "QBMATH000001", "status": "converted"}],
    }
    answer_summary = {
        "detected": 358,
        "converted": 357,
        "failed": 1,
        "formulas": [{"marker": "QBMATH000001", "status": "needs_review"}],
    }
    monkeypatch.setattr(
        imports,
        "_drafts_from_docx",
        lambda path, source_name: ([], question_summary),
    )
    monkeypatch.setattr(
        imports,
        "_plain_segments_from_path",
        lambda path, work_dir: ([], None, {}, answer_summary),
    )

    task = asyncio.run(
        imports.create_import_task(
            upload("questions.docx", b"questions"),
            upload("answers.docx", b"answers"),
        )
    )

    assert task["mathtype"]["detected"] == 521
    assert task["mathtype"]["converted"] == 520
    assert task["mathtype"]["failed"] == 1
    assert task["mathtype"]["sources"] == [
        {
            "role": "question",
            "source": "questions.docx",
            "detected": 163,
            "converted": 163,
            "failed": 0,
        },
        {
            "role": "answer",
            "source": "answers.docx",
            "detected": 358,
            "converted": 357,
            "failed": 1,
        },
    ]
    assert [item["source_role"] for item in task["mathtype"]["formulas"]] == [
        "question",
        "answer",
    ]


def test_commit_confirmed_import_drafts(isolated_data):
    task = {
        "id": "9d875813-bec5-4c6d-90c0-37bcf010e20c",
        "status": "待审核",
        "created_at": "2026-07-26T00:00:00+08:00",
        "source": "manual-test",
        "drafts": [
            {
                "id": "draft-1",
                "original_number": "1",
                "question": "第一题",
                "answer": "A",
                "analysis": "解析一",
                "remarks": "",
                "block_code": "LX",
                "type_code": "JC",
                "question_type": "选择题",
                "knowledge_points": ["牛顿第二定律"],
                "extra_types": [],
                "difficulty": "0.7",
                "year": "2026",
                "source": "导入测试",
                "draft_id": "",
                "images": [],
                "confirmed": True,
            },
            {
                "id": "draft-2",
                "original_number": "2",
                "question": "第二题",
                "answer": "",
                "analysis": "",
                "remarks": "",
                "block_code": "DX",
                "type_code": "JD",
                "question_type": "计算题",
                "knowledge_points": [],
                "extra_types": [],
                "difficulty": "",
                "year": "",
                "source": "导入测试",
                "draft_id": "",
                "images": [],
                "confirmed": False,
            },
        ],
    }
    imports.save_import_task(task)

    result = asyncio.run(
        imports.commit_import_task(
            task["id"],
            {"drafts": task["drafts"], "selected_ids": ["draft-1"]},
        )
    )

    assert result["created"][0]["id"] == "LXJC0001"
    metadata, sections = storage.read_question("LXJC0001")
    assert metadata["题型"] == "选择题"
    assert sections["答案"] == "A"
    assert imports.load_import_task(task["id"])["status"] == "部分入库"


def test_existing_import_draft_normalizes_two_column_options_when_loaded(isolated_data):
    task_id = "2f840a82-3e5c-43a5-a7a7-43161eb95c09"
    task = {
        "id": task_id,
        "status": "待审核",
        "drafts": [
            {
                "id": "draft-1",
                "question": "A. 选项一 B. 选项二\nC. 选项三 D. 选项四",
                "answer": "",
                "analysis": "",
                "remarks": "",
            }
        ],
    }
    storage.ensure_dirs()
    storage.atomic_write_text(
        imports.task_path(task_id),
        json.dumps(task, ensure_ascii=False, indent=2) + "\n",
    )

    loaded = imports.load_import_task(task_id)

    assert loaded["drafts"][0]["question"] == (
        "A. 选项一\nB. 选项二\nC. 选项三\nD. 选项四"
    )


def test_split_and_merge_import_drafts(isolated_data):
    task = {
        "id": "8ac0b4f2-60b5-4acc-82e1-bf97f9708d28",
        "status": "待审核",
        "created_at": "2026-07-26T00:00:00+08:00",
        "source": "split-test",
        "drafts": [
            {
                "id": "draft-a",
                "original_number": "1",
                "question": "第一部分文字\n第二部分文字",
                "answer": "",
                "analysis": "",
                "remarks": "",
                "block_code": "LX",
                "type_code": "JC",
                "question_type": "计算题",
                "knowledge_points": [],
                "extra_types": [],
                "difficulty": "",
                "year": "",
                "source": "测试",
                "draft_id": "",
                "images": [],
                "warnings": [],
                "confidence": 1,
                "requires_attention": False,
                "answer_match": "unmatched",
                "confirmed": False,
                "committed_id": "",
            }
        ],
    }
    imports.save_import_task(task)
    position = task["drafts"][0]["question"].index("\n")

    split = imports.split_import_draft(task["id"], "draft-a", position)
    assert len(split["drafts"]) == 2
    assert split["drafts"][1]["question"] == "第二部分文字"

    merged = imports.merge_import_drafts(
        task["id"],
        split["drafts"][0]["id"],
        split["drafts"][1]["id"],
    )
    assert len(merged["drafts"]) == 1
    assert "第一部分文字" in merged["drafts"][0]["question"]
    assert "第二部分文字" in merged["drafts"][0]["question"]


def test_materialize_chunk_deduplicates_repeated_image(isolated_data, tmp_path):
    source = tmp_path / "formula.wmf"
    source.write_bytes(b"fake-wmf")
    markdown = "公式：![](formula.wmf)，再次出现：![](formula.wmf)"

    converted, draft_id, images = imports._materialize_chunk(
        markdown,
        source_dir=tmp_path,
        assets={"formula.wmf": source},
    )

    assert converted.count(f"/draft-assets/{draft_id}/formula.wmf") == 2
    assert [item["name"] for item in images] == ["formula.wmf"]


def test_replace_draft_metafile_updates_markdown_and_file(isolated_data):
    task_id = "fbdb97fe-a9f0-4a42-a730-b5147b1742cc"
    draft_asset_id = "f973431e-90ab-481b-bc94-a87905335f38"
    draft_dir = config.DRAFT_ASSETS_DIR / draft_asset_id
    draft_dir.mkdir(parents=True)
    (draft_dir / "formula.wmf").write_bytes(b"fake-wmf")
    old_url = f"/draft-assets/{draft_asset_id}/formula.wmf"
    task = {
        "id": task_id,
        "status": "待审核",
        "created_at": "2026-07-26T00:00:00+08:00",
        "source": "mathtype.docx",
        "drafts": [
            {
                "id": "draft-1",
                "question": f"由 ![公式]({old_url}) 可得 *F*。",
                "answer": "",
                "analysis": "",
                "remarks": "",
                "draft_id": draft_asset_id,
                "images": [{"name": "formula.wmf", "url": old_url}],
                "formula_image_names": ["formula.wmf"],
                "confirmed": True,
            }
        ],
    }
    imports.save_import_task(task)
    buffer = BytesIO()
    Image.new("RGB", (64, 24), "white").save(buffer, format="PNG")

    result = asyncio.run(
        imports.replace_draft_metafile(
            task_id,
            "draft-1",
            "formula.wmf",
            upload("formula.png", buffer.getvalue()),
        )
    )

    updated = imports.load_import_task(task_id)["drafts"][0]
    assert result["converted_name"] == "formula.png"
    assert "formula.png" in updated["question"]
    assert "formula.wmf" not in updated["question"]
    assert updated["formula_image_names"] == ["formula.png"]
    assert updated["confirmed"] is False
    assert (draft_dir / "formula.png").is_file()
    assert not (draft_dir / "formula.wmf").exists()
