#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_BUNDLE="${1:?Pass the built .app path}"
APP_NAME="${2:-题搭子}"
PYTHON="${3:-python3}"
MACHINE="$(uname -m)"
if [[ "$MACHINE" == "arm64" || "$MACHINE" == "aarch64" ]]; then
  OFFICECLI_NAME="officecli-mac-arm64"
else
  OFFICECLI_NAME="officecli-mac-x64"
fi

RUNTIME="$APP_BUNDLE/Contents/Resources"
REQUIRED=(
  "static/index.html"
  "data/knowledge.yaml"
  "templates/a4_single.docx"
  "tools/pandoc/pandoc"
  "tools/officecli/$OFFICECLI_NAME"
  "third_party/mathtype_to_mathml/convert.rb"
  "third_party/mathtype_to_mathml/bindata-2.4.15.gem"
  "third_party/mathtype_to_mathml/ruby-ole-1.2.13.1.gem"
  "third_party/mathtype_to_mathml/mathtype_to_mathml_plus-0.0.16.gem"
)
for relative in "${REQUIRED[@]}"; do
  if [[ ! -f "$RUNTIME/$relative" ]]; then
    echo "macOS release is missing: $relative" >&2
    exit 1
  fi
done
if [[ ! -x "$APP_BUNDLE/Contents/MacOS/$APP_NAME" ]]; then
  echo "macOS release is missing the application executable." >&2
  exit 1
fi

PANDOC="$RUNTIME/tools/pandoc/pandoc"
OFFICECLI="$RUNTIME/tools/officecli/$OFFICECLI_NAME"
"$PANDOC" --version >/dev/null
OFFICECLI_SKIP_UPDATE=1 OFFICECLI_RESIDENT_FLUSH=each "$OFFICECLI" --version >/dev/null
"$PYTHON" "$PROJECT_ROOT/scripts/audit_mathtype_runtime.py" \
  --runtime-root "$RUNTIME" \
  --ruby /usr/bin/ruby

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
printf 'Word bundle smoke test\n' >"$TEMP_DIR/input.md"
"$PANDOC" "$TEMP_DIR/input.md" -o "$TEMP_DIR/output.docx"
"$PANDOC" "$TEMP_DIR/output.docx" -t plain -o "$TEMP_DIR/output.txt"
grep -Fq "Word bundle smoke test" "$TEMP_DIR/output.txt"

echo "macOS bundle audit passed."
