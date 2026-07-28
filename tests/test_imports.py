import asyncio
import json
from io import BytesIO

import pymupdf
from PIL import Image
from starlette.datastructures import UploadFile

from app import config, storage
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


def test_digital_pdf_creates_review_drafts(isolated_data):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "1. First physics question")
    page.insert_text((72, 110), "2. Second physics question")
    pdf_bytes = document.tobytes()
    document.close()

    task = asyncio.run(imports.create_import_task(upload("questions.pdf", pdf_bytes)))

    assert task["status"] == "待审核"
    assert len(task["drafts"]) == 2
    assert [item["original_number"] for item in task["drafts"]] == ["1", "2"]
    assert all(item["source_kind"] == "digital_pdf" for item in task["drafts"])
    assert not list(config.QUESTIONS_DIR.glob("*.md"))


def test_image_without_ocr_stays_pending_with_original_image(isolated_data, monkeypatch):
    buffer = BytesIO()
    Image.new("RGB", (160, 100), "white").save(buffer, format="PNG")
    monkeypatch.setattr(imports, "ocr_available", lambda: False)

    task = asyncio.run(imports.create_import_task(upload("photo.png", buffer.getvalue())))

    assert len(task["drafts"]) == 1
    draft = task["drafts"][0]
    assert draft["confidence"] == 0
    assert draft["requires_attention"] is True
    assert draft["images"]
    assert (config.DRAFT_ASSETS_DIR / draft["draft_id"] / draft["images"][0]["name"]).exists()


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
