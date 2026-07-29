from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import mathtype  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--ruby", type=Path, required=True)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    ruby = args.ruby.resolve()
    mathtype.VENDOR_DIR = runtime_root / "third_party" / "mathtype_to_mathml"
    mathtype.CONVERTER_SCRIPT = mathtype.VENDOR_DIR / "convert.rb"
    mathtype.find_ruby = lambda: str(ruby) if ruby.is_file() else None
    mathtype._converter_runtime_status.cache_clear()
    status = mathtype.mathtype_status()
    if not status["available"]:
        print(status["message"], file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="question-bank-mathtype-audit-") as temp_dir:
        runtime_dir = Path(temp_dir) / "ruby"
        try:
            rubylib = mathtype._vendor_rubylib(runtime_dir)
        except Exception as exc:
            print(f"MathType fixture extraction failed: {exc}", file=sys.stderr)
            return 1
        fixture = (
            runtime_dir
            / "mathtype-plus"
            / "lib"
            / "mathtype-0.0.7.5"
            / "spec"
            / "fixtures"
            / "input"
            / "mathtype5"
            / "equation1.bin"
        )
        if not fixture.is_file():
            print("MathType conversion fixture is missing.", file=sys.stderr)
            return 1
        environment = dict(os.environ)
        environment["RUBYLIB"] = os.pathsep.join(
            item for item in (rubylib, environment.get("RUBYLIB", "")) if item
        )
        completed = subprocess.run(
            [str(ruby), str(mathtype.CONVERTER_SCRIPT), "--stdin-json"],
            cwd=str(runtime_root),
            env=environment,
            input=json.dumps({"AUDIT_FORMULA": str(fixture)}, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        rows = []
        for line in completed.stdout.splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        result = next((item for item in rows if item.get("id") == "AUDIT_FORMULA"), None)
        if completed.returncode != 0 or not result or not result.get("ok"):
            error = result.get("error") if result else completed.stderr.strip()
            print(f"MathType fixture conversion failed: {error}", file=sys.stderr)
            return 1
        try:
            mathml = base64.b64decode(result["mathml"]).decode("utf-8")
        except (KeyError, ValueError, UnicodeDecodeError) as exc:
            print(f"MathType fixture output is invalid: {exc}", file=sys.stderr)
            return 1
        if "<math" not in mathml:
            print("MathType fixture did not produce MathML.", file=sys.stderr)
            return 1

    print("MathType runtime audit passed with a real formula conversion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
