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
        fixture_root = (
            runtime_dir
            / "mathtype-plus"
            / "lib"
            / "mathtype-0.0.7.5"
            / "spec"
            / "fixtures"
            / "input"
        )
        equation_editor_fixtures = sorted((fixture_root / "mathtype3").glob("*.bin"))
        fixtures = {
            f"AUDIT_EQUATION_EDITOR_3_{fixture.stem.upper()}": fixture
            for fixture in equation_editor_fixtures
        }
        fixtures["AUDIT_MATHTYPE_5"] = fixture_root / "mathtype5" / "equation1.bin"
        if (
            not equation_editor_fixtures
            or any(not fixture.is_file() for fixture in fixtures.values())
        ):
            print("Formula conversion fixture is missing.", file=sys.stderr)
            return 1
        environment = dict(os.environ)
        environment["RUBYLIB"] = os.pathsep.join(
            item for item in (rubylib, environment.get("RUBYLIB", "")) if item
        )
        completed = subprocess.run(
            [str(ruby), str(mathtype.CONVERTER_SCRIPT), "--stdin-json"],
            cwd=str(runtime_root),
            env=environment,
            input=json.dumps(
                {marker: str(fixture) for marker, fixture in fixtures.items()},
                ensure_ascii=False,
            ),
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
        results = {str(item.get("id") or ""): item for item in rows}
        if completed.returncode != 0:
            print(
                f"Formula fixture conversion failed: {completed.stderr.strip()}",
                file=sys.stderr,
            )
            return 1
        equations: dict[str, str] = {}
        for marker in fixtures:
            result = results.get(marker)
            if not result or not result.get("ok"):
                error = result.get("error") if result else "no result"
                print(f"{marker} conversion failed: {error}", file=sys.stderr)
                return 1
            try:
                mathml = base64.b64decode(result["mathml"]).decode("utf-8")
            except (KeyError, ValueError, UnicodeDecodeError) as exc:
                print(f"{marker} output is invalid: {exc}", file=sys.stderr)
                return 1
            if "<math" not in mathml:
                print(f"{marker} did not produce MathML.", file=sys.stderr)
                return 1
            if any(0xE000 <= ord(character) <= 0xF8FF for character in mathml):
                print(f"{marker} retained an unsupported private-use character.", file=sys.stderr)
                return 1
            equations[marker] = mathml

        pandoc_name = "pandoc.exe" if os.name == "nt" else "pandoc"
        pandoc = runtime_root / "tools" / "pandoc" / pandoc_name
        if not pandoc.is_file():
            print("Bundled Pandoc is missing from the formula audit.", file=sys.stderr)
            return 1
        latex, latex_failures = mathtype.mathml_to_latex(equations, str(pandoc))
        if latex_failures or set(latex) != set(fixtures):
            print(
                f"Formula-to-LaTeX audit failed: {latex_failures}",
                file=sys.stderr,
            )
            return 1
        if "\\frac" not in latex["AUDIT_EQUATION_EDITOR_3_FRAC"]:
            print("Equation Editor 3.0 audit lost the fraction structure.", file=sys.stderr)
            return 1

    print("Formula runtime audit passed for Equation Editor 3.0 and MathType.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
