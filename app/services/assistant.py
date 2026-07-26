from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app import config, knowledge, storage
from app.errors import AppError
from app.services import models


CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
    "十三": 13,
    "十四": 14,
    "十五": 15,
    "二十": 20,
}

BLOCK_ALIASES = {
    "CD": ("磁场与电磁感应", "电磁感应", "磁场", "电磁"),
    "XD": ("近代物理", "现代物理", "原子物理"),
    "SY": ("实验", "实验题"),
    "LX": ("力学",),
    "DX": ("电学", "电路"),
    "GX": ("光学",),
    "RX": ("热学", "热力学"),
    "ZH": ("综合", "综合题"),
}

TYPE_ALIASES = {
    "JS": ("计算量大", "大计算量", "计算繁"),
    "CX": ("创新题", "创新"),
    "YC": ("易错题", "易错"),
    "YZ": ("压轴题", "压轴", "拔高"),
    "JD": ("经典题", "经典"),
    "JC": ("基础题", "基础"),
    "MX": ("模型题", "模型"),
}

QUESTION_TYPE_ALIASES = {
    "选择题": ("选择题", "选择"),
    "填空题": ("填空题", "填空"),
    "实验题": ("实验题",),
    "计算题": ("计算题", "解答题", "大题"),
}

SOURCE_TERMS = ("高考", "模拟", "月考", "联考", "期中", "期末", "课后", "自编")


def _number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    return CHINESE_NUMBERS.get(value)


def _extract_number(text: str, suffix: str) -> tuple[int | None, bool]:
    match = re.search(rf"(\d{{1,3}}|[一二两三四五六七八九十]{{1,3}})\s*{suffix}", text)
    if not match:
        return None, False
    value = _number(match.group(1))
    return value, value is not None


def _difficulty_coefficient(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 0 <= parsed <= 1:
        return parsed
    if 1 <= parsed <= 5:
        return round((6 - parsed) / 5, 3)
    return None


def parse_query(query: str, *, current_year: int | None = None) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", str(query or "")).strip()
    if not text:
        raise AppError("请输入找题要求。")
    year_now = current_year or datetime.now().year

    count, count_explicit = _extract_number(text, "道")
    minutes, minutes_explicit = _extract_number(text, r"(?:分钟|分(?:钟)?)")
    count = max(1, min(count or 10, 100))
    minutes = max(5, min(minutes, 300)) if minutes else None

    block_codes = [
        code
        for code, aliases in BLOCK_ALIASES.items()
        if any(alias in text for alias in aliases)
    ]
    type_codes = [
        code
        for code, aliases in TYPE_ALIASES.items()
        if any(alias in text for alias in aliases)
    ]
    question_types = [
        question_type
        for question_type, aliases in QUESTION_TYPE_ALIASES.items()
        if any(alias in text for alias in aliases)
    ]
    knowledge_points = [item for item in knowledge.all_knowledge_points() if item in text]

    years = sorted({int(value) for value in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)})
    if "今年" in text and year_now not in years:
        years.append(year_now)
    if "去年" in text and year_now - 1 not in years:
        years.append(year_now - 1)
    year_from = None
    relative_match = re.search(r"近\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*年", text)
    if relative_match:
        relative_years = _number(relative_match.group(1))
        if relative_years:
            year_from = year_now - relative_years + 1

    difficulty_match = re.search(r"难度(?:系数)?\s*([0-9]+(?:\.[0-9]+)?)", text)
    difficulty_target = _difficulty_coefficient(difficulty_match.group(1)) if difficulty_match else None
    difficulty_label = ""
    if difficulty_target is None:
        difficulty_terms = (
            (("很难", "困难", "压轴", "拔高"), 0.22, "困难"),
            (("偏难", "较难", "难度较大"), 0.4, "偏难"),
            (("中等", "适中"), 0.6, "中等"),
            (("简单", "容易", "基础"), 0.82, "基础"),
        )
        for aliases, target, label in difficulty_terms:
            if any(alias in text for alias in aliases):
                difficulty_target, difficulty_label = target, label
                break
    else:
        difficulty_label = difficulty_match.group(1)

    source_terms = [item for item in SOURCE_TERMS if item in text]
    require_answer = any(item in text for item in ("带答案", "有答案", "答案完整"))
    require_analysis = any(item in text for item in ("带解析", "有解析", "解析完整"))

    return {
        "original_query": text,
        "count": count,
        "count_explicit": count_explicit,
        "minutes": minutes,
        "minutes_explicit": minutes_explicit,
        "block_codes": list(dict.fromkeys(block_codes)),
        "blocks": [config.BLOCKS[code] for code in dict.fromkeys(block_codes)],
        "type_codes": list(dict.fromkeys(type_codes)),
        "types": [config.TYPES[code] for code in dict.fromkeys(type_codes)],
        "question_types": list(dict.fromkeys(question_types)),
        "knowledge_points": knowledge_points,
        "years": sorted(set(years)),
        "year_from": year_from,
        "difficulty_target": difficulty_target,
        "difficulty_label": difficulty_label,
        "source_terms": source_terms,
        "require_answer": require_answer,
        "require_analysis": require_analysis,
    }


def estimate_minutes(item: dict[str, Any]) -> int:
    base = {
        "选择题": 4,
        "填空题": 5,
        "实验题": 10,
        "计算题": 14,
        "其他": 7,
    }.get(str(item.get("题型") or "其他"), 7)
    coefficient = _difficulty_coefficient(item.get("难度系数"))
    if coefficient is None:
        return base
    multiplier = 1.35 if coefficient <= 0.35 else 1.15 if coefficient <= 0.55 else 0.9 if coefficient >= 0.8 else 1
    return max(2, round(base * multiplier))


def _matches_constraints(item: dict[str, Any], parsed: dict[str, Any]) -> bool:
    if parsed["blocks"] and item.get("板块") not in parsed["blocks"]:
        return False
    item_types = [str(value) for value in item.get("类型", []) or []]
    if parsed["types"] and not all(value in item_types for value in parsed["types"]):
        return False
    if parsed["question_types"] and item.get("题型") not in parsed["question_types"]:
        return False
    item_knowledge = [str(value) for value in item.get("知识点", []) or []]
    if parsed["knowledge_points"] and not all(value in item_knowledge for value in parsed["knowledge_points"]):
        return False
    item_year = str(item.get("年份") or "")
    if parsed["years"] and item_year not in {str(value) for value in parsed["years"]}:
        return False
    if parsed["year_from"]:
        try:
            if int(item_year) < int(parsed["year_from"]):
                return False
        except (TypeError, ValueError):
            return False
    source = str(item.get("来源") or "")
    if parsed["source_terms"] and not any(term in source for term in parsed["source_terms"]):
        return False
    if parsed["require_answer"] and not str(item.get("答案") or "").strip():
        return False
    if parsed["require_analysis"] and not str(item.get("解析") or "").strip():
        return False
    target = parsed["difficulty_target"]
    if target is not None:
        coefficient = _difficulty_coefficient(item.get("难度系数"))
        if coefficient is None or abs(coefficient - target) > 0.24:
            return False
    return True


def _candidate_score(item: dict[str, Any], parsed: dict[str, Any]) -> float:
    score = 0.0
    score += 4 * sum(point in (item.get("知识点") or []) for point in parsed["knowledge_points"])
    score += 3 * sum(item.get("板块") == block for block in parsed["blocks"])
    score += 2 * sum(value in (item.get("类型") or []) for value in parsed["types"])
    score += 1.5 * sum(item.get("题型") == value for value in parsed["question_types"])
    coefficient = _difficulty_coefficient(item.get("难度系数"))
    if coefficient is not None and parsed["difficulty_target"] is not None:
        score += max(0, 2 - abs(coefficient - parsed["difficulty_target"]) * 5)
    if str(item.get("答案") or "").strip():
        score += 0.35
    if str(item.get("解析") or "").strip():
        score += 0.35
    try:
        score += max(0, int(item.get("年份") or 0) - datetime.now().year + 4) * 0.05
    except (TypeError, ValueError):
        pass
    return round(score, 3)


def _reason(item: dict[str, Any], parsed: dict[str, Any]) -> str:
    reasons: list[str] = []
    if item.get("板块"):
        reasons.append(str(item["板块"]))
    matched_types = [value for value in parsed["types"] if value in (item.get("类型") or [])]
    if matched_types:
        reasons.append("、".join(matched_types))
    matched_knowledge = [value for value in parsed["knowledge_points"] if value in (item.get("知识点") or [])]
    if matched_knowledge:
        reasons.append("考查" + "、".join(matched_knowledge[:3]))
    if item.get("题型"):
        reasons.append(str(item["题型"]))
    if item.get("难度系数") not in (None, ""):
        reasons.append(f"难度系数 {item['难度系数']}")
    if item.get("年份"):
        reasons.append(str(item["年份"]) + " 年")
    if not reasons:
        reasons.append("符合当前本地筛选条件")
    return "；".join(reasons)


def _public_candidate(item: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "block": str(item.get("板块") or ""),
        "main_type": str(item.get("主类型") or ""),
        "types": [str(value) for value in item.get("类型", []) or []],
        "knowledge_points": [str(value) for value in item.get("知识点", []) or []],
        "question_type": str(item.get("题型") or ""),
        "difficulty": str(item.get("难度系数") or ""),
        "year": str(item.get("年份") or ""),
        "source": str(item.get("来源") or ""),
        "preview": storage.question_preview(str(item.get("题目") or ""), 160),
        "has_answer": bool(str(item.get("答案") or "").strip()),
        "has_analysis": bool(str(item.get("解析") or "").strip()),
        "estimated_minutes": estimate_minutes(item),
        "reason": _reason(item, parsed),
        "score": _candidate_score(item, parsed),
    }


def recommend_questions(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_query(str(payload.get("query") or ""))
    candidates = [
        _public_candidate(item, parsed)
        for item in storage.read_all_questions()
        if _matches_constraints(item, parsed)
    ]
    candidates.sort(key=lambda item: (-float(item["score"]), item["id"]))

    requested_count = int(parsed["count"])
    time_limit = parsed["minutes"]
    selected: list[dict[str, Any]] = []
    total_minutes = 0
    for item in candidates:
        if len(selected) >= requested_count:
            break
        item_minutes = int(item["estimated_minutes"])
        if time_limit and selected and total_minutes + item_minutes > int(time_limit * 1.1):
            continue
        selected.append(item)
        total_minutes += item_minutes

    warnings: list[str] = []
    if len(selected) < requested_count:
        warnings.append(f"严格条件下只找到 {len(selected)} 道题，没有自动放宽老师的要求。")
    if time_limit and total_minutes < max(5, int(time_limit * 0.65)):
        warnings.append(f"当前推荐预计约 {total_minutes} 分钟，少于目标 {time_limit} 分钟。")

    used_ai = False
    sent_fields: list[str] = []
    if payload.get("use_ai") is True and selected:
        settings = models.load_model_settings()
        if settings["cloud"] and payload.get("consent") is not True:
            raise AppError(
                "调用云模型前需要确认发送查询要求和候选题元数据。",
                code="consent_required",
            )
        try:
            ranked = models.rank_question_candidates(
                query=parsed["original_query"],
                candidates=selected,
                count=requested_count,
            )
            by_id = {item["id"]: item for item in selected}
            enhanced: list[dict[str, Any]] = []
            for recommendation in ranked["recommendations"]:
                item = by_id.get(str(recommendation["id"]))
                if not item:
                    continue
                enhanced.append({**item, "reason": str(recommendation["reason"])})
            enhanced.extend(item for item in selected if item["id"] not in {value["id"] for value in enhanced})
            selected = enhanced[:requested_count]
            used_ai = True
            sent_fields = [
                "找题要求",
                "候选题号",
                "板块",
                "类型",
                "知识点",
                "题型",
                "难度系数",
                "年份",
                "来源",
                "题目预览",
            ]
        except AppError as exc:
            if exc.code == "consent_required":
                raise
            warnings.append(f"AI 推荐暂不可用，已保留本地排序：{exc.message}")

    return {
        "query": parsed["original_query"],
        "parsed": parsed,
        "items": selected,
        "candidate_count": len(candidates),
        "recommended_count": len(selected),
        "estimated_minutes": sum(int(item["estimated_minutes"]) for item in selected),
        "warnings": warnings,
        "used_ai": used_ai,
        "sent_fields": sent_fields,
        "requires_teacher_selection": True,
    }
