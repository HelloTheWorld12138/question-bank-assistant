import pytest

from app import storage
from app.errors import AppError
from app.services import assistant


def save_question(
    question_id,
    *,
    block,
    main_type,
    types,
    knowledge,
    question_type,
    difficulty,
    year,
    question,
    answer="A",
    analysis="教师解析",
):
    storage.write_question(
        question_id,
        {
            "id": question_id,
            "板块": block,
            "主类型": main_type,
            "类型": types,
            "知识点": knowledge,
            "题型": question_type,
            "难度系数": difficulty,
            "年份": year,
            "来源": "校内模拟",
            "图片": [],
        },
        {"题目": question, "答案": answer, "解析": analysis, "备注": ""},
    )


def test_parse_natural_language_constraints():
    parsed = assistant.parse_query(
        "找5道近三年力学创新题，中等难度，覆盖牛顿第二定律，约45分钟，带解析",
        current_year=2026,
    )
    assert parsed["count"] == 5
    assert parsed["minutes"] == 45
    assert parsed["blocks"] == ["力学"]
    assert parsed["types"] == ["创新题"]
    assert parsed["knowledge_points"] == ["牛顿第二定律"]
    assert parsed["year_from"] == 2024
    assert parsed["require_analysis"] is True


def test_local_recommendation_filters_before_ranking(isolated_data):
    save_question(
        "LXCX0001",
        block="力学",
        main_type="创新题",
        types=["创新题"],
        knowledge=["牛顿第二定律"],
        question_type="计算题",
        difficulty="0.62",
        year="2025",
        question="连接体动力学问题",
    )
    save_question(
        "LXCX0002",
        block="力学",
        main_type="创新题",
        types=["创新题"],
        knowledge=["牛顿第二定律"],
        question_type="选择题",
        difficulty="0.58",
        year="2024",
        question="图像判断问题",
        analysis="",
    )
    save_question(
        "DXCX0001",
        block="电学",
        main_type="创新题",
        types=["创新题"],
        knowledge=["欧姆定律"],
        question_type="计算题",
        difficulty="0.6",
        year="2025",
        question="电路问题",
    )

    result = assistant.recommend_questions(
        {"query": "找3道近三年力学创新题，中等难度，牛顿第二定律，带解析"}
    )

    assert [item["id"] for item in result["items"]] == ["LXCX0001"]
    assert result["candidate_count"] == 1
    assert result["requires_teacher_selection"] is True
    assert result["used_ai"] is False
    assert result["warnings"]


def test_ai_ranking_receives_candidates_only_after_local_filter(isolated_data, monkeypatch):
    save_question(
        "LXJC0001",
        block="力学",
        main_type="基础题",
        types=["基础题"],
        knowledge=["匀变速直线运动"],
        question_type="选择题",
        difficulty="0.85",
        year="2026",
        question="汽车从静止开始运动。",
        answer="保密答案",
        analysis="保密解析",
    )
    captured = {}

    monkeypatch.setattr(
        assistant.models,
        "load_model_settings",
        lambda: {"cloud": False},
    )

    def rank_question_candidates(**kwargs):
        captured.update(kwargs)
        return {"recommendations": [{"id": "LXJC0001", "reason": "基础巩固"}]}

    monkeypatch.setattr(assistant.models, "rank_question_candidates", rank_question_candidates)
    result = assistant.recommend_questions({"query": "找1道力学基础题", "use_ai": True})

    assert result["used_ai"] is True
    assert captured["candidates"][0]["id"] == "LXJC0001"
    assert "answer" not in captured["candidates"][0]
    assert "analysis" not in captured["candidates"][0]


def test_cloud_ai_recommendation_requires_consent(isolated_data, monkeypatch):
    save_question(
        "LXJC0001",
        block="力学",
        main_type="基础题",
        types=["基础题"],
        knowledge=[],
        question_type="选择题",
        difficulty="0.8",
        year="2026",
        question="测试题",
    )
    monkeypatch.setattr(assistant.models, "load_model_settings", lambda: {"cloud": True})

    with pytest.raises(AppError) as error:
        assistant.recommend_questions({"query": "找1道力学基础题", "use_ai": True})
    assert error.value.code == "consent_required"
