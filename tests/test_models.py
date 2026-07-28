import json

import httpx
import pytest

from app import config
from app.errors import AppError
from app.services import models


class MemorySecrets:
    def __init__(self):
        self.values = {}

    def get(self, provider):
        return self.values.get(provider, "")

    def set(self, provider, value):
        self.values[provider] = value

    def delete(self, provider):
        self.values.pop(provider, None)


def test_settings_never_persist_api_key(isolated_data, monkeypatch):
    secrets = MemorySecrets()
    monkeypatch.setattr(models, "SECRET_STORE", secrets)

    saved = models.save_model_settings(
        {
            "provider": "aliyun",
            "model": "qwen3.7-plus",
            "api_key": "sk-secret",
            "enabled": True,
        }
    )

    raw = config.SETTINGS_FILE.read_text(encoding="utf-8")
    assert "sk-secret" not in raw
    assert json.loads(raw)["provider"] == "aliyun"
    assert saved["api_key_configured"] is True
    assert "api_key" not in saved
    assert secrets.get("aliyun") == "sk-secret"


def test_cloud_provider_requires_explicit_consent(isolated_data, monkeypatch):
    secrets = MemorySecrets()
    secrets.set("aliyun", "sk-test")
    monkeypatch.setattr(models, "SECRET_STORE", secrets)
    models.save_model_settings({"provider": "aliyun", "enabled": True})

    with pytest.raises(AppError, match="确认发送"):
        models.classify_question({"question_text": "测试题", "consent": False})


def test_openai_compatible_classification_validates_schema(isolated_data, monkeypatch):
    secrets = MemorySecrets()
    secrets.set("aliyun", "sk-test")
    monkeypatch.setattr(models, "SECRET_STORE", secrets)
    models.save_model_settings(
        {
            "provider": "aliyun",
            "model": "qwen3.7-plus",
            "enabled": True,
            "timeout_seconds": 5,
            "max_retries": 0,
        }
    )

    response_data = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "板块": "力学",
                            "主类型": "创新题",
                            "类型": ["创新题", "计算量大"],
                            "知识点": ["牛顿第二定律"],
                            "题型": "计算题",
                            "难度系数": 0.42,
                            "置信度": 0.91,
                            "理由": "需要建立动力学模型",
                            "警告": [],
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }

    def handler(request):
        assert request.url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-test"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert "答案" not in body["messages"][-1]["content"]
        return httpx.Response(200, json=response_data)

    monkeypatch.setattr(models, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    result = models.classify_question({"question_text": "如图，求物体加速度。", "consent": True})

    assert result["draft"]["板块"] == "力学"
    assert result["draft"]["题型"] == "计算题"
    assert result["requires_confirmation"] is True


def test_invalid_model_json_is_rejected(isolated_data, monkeypatch):
    secrets = MemorySecrets()
    secrets.set("deepseek", "sk-test")
    monkeypatch.setattr(models, "SECRET_STORE", secrets)
    models.save_model_settings(
        {"provider": "deepseek", "enabled": True, "max_retries": 0}
    )

    def handler(_):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"板块":"不存在"}'}}]},
        )

    monkeypatch.setattr(models, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    with pytest.raises(AppError, match="格式校验"):
        models.classify_question({"question_text": "测试题", "consent": True})


def test_ollama_health_and_classification_need_no_cloud_consent(isolated_data, monkeypatch):
    models.save_model_settings(
        {
            "provider": "ollama",
            "base_url": "http://127.0.0.1:11434",
            "model": "qwen3:8b",
            "enabled": True,
        }
    )

    draft = {
        "板块": "电学",
        "主类型": "经典题",
        "类型": ["经典题"],
        "知识点": ["闭合电路欧姆定律"],
        "题型": "选择题",
        "难度系数": 0.68,
        "置信度": 0.8,
        "理由": "考查基本规律",
        "警告": [],
    }

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})
        assert request.url.path == "/api/chat"
        return httpx.Response(200, json={"message": {"content": json.dumps(draft, ensure_ascii=False)}})

    monkeypatch.setattr(models, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    health = models.test_model_connection()
    result = models.classify_question({"question_text": "电路题", "consent": False})

    assert health["ok"] is True
    assert result["draft"]["板块"] == "电磁学"


def test_model_candidate_ranking_uses_minimal_metadata(isolated_data, monkeypatch):
    secrets = MemorySecrets()
    secrets.set("deepseek", "sk-test")
    monkeypatch.setattr(models, "SECRET_STORE", secrets)
    models.save_model_settings(
        {"provider": "deepseek", "enabled": True, "max_retries": 0}
    )

    def handler(request):
        body = json.loads(request.content)
        prompt = body["messages"][-1]["content"]
        assert "保密答案" not in prompt
        assert "完整解析" not in prompt
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "recommendations": [
                                        {"id": "LXCX0001", "reason": "匹配动力学创新情境"}
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(models, "HTTP_TRANSPORT", httpx.MockTransport(handler))
    result = models.rank_question_candidates(
        query="找一道力学创新题",
        count=1,
        candidates=[
            {
                "id": "LXCX0001",
                "block": "力学",
                "types": ["创新题"],
                "knowledge_points": ["牛顿第二定律"],
                "question_type": "计算题",
                "difficulty": "0.5",
                "year": "2026",
                "source": "教师自编",
                "preview": "如图，求物体加速度。",
                "estimated_minutes": 12,
            }
        ],
    )

    assert result["recommendations"][0]["id"] == "LXCX0001"
