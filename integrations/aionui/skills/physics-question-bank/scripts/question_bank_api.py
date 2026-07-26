#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def base_url() -> str:
    value = os.getenv("QUESTION_BANK_API", "http://127.0.0.1:8000").rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("QUESTION_BANK_API 必须是本机 HTTP 地址。")
    return value


def request(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(base_url() + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = {"detail": body or str(exc)}
        raise RuntimeError(json.dumps(detail, ensure_ascii=False)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("无法连接本地题库，请先启动高中物理题库助手。") from exc


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="AionUI 本地物理题库 API 客户端")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("status")

    recommend = commands.add_parser("recommend")
    recommend.add_argument("query")
    recommend.add_argument("--ai", action="store_true")
    recommend.add_argument("--consent", action="store_true")

    detail = commands.add_parser("get")
    detail.add_argument("question_id")

    export = commands.add_parser("export")
    export.add_argument("ids", nargs="+")
    export.add_argument("--title", default="智能组卷")
    export.add_argument(
        "--mode",
        choices=("questions", "answers", "analysis", "answer_sheet", "analysis_sheet"),
        default="questions",
    )
    export.add_argument(
        "--template",
        choices=("a4_single", "a4_double", "formal_exam"),
        default="a4_single",
    )
    export.add_argument("--duration", default="")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "status":
            result = request("GET", "/api/health")
        elif args.command == "recommend":
            result = request(
                "POST",
                "/api/assistant/recommend",
                {"query": args.query, "use_ai": args.ai, "consent": args.consent},
            )
        elif args.command == "get":
            question_id = urllib.parse.quote(args.question_id, safe="")
            result = request("GET", f"/api/questions/{question_id}")
        else:
            result = request(
                "POST",
                "/api/export",
                {
                    "ids": args.ids,
                    "title": args.title,
                    "mode": args.mode,
                    "template": args.template,
                    "duration": args.duration,
                },
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
