import json

import httpx
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.services import models


def test_health_and_question_api(isolated_data):
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["schema_version"] == 1
        assert health.json()["source_revision"] == config.SOURCE_REVISION
        app_script = client.get("/app.js")
        assert app_script.status_code == 200
        assert app_script.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"
        options = client.get("/api/options")
        assert [item["name"] for item in options.json()["blocks"]] == [
            "力学",
            "电磁学",
            "热学",
            "光学",
            "近代物理",
            "物理实验",
            "物理学史、方法、单位制、常识",
        ]

        response = client.post(
            "/api/questions",
            data={
                "block_code": "LX",
                "type_code": "JC",
                "difficulty": "2",
                "year": "2026",
                "source": "接口测试",
                "question_text": "测试题目",
                "answer_text": "A",
                "analysis_text": "测试解析",
                "knowledge_points": "速度",
                "question_type": "选择题",
            },
        )
        assert response.status_code == 200
        assert response.json()["id"] == "LXJC0001"

        search = client.get("/api/questions", params={"block": "力学", "knowledge": "速度"})
        assert search.status_code == 200
        assert search.json()["items"][0]["id"] == "LXJC0001"

        detail = client.get("/api/questions/LXJC0001")
        assert detail.status_code == 200
        assert detail.json()["metadata"]["难度系数"] == "2"
        assert detail.json()["metadata"]["题型"] == "选择题"

        copied = client.post("/api/questions/LXJC0001/copy", json={})
        assert copied.status_code == 200
        assert copied.json()["id"] == "LXJC0002"

        batch = client.post(
            "/api/questions/batch-update",
            json={
                "ids": ["LXJC0001", "LXJC0002"],
                "add_types": ["易错题"],
                "add_knowledge": ["匀变速直线运动"],
                "question_type": "计算题",
            },
        )
        assert batch.status_code == 200
        assert batch.json()["count"] == 2

        sorted_search = client.get(
            "/api/questions",
            params={"question_type": "计算题", "query": "测试题目", "sort_by": "id", "sort_order": "desc"},
        )
        assert sorted_search.status_code == 200
        assert [item["id"] for item in sorted_search.json()["items"]] == ["LXJC0002", "LXJC0001"]

        updated = client.put(
            "/api/questions/LXJC0001",
            json={
                "metadata": {"知识点": ["速度", "加速度"]},
                "sections": {"题目": "修改后的测试题目"},
            },
        )
        assert updated.status_code == 200

        integrity = client.get("/api/integrity")
        assert integrity.status_code == 200
        assert integrity.json()["ok"] is True

        deleted = client.delete("/api/questions/LXJC0001")
        assert deleted.status_code == 200
        trash_id = deleted.json()["trash_id"]
        assert client.get("/api/questions/LXJC0001").status_code == 404

        restored = client.post(f"/api/trash/{trash_id}/restore")
        assert restored.status_code == 200
        assert client.get("/api/questions/LXJC0001").status_code == 200

        unsafe = client.get("/api/questions/../../secrets")
        assert unsafe.status_code in {400, 404}


def test_model_settings_test_and_classification_api(isolated_data, monkeypatch):
    secrets = {}

    class MemorySecrets:
        def get(self, provider):
            return secrets.get(provider, "")

        def set(self, provider, value):
            secrets[provider] = value

        def delete(self, provider):
            secrets.pop(provider, None)

    monkeypatch.setattr(models, "SECRET_STORE", MemorySecrets())
    draft = {
        "板块": "力学",
        "主类型": "经典题",
        "类型": ["经典题"],
        "知识点": ["牛顿第二定律"],
        "题型": "计算题",
        "难度系数": 0.5,
        "置信度": 0.88,
        "理由": "考查动力学",
        "警告": [],
    }

    def handler(request):
        body = json.loads(request.content)
        prompt = body["messages"][-1]["content"]
        content = {"ok": True} if '{"ok": true}' in prompt else draft
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]},
        )

    monkeypatch.setattr(models, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    with TestClient(app) as client:
        saved = client.put(
            "/api/models/settings",
            json={
                "provider": "aliyun",
                "api_key": "sk-test",
                "model": "qwen3.7-plus",
                "enabled": True,
                "max_retries": 0,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["settings"]["api_key_configured"] is True
        assert "api_key" not in saved.json()["settings"]

        tested = client.post("/api/models/test")
        assert tested.status_code == 200
        assert tested.json()["ok"] is True

        no_consent = client.post(
            "/api/ai/classify",
            json={"question_text": "测试题", "consent": False},
        )
        assert no_consent.status_code == 400
        assert no_consent.json()["code"] == "consent_required"

        classified = client.post(
            "/api/ai/classify",
            json={"question_text": "测试题", "consent": True},
        )
        assert classified.status_code == 200
        assert classified.json()["draft"]["板块"] == "力学"
        assert classified.json()["requires_confirmation"] is True


def test_batch_pdf_import_is_rejected(isolated_data):
    with TestClient(app) as client:
        analyzed = client.post(
            "/api/import/analyze",
            files={"file": ("questions.pdf", b"pdf", "application/pdf")},
        )
        assert analyzed.status_code == 400
        assert "仅支持 .docx Word 文件" in analyzed.json()["detail"]


def test_assistant_parse_and_recommend_api(isolated_data):
    from app import storage

    storage.write_question(
        "LXJC0001",
        {
            "id": "LXJC0001",
            "板块": "力学",
            "主类型": "基础题",
            "类型": ["基础题"],
            "知识点": ["牛顿第二定律"],
            "题型": "选择题",
            "难度系数": 0.8,
            "年份": 2026,
            "来源": "教师自编",
            "图片": [],
        },
        {"题目": "一个物体在恒力作用下运动。", "答案": "A", "解析": "略", "备注": ""},
    )
    with TestClient(app) as client:
        parsed = client.get("/api/assistant/parse", params={"query": "找1道力学基础题"})
        assert parsed.status_code == 200
        assert parsed.json()["blocks"] == ["力学"]

        recommended = client.post(
            "/api/assistant/recommend",
            json={"query": "找1道力学基础题，牛顿第二定律"},
        )
        assert recommended.status_code == 200
        assert recommended.json()["items"][0]["id"] == "LXJC0001"
        assert recommended.json()["requires_teacher_selection"] is True
