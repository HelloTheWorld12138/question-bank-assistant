from app import config, storage


def test_markdown_round_trip_uses_schema_and_canonical_difficulty(isolated_data):
    metadata = {
        "id": "LXCX0001",
        "板块": "力学",
        "主类型": "创新题",
        "类型": ["创新题"],
        "知识点": ["牛顿第二定律"],
        "难度": 3,
        "年份": 2026,
        "来源": "测试样本",
        "解析来源": "教师上传",
        "图片": [],
    }
    sections = {"题目": "求物体加速度。", "答案": "3 m/s²", "解析": "由 F=ma。", "备注": ""}

    path = storage.write_question("LXCX0001", metadata, sections)
    loaded_metadata, loaded_sections = storage.read_question("LXCX0001")

    assert path == config.QUESTIONS_DIR / "LXCX0001.md"
    assert loaded_metadata["schema_version"] == config.SCHEMA_VERSION
    assert loaded_metadata["难度系数"] == 3
    assert "难度" not in loaded_metadata
    assert loaded_metadata["创建时间"]
    assert loaded_metadata["更新时间"]
    assert loaded_sections == sections


def test_old_markdown_difficulty_remains_readable(isolated_data):
    old_markdown = """---
id: LXJC0001
板块: 力学
主类型: 基础题
难度: 2
---

# 题目

旧题正文

# 答案

A

# 解析

旧解析

# 备注
"""
    (config.QUESTIONS_DIR / "LXJC0001.md").write_text(old_markdown, encoding="utf-8")

    metadata, sections = storage.read_question("LXJC0001")

    assert metadata["schema_version"] == config.SCHEMA_VERSION
    assert metadata["难度系数"] == 2
    assert sections["题目"] == "旧题正文"


def test_read_all_questions_exposes_compatible_fields(isolated_data):
    storage.write_question(
        "DXJD0001",
        {"id": "DXJD0001", "板块": "电学", "主类型": "经典题", "难度系数": "0.65"},
        {"题目": "电路题", "答案": "B", "解析": "解析", "备注": ""},
    )

    item = storage.read_all_questions()[0]

    assert item["难度"] == "0.65"
    assert item["难度系数"] == "0.65"
    assert item["preview"] == "电路题"
