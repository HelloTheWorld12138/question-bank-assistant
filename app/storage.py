from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import yaml

from app import config
from app.errors import NotFoundError


SECTION_NAMES = ("题目", "答案", "解析", "备注")


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def ensure_dirs() -> None:
    config.QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    config.DRAFT_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    config.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not config.INDEX_FILE.exists():
        config.INDEX_FILE.write_text("{}", encoding="utf-8")


def load_index() -> dict[str, int]:
    ensure_dirs()
    try:
        data = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {}
    return {str(key): int(value) for key, value in data.items()}


def save_index(index: dict[str, int]) -> None:
    ensure_dirs()
    config.INDEX_FILE.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_lines(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


def split_markdown_sections(text: str) -> tuple[dict[str, Any], dict[str, str]]:
    metadata: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                loaded = yaml.safe_load(parts[1]) or {}
                metadata = loaded if isinstance(loaded, dict) else {}
            except yaml.YAMLError:
                metadata = {}
            body = parts[2]

    sections = {name: "" for name in SECTION_NAMES}
    current = "题目"
    collected: dict[str, list[str]] = {name: [] for name in SECTION_NAMES}
    for raw_line in body.splitlines():
        heading = raw_line.strip().lstrip("#").strip()
        if heading in sections:
            current = heading
            continue
        collected[current].append(raw_line)

    for name, lines in collected.items():
        sections[name] = "\n".join(lines).strip()
    return metadata, sections


def normalize_metadata(metadata: dict[str, Any], *, for_write: bool = False) -> dict[str, Any]:
    normalized = dict(metadata)
    normalized.setdefault("schema_version", config.SCHEMA_VERSION)
    if "难度系数" not in normalized and "难度" in normalized:
        normalized["难度系数"] = normalized.pop("难度")
    if for_write:
        timestamp = now_iso()
        normalized.setdefault("创建时间", timestamp)
        normalized["更新时间"] = timestamp
    return normalized


def build_markdown(metadata: dict[str, Any], sections: dict[str, str]) -> str:
    normalized = normalize_metadata(metadata, for_write=True)
    frontmatter = yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False).strip()
    return (
        f"---\n{frontmatter}\n---\n\n"
        f"# 题目\n\n{sections.get('题目', '').strip()}\n\n"
        f"# 答案\n\n{sections.get('答案', '').strip()}\n\n"
        f"# 解析\n\n{sections.get('解析', '').strip()}\n\n"
        f"# 备注\n\n{sections.get('备注', '').strip()}\n"
    )


def question_preview(text: str, length: int = 120) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:length] + ("..." if len(compact) > length else "")


def question_path(question_id: str):
    return config.QUESTIONS_DIR / f"{question_id}.md"


def write_question(question_id: str, metadata: dict[str, Any], sections: dict[str, str]):
    ensure_dirs()
    path = question_path(question_id)
    path.write_text(build_markdown(metadata, sections), encoding="utf-8")
    return path


def read_question(question_id: str) -> tuple[dict[str, Any], dict[str, str]]:
    path = question_path(question_id)
    if not path.exists():
        raise NotFoundError("题目不存在")
    metadata, sections = split_markdown_sections(path.read_text(encoding="utf-8"))
    return normalize_metadata(metadata), sections


def read_all_questions() -> list[dict[str, Any]]:
    ensure_dirs()
    questions: list[dict[str, Any]] = []
    for path in sorted(config.QUESTIONS_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        metadata, sections = split_markdown_sections(raw)
        metadata = normalize_metadata(metadata)
        difficulty = metadata.get("难度系数", "")
        questions.append(
            {
                "id": metadata.get("id", path.stem),
                "板块": metadata.get("板块", ""),
                "主类型": metadata.get("主类型", ""),
                "类型": metadata.get("类型", []),
                "知识点": metadata.get("知识点", []),
                "难度": difficulty,
                "难度系数": difficulty,
                "年份": metadata.get("年份", ""),
                "来源": metadata.get("来源", ""),
                "解析来源": metadata.get("解析来源", ""),
                "图片": metadata.get("图片", []),
                "题目": sections.get("题目", ""),
                "答案": sections.get("答案", ""),
                "解析": sections.get("解析", ""),
                "备注": sections.get("备注", ""),
                "preview": question_preview(sections.get("题目", "")),
            }
        )
    return questions
