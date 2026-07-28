from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

from app import config
from app.errors import AppError
from app.processes import hidden_process_kwargs


_OFFICECLI_LOCK = threading.Lock()


def find_officecli() -> str | None:
    configured = os.getenv("OFFICECLI_PATH", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path.resolve())
    if config.LOCAL_OFFICECLI.is_file():
        return str(config.LOCAL_OFFICECLI)
    return shutil.which("officecli")


def command_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["OFFICECLI_SKIP_UPDATE"] = "1"
    environment["OFFICECLI_RESIDENT_FLUSH"] = "each"
    return environment


def run_officecli(
    arguments: list[str],
    *,
    timeout: int = 60,
    require_json: bool = True,
) -> dict[str, Any] | str:
    executable = find_officecli()
    if not executable:
        raise AppError("未检测到 OfficeCLI，将使用 Pandoc 基础导出。")
    command = [executable, *arguments]
    if require_json and "--json" not in command:
        command.append("--json")
    with _OFFICECLI_LOCK:
        try:
            completed = subprocess.run(
                command,
                cwd=str(config.ROOT),
                env=command_environment(),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                **hidden_process_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            raise AppError("OfficeCLI 处理超时，已保留 Word 文件。", code="officecli_timeout") from exc
        except OSError as exc:
            raise AppError("OfficeCLI 无法启动，已保留 Word 文件。", code="officecli_start_failed") from exc

    output = (completed.stdout or "").strip()
    error = (completed.stderr or "").strip()
    parsed: dict[str, Any] | None = None
    if require_json and output:
        try:
            raw = json.loads(output)
            parsed = raw if isinstance(raw, dict) else {"success": True, "data": raw}
        except json.JSONDecodeError:
            parsed = None
    if completed.returncode != 0 or (parsed and parsed.get("success") is False):
        message = ""
        if parsed:
            detail = parsed.get("error") or parsed.get("message") or parsed.get("data")
            message = str(detail or "")
        raise AppError(message or error or output or "OfficeCLI 处理失败", code="officecli_failed")
    if require_json:
        if parsed is None:
            raise AppError("OfficeCLI 返回了无法识别的结果", code="officecli_invalid_output")
        return parsed
    return output


def officecli_status() -> dict[str, Any]:
    executable = find_officecli()
    if not executable:
        return {
            "available": False,
            "version": "",
            "expected_version": config.OFFICECLI_VERSION,
            "path": "",
        }
    try:
        version = str(run_officecli(["--version"], require_json=False, timeout=10)).strip()
    except AppError:
        version = ""
    return {
        "available": bool(version),
        "version": version,
        "expected_version": config.OFFICECLI_VERSION,
        "version_matches": version == config.OFFICECLI_VERSION,
        "path": executable,
    }


def validate_document(path: Path) -> dict[str, Any]:
    result = run_officecli(["validate", str(path)])
    return {
        "ok": bool(result.get("success")),
        "message": str(result.get("message") or result.get("data") or ""),
    }


def inspect_issues(path: Path) -> dict[str, Any]:
    result = run_officecli(["view", str(path), "issues"])
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    all_issues = data.get("issues") or []
    ignored_messages = {"Body paragraph missing first-line indent"}
    issues = [
        issue
        for issue in all_issues
        if not isinstance(issue, dict) or str(issue.get("message") or "") not in ignored_messages
    ]
    return {
        "count": len(issues),
        "issues": issues,
        "ignored_count": max(len(all_issues) - len(issues), 0),
    }


def render_html(path: Path, output: Path) -> Path:
    run_officecli(["view", str(path), "html", "-o", str(output)], timeout=90)
    if not output.exists():
        raise AppError("OfficeCLI 未生成预览文件", code="officecli_preview_missing")
    return output


def read_document_structure(path: Path, depth: int = 3) -> dict[str, Any]:
    result = run_officecli(["get", str(path), "/", "--depth", str(depth)])
    data = result.get("data")
    return data if isinstance(data, dict) else {"data": data}


def merge_template(template: Path, output: Path, data_file: Path) -> Path:
    run_officecli(
        ["merge", str(template), str(output), "--data", str(data_file), "--force"],
        timeout=90,
    )
    if not output.exists():
        raise AppError("OfficeCLI 未生成模板合并文件", code="officecli_merge_missing")
    return output
