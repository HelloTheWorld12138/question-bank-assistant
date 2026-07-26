from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


SYSTEM_PROMPT = """你是一个本地题库导入助手。请把 Markdown 题目材料拆成结构化 JSON。

要求：
1. 只输出 JSON，不要输出解释。
2. JSON 字段固定为 question、answer、analysis、metadata、confidence、notes。
3. question 保留题干、选项、图片、公式 Markdown。
4. answer 只放答案；如果原文没有明确答案，留空。
5. analysis 只放解析/解题过程；如果原文没有明确解析，留空。
6. metadata 是对象，可包含：板块、主类型、类型、知识点、难度系数、年份、来源、解析来源、备注。
7. 不要编造不存在的答案、解析或元数据。
"""


def opencode_available() -> bool:
    command = os.getenv("QUESTION_AGENT_COMMAND", "").strip()
    if command:
        return True
    return shutil.which("opencode") is not None


def build_prompt(markdown: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nMarkdown 原文：\n\n```markdown\n{markdown}\n```"


def parse_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def normalize_agent_sections(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "question": str(data.get("question") or "").strip(),
        "answer": str(data.get("answer") or "").strip(),
        "analysis": str(data.get("analysis") or "").strip(),
        "metadata": metadata,
        "confidence": data.get("confidence"),
        "notes": data.get("notes") or "",
    }


def run_opencode(markdown: str, cwd: Path, timeout: int = 90) -> tuple[dict[str, Any] | None, str]:
    prompt = build_prompt(markdown)
    command_template = os.getenv("QUESTION_AGENT_COMMAND", "").strip()

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        prompt_file = temp_path / "prompt.md"
        output_file = temp_path / "result.json"
        prompt_file.write_text(prompt, encoding="utf-8")

        if command_template:
            command = command_template.format(
                prompt_file=str(prompt_file),
                output_file=str(output_file),
            )
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                shell=True,
                timeout=timeout,
                check=False,
            )
        else:
            completed = subprocess.run(
                ["opencode", "run", "--print", prompt],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

        output = ""
        if output_file.exists():
            output = output_file.read_text(encoding="utf-8", errors="replace")
        output = output or completed.stdout
        if completed.returncode != 0:
            detail = completed.stderr.strip() or output.strip()
            return None, detail or "opencode 调用失败"

    data = parse_json_object(output)
    if not data:
        return None, "opencode 没有返回可解析的 JSON"
    return normalize_agent_sections(data), ""
