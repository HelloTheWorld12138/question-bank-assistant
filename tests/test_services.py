import asyncio

from app import config, storage
from app.services import questions


def test_question_ids_increment_per_prefix(isolated_data):
    assert questions.next_question_id("LX", "CX") == "LXCX0001"
    assert questions.next_question_id("LX", "CX") == "LXCX0002"
    assert questions.next_question_id("DX", "JD") == "DXJD0001"


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
    exported = questions.export_exam({"ids": ["LXCX0001"], "mode": "analysis"})
    exam = (config.EXPORT_DIR / "exam.md").read_text(encoding="utf-8")
    assert exported["docx_created"] is False
    assert "【LXCX0001】" in exam
    assert "3 m/s²" in exam
    assert "由 F=ma" in exam

