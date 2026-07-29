from __future__ import annotations

import argparse
import sys
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
    print("MathType runtime audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
