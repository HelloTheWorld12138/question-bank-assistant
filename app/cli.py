from __future__ import annotations

import argparse
import json
from typing import Any

from app import config, storage
from app.errors import AppError
from app.services import assistant, questions


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="高中物理题库本地 CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="查看题库状态")

    parse = commands.add_parser("parse", help="把自然语言要求解析为筛选条件")
    parse.add_argument("query")

    recommend = commands.add_parser("recommend", help="按自然语言要求推荐题目")
    recommend.add_argument("query")
    recommend.add_argument("--ai", action="store_true", help="使用已配置的可选模型增强排序")
    recommend.add_argument("--consent", action="store_true", help="确认云模型可接收最少候选元数据")

    export = commands.add_parser("export", help="按题号导出试卷")
    export.add_argument("ids", nargs="+")
    export.add_argument("--title", default="智能组卷")
    export.add_argument(
        "--mode",
        choices=("questions", "answers", "analysis", "answer_sheet", "analysis_sheet"),
        default="questions",
    )
    export.add_argument("--template", choices=tuple(config.EXAM_TEMPLATES), default="a4_single")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            _print(
                {
                    "status": "ok",
                    "version": config.APP_VERSION,
                    "questions": len(storage.read_all_questions()),
                    "data_dir": str(config.VAULT),
                }
            )
        elif args.command == "parse":
            _print(assistant.parse_query(args.query))
        elif args.command == "recommend":
            _print(
                assistant.recommend_questions(
                    {"query": args.query, "use_ai": args.ai, "consent": args.consent}
                )
            )
        elif args.command == "export":
            _print(
                questions.export_exam(
                    {
                        "ids": args.ids,
                        "title": args.title,
                        "mode": args.mode,
                        "template": args.template,
                    }
                )
            )
    except AppError as exc:
        _print({"status": "error", "code": exc.code, "message": exc.message})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
