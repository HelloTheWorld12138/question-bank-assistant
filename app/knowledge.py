from __future__ import annotations

from functools import lru_cache

import yaml

from app import config


@lru_cache(maxsize=1)
def knowledge_by_block() -> dict[str, list[str]]:
    if not config.KNOWLEDGE_FILE.exists():
        return {name: [] for name in config.BLOCKS.values()}
    loaded = yaml.safe_load(config.KNOWLEDGE_FILE.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        return {name: [] for name in config.BLOCKS.values()}
    return {
        block: [str(item).strip() for item in loaded.get(block, []) if str(item).strip()]
        for block in config.BLOCKS.values()
    }


def all_knowledge_points() -> list[str]:
    result: list[str] = []
    for items in knowledge_by_block().values():
        for item in items:
            if item not in result:
                result.append(item)
    return result
