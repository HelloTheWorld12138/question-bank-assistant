from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import jsonschema
import keyring
from keyring.errors import KeyringError

from app import config, knowledge, storage
from app.errors import AppError


logger = logging.getLogger(__name__)
KEYRING_SERVICE = "PhysicsQuestionBankAssistant"
HTTP_TRANSPORT: httpx.BaseTransport | None = None
MIN_REQUEST_INTERVAL_SECONDS = 0.2
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0

PROVIDERS: dict[str, dict[str, Any]] = {
    "aliyun": {
        "name": "阿里云百炼 / 通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-plus",
        "cloud": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "cloud": True,
    },
    "custom": {
        "name": "其他兼容服务（含 LM Studio）",
        "base_url": "",
        "model": "",
        "cloud": True,
    },
    "ollama": {
        "name": "本机模型（Ollama）",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen3:8b",
        "cloud": False,
    },
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "local_only": False,
    "provider": "aliyun",
    "base_url": PROVIDERS["aliyun"]["base_url"],
    "model": PROVIDERS["aliyun"]["model"],
    "timeout_seconds": 45,
    "max_retries": 2,
}

CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["板块", "主类型", "类型", "知识点", "题型", "难度系数", "置信度", "理由", "警告"],
    "properties": {
        "板块": {"type": "string", "enum": list(config.BLOCK_OPTIONS.values())},
        "主类型": {"type": "string", "enum": list(config.TYPES.values())},
        "类型": {
            "type": "array",
            "items": {"type": "string", "enum": list(config.TYPES.values())},
            "uniqueItems": True,
            "minItems": 1,
        },
        "知识点": {
            "type": "array",
            "items": {"type": "string", "enum": knowledge.all_knowledge_points()},
            "uniqueItems": True,
            "maxItems": 12,
        },
        "题型": {"type": "string", "enum": list(config.QUESTION_TYPES)},
        "难度系数": {"type": "number", "minimum": 0, "maximum": 1},
        "置信度": {"type": "number", "minimum": 0, "maximum": 1},
        "理由": {"type": "string", "minLength": 1, "maxLength": 300},
        "警告": {
            "type": "array",
            "items": {"type": "string", "maxLength": 160},
            "maxItems": 8,
        },
    },
}


class SecretStore:
    def _username(self, provider: str) -> str:
        return f"{provider}-api-key"

    def get(self, provider: str) -> str:
        environment_names = {
            "aliyun": "DASHSCOPE_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "custom": "QUESTION_BANK_CUSTOM_API_KEY",
        }
        environment_value = os.getenv(environment_names.get(provider, ""), "")
        if environment_value:
            return environment_value
        try:
            return keyring.get_password(KEYRING_SERVICE, self._username(provider)) or ""
        except KeyringError:
            return ""

    def set(self, provider: str, value: str) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, self._username(provider), value)
        except KeyringError as exc:
            raise AppError(
                "访问密钥未能安全保存，请检查系统设置后重试。"
            ) from exc

    def delete(self, provider: str) -> None:
        try:
            keyring.delete_password(KEYRING_SERVICE, self._username(provider))
        except KeyringError:
            return


SECRET_STORE = SecretStore()


def _provider_defaults(provider: str) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise AppError("未知模型服务")
    spec = PROVIDERS[provider]
    return {
        **DEFAULT_SETTINGS,
        "provider": provider,
        "base_url": spec["base_url"],
        "model": spec["model"],
    }


def load_model_settings() -> dict[str, Any]:
    storage.ensure_dirs()
    raw: dict[str, Any] = {}
    if config.SETTINGS_FILE.exists():
        try:
            loaded = json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except (json.JSONDecodeError, OSError):
            raw = {}
    provider = str(raw.get("provider") or DEFAULT_SETTINGS["provider"])
    if provider not in PROVIDERS:
        provider = str(DEFAULT_SETTINGS["provider"])
    settings = {**_provider_defaults(provider), **raw, "provider": provider}
    settings.pop("api_key", None)
    settings["api_key_configured"] = bool(SECRET_STORE.get(provider))
    settings["provider_name"] = PROVIDERS[provider]["name"]
    settings["cloud"] = PROVIDERS[provider]["cloud"]
    return settings


def _validated_base_url(provider: str, value: Any) -> str:
    base_url = str(value or "").strip().rstrip("/")
    if not base_url:
        raise AppError("请填写模型服务地址")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise AppError("模型服务地址格式不正确")
    local_host = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not local_host:
        raise AppError("非本机模型服务必须使用 HTTPS")
    if provider == "ollama" and not local_host:
        raise AppError("Ollama 地址必须指向本机")
    return base_url


def save_model_settings(payload: dict[str, Any]) -> dict[str, Any]:
    previous = load_model_settings()
    provider = str(payload.get("provider") or previous["provider"])
    if provider not in PROVIDERS:
        raise AppError("未知模型服务")
    provider_changed = provider != previous["provider"]
    defaults = _provider_defaults(provider)
    base_url = _validated_base_url(
        provider,
        payload.get("base_url")
        if "base_url" in payload
        else defaults["base_url"] if provider_changed else previous["base_url"],
    )
    model = str(
        payload.get("model")
        if "model" in payload
        else defaults["model"] if provider_changed else previous["model"]
    ).strip()
    if not model or len(model) > 120:
        raise AppError("请填写有效的模型名称")
    timeout_seconds = int(payload.get("timeout_seconds", previous["timeout_seconds"]))
    max_retries = int(payload.get("max_retries", previous["max_retries"]))
    if not 5 <= timeout_seconds <= 300:
        raise AppError("连接超时应为 5～300 秒")
    if not 0 <= max_retries <= 3:
        raise AppError("重试次数应为 0～3 次")

    api_key = str(payload.get("api_key") or "").strip()
    if api_key:
        SECRET_STORE.set(provider, api_key)
    if payload.get("clear_api_key") is True:
        SECRET_STORE.delete(provider)

    settings = {
        "enabled": payload.get("enabled", previous["enabled"]) is True,
        "local_only": payload.get("local_only", previous["local_only"]) is True,
        "provider": provider,
        "base_url": base_url,
        "model": model,
        "timeout_seconds": timeout_seconds,
        "max_retries": max_retries,
    }
    storage.atomic_write_text(
        config.SETTINGS_FILE,
        json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
    )
    return load_model_settings()


def provider_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "name": value["name"],
            "default_base_url": value["base_url"],
            "default_model": value["model"],
            "cloud": value["cloud"],
        }
        for key, value in PROVIDERS.items()
    ]


def _rate_limit() -> None:
    global _LAST_REQUEST_AT
    with _RATE_LOCK:
        delay = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _LAST_REQUEST_AT)
        if delay > 0:
            time.sleep(delay)
        _LAST_REQUEST_AT = time.monotonic()


def _client(settings: dict[str, Any]) -> httpx.Client:
    kwargs: dict[str, Any] = {
        "timeout": httpx.Timeout(float(settings["timeout_seconds"])),
        "follow_redirects": False,
    }
    if HTTP_TRANSPORT is not None:
        kwargs["transport"] = HTTP_TRANSPORT
    return httpx.Client(**kwargs)


def _response_error(response: httpx.Response) -> AppError:
    messages = {
        401: "访问密钥无效，请重新检查。",
        402: "模型账户余额不足。",
        403: "当前访问密钥没有使用该模型的权限。",
        404: "模型名称或服务地址不存在。",
        429: "模型服务请求过于频繁，请稍后再试。",
    }
    message = messages.get(response.status_code, f"模型服务返回错误（HTTP {response.status_code}）。")
    return AppError(message, status_code=502, code="model_service_error")


def _request_json(
    settings: dict[str, Any],
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(int(settings["max_retries"]) + 1):
        _rate_limit()
        try:
            with _client(settings) as client:
                response = client.request(method, url, headers=headers, json=body)
            if response.status_code >= 400:
                if response.status_code not in {429, 500, 502, 503, 504} or attempt >= int(settings["max_retries"]):
                    raise _response_error(response)
                last_error = _response_error(response)
            else:
                data = response.json()
                if not isinstance(data, dict):
                    raise AppError("模型服务返回了无法识别的数据。", status_code=502)
                return data
        except AppError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt >= int(settings["max_retries"]):
                break
        time.sleep(min(0.5 * (2**attempt), 2.0))
    logger.warning("Model request failed provider=%s error=%s", settings["provider"], type(last_error).__name__)
    raise AppError(
        "无法连接模型服务。核心题库仍可离线使用，请检查网络、地址或稍后重试。",
        status_code=503,
        code="model_unavailable",
    )


def _content_as_json(content: Any) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip() if len(lines) > 2 else text
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AppError("模型没有返回有效 JSON，请重新生成或手动填写。", status_code=502) from exc
    if not isinstance(parsed, dict):
        raise AppError("模型返回格式不是对象，请重新生成或手动填写。", status_code=502)
    return parsed


class ModelProvider(ABC):
    def __init__(self, settings: dict[str, Any], api_key: str = "") -> None:
        self.settings = settings
        self.api_key = api_key

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def chat_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class OpenAICompatibleProvider(ModelProvider):
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def chat_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.settings["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        if self.settings["provider"] == "aliyun":
            body["enable_thinking"] = False
        data = _request_json(
            self.settings,
            method="POST",
            url=f"{self.settings['base_url']}/chat/completions",
            headers=self._headers(),
            body=body,
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AppError("模型响应缺少正文，请重试。", status_code=502) from exc
        return _content_as_json(content)

    def health_check(self) -> dict[str, Any]:
        result = self.chat_json(
            "只输出 JSON，不要解释。",
            '请回复 {"ok": true} 这一个 JSON 对象。',
            {
                "type": "object",
                "required": ["ok"],
                "properties": {"ok": {"type": "boolean"}},
            },
        )
        if result.get("ok") is not True:
            raise AppError("模型已连接，但未返回预期测试结果。", status_code=502)
        return {"ok": True, "model": self.settings["model"]}


class OllamaProvider(ModelProvider):
    def health_check(self) -> dict[str, Any]:
        data = _request_json(
            self.settings,
            method="GET",
            url=f"{self.settings['base_url']}/api/tags",
        )
        available = [str(item.get("name") or item.get("model") or "") for item in data.get("models", [])]
        model = self.settings["model"]
        return {"ok": True, "model": model, "model_available": model in available, "available_models": available}

    def chat_json(self, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        data = _request_json(
            self.settings,
            method="POST",
            url=f"{self.settings['base_url']}/api/chat",
            body={
                "model": self.settings["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "format": schema,
                "options": {"temperature": 0.1},
            },
        )
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise AppError("本地模型响应缺少正文，请重试。", status_code=502) from exc
        return _content_as_json(content)


def _configured_provider(*, require_enabled: bool) -> tuple[ModelProvider, dict[str, Any]]:
    settings = load_model_settings()
    if require_enabled and not settings["enabled"]:
        raise AppError("AI 辅助功能尚未启用。")
    if settings["local_only"] and settings["cloud"]:
        raise AppError("当前已开启“只使用本地功能”，不会连接云端模型。")
    api_key = SECRET_STORE.get(settings["provider"])
    local_base = urlparse(settings["base_url"]).hostname in {"127.0.0.1", "localhost", "::1"}
    if settings["provider"] != "ollama" and not api_key and not local_base:
        raise AppError("尚未保存该模型服务的访问密钥。")
    if settings["provider"] == "ollama":
        return OllamaProvider(settings), settings
    return OpenAICompatibleProvider(settings, api_key), settings


def test_model_connection() -> dict[str, Any]:
    provider, settings = _configured_provider(require_enabled=False)
    started = time.monotonic()
    result = provider.health_check()
    return {
        **result,
        "provider": settings["provider"],
        "provider_name": settings["provider_name"],
        "latency_ms": round((time.monotonic() - started) * 1000),
    }


def _classification_prompt(question_text: str) -> tuple[str, str]:
    system_prompt = (
        "你是高中物理题库整理助手。只做分类和元数据提取，不解题、不生成答案。"
        "必须输出一个严格 JSON 对象，不得增加 Markdown 或解释。"
        f"板块只能选：{'、'.join(config.BLOCK_OPTIONS.values())}。"
        f"主类型和类型只能选：{'、'.join(config.TYPES.values())}。"
        f"题型只能选：{'、'.join(config.QUESTION_TYPES)}。"
        f"知识点只能从以下标准字典中选择：{'、'.join(knowledge.all_knowledge_points())}。"
        "难度系数范围为 0 到 1，数值越小越难。主类型必须同时出现在类型数组中。"
    )
    user_prompt = (
        "请对下面这道高中物理题进行分类，以 JSON 格式返回板块、主类型、类型、知识点、"
        "题型、难度系数、置信度、理由和警告。题目原文如下：\n\n"
        f"{question_text[:12000]}"
    )
    return system_prompt, user_prompt


def _validate_classification(result: dict[str, Any]) -> dict[str, Any]:
    if "板块" in result:
        result["板块"] = config.canonical_block_name(result["板块"])
    if isinstance(result.get("难度系数"), str):
        try:
            result["难度系数"] = float(result["难度系数"])
        except ValueError:
            pass
    if isinstance(result.get("置信度"), str):
        try:
            result["置信度"] = float(result["置信度"])
        except ValueError:
            pass
    try:
        jsonschema.validate(result, CLASSIFICATION_SCHEMA)
    except jsonschema.ValidationError as exc:
        path = ".".join(str(item) for item in exc.absolute_path) or "根节点"
        raise AppError(f"模型结果格式校验失败（{path}），请重试或手动填写。", status_code=502) from exc
    if result["主类型"] not in result["类型"]:
        raise AppError("模型结果格式校验失败（主类型未包含在类型中）。", status_code=502)
    return result


def classify_question(payload: dict[str, Any]) -> dict[str, Any]:
    question_text = str(payload.get("question_text") or "").strip()
    if not question_text:
        raise AppError("请先填写题目正文。")
    provider, settings = _configured_provider(require_enabled=True)
    if settings["cloud"] and payload.get("consent") is not True:
        raise AppError("调用云模型前需要确认发送当前题目正文。", code="consent_required")
    system_prompt, user_prompt = _classification_prompt(question_text)
    result = _validate_classification(
        provider.chat_json(system_prompt, user_prompt, CLASSIFICATION_SCHEMA)
    )
    draft_id = str(uuid.uuid4())
    draft_record = {
        "id": draft_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "provider": settings["provider"],
        "model": settings["model"],
        "classification": result,
        "status": "待教师确认",
    }
    storage.atomic_write_text(
        config.AI_DRAFTS_DIR / f"{draft_id}.json",
        json.dumps(draft_record, ensure_ascii=False, indent=2) + "\n",
    )
    logger.info(
        "AI classification draft created provider=%s model=%s draft_id=%s",
        settings["provider"],
        settings["model"],
        draft_id,
    )
    return {
        "draft_id": draft_id,
        "draft": result,
        "requires_confirmation": True,
        "provider": settings["provider"],
        "model": settings["model"],
        "sent_fields": ["题目正文"],
    }


def rank_question_candidates(
    *,
    query: str,
    candidates: list[dict[str, Any]],
    count: int,
) -> dict[str, Any]:
    if not candidates:
        return {"recommendations": []}
    provider, _settings = _configured_provider(require_enabled=True)
    candidates = candidates[:50]
    candidate_ids = [str(item["id"]) for item in candidates]
    limit = max(1, min(int(count), len(candidate_ids)))
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["recommendations"],
        "properties": {
            "recommendations": {
                "type": "array",
                "minItems": 1,
                "maxItems": limit,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "reason"],
                    "properties": {
                        "id": {"type": "string", "enum": candidate_ids},
                        "reason": {"type": "string", "minLength": 1, "maxLength": 180},
                    },
                },
            }
        },
    }
    safe_candidates = [
        {
            "id": item["id"],
            "板块": item["block"],
            "类型": item["types"],
            "知识点": item["knowledge_points"],
            "题型": item["question_type"],
            "难度系数": item["difficulty"],
            "年份": item["year"],
            "来源": item["source"],
            "题目预览": item["preview"],
            "预计分钟": item["estimated_minutes"],
        }
        for item in candidates
    ]
    result = provider.chat_json(
        (
            "你是高中物理教师的选题助手。只允许从候选题号中排序并写简短推荐理由，"
            "不解题、不改题、不生成答案。必须输出严格 JSON。"
        ),
        (
            f"教师要求：{query[:1000]}\n"
            f"最多推荐 {limit} 道。候选题最少元数据如下：\n"
            f"{json.dumps(safe_candidates, ensure_ascii=False)}"
        ),
        schema,
    )
    try:
        jsonschema.validate(result, schema)
    except jsonschema.ValidationError as exc:
        raise AppError("模型推荐结果格式不正确，已回退到本地排序。", status_code=502) from exc
    recommendations = result["recommendations"]
    ids = [str(item["id"]) for item in recommendations]
    if len(ids) != len(set(ids)):
        raise AppError("模型推荐结果包含重复题号，已回退到本地排序。", status_code=502)
    return result
