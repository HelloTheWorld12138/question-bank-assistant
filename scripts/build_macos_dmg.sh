#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv-build"
DIST="$ROOT/dist"
BUILD="$ROOT/build/macos"
APP_NAME="题搭子"
DMG_STAGE="$BUILD/dmg-root"

cd "$ROOT"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r requirements-build.txt

rm -rf "$BUILD" "$DIST/$APP_NAME.app" "$DIST/$APP_NAME.dmg"
"$VENV/bin/python" -m PyInstaller --noconfirm --clean --windowed --onedir \
  --name "$APP_NAME" \
  --icon "$ROOT/assets/tidazi.icns" \
  --osx-bundle-identifier "cn.edu.ccnu.physics-question-bank" \
  --distpath "$DIST" \
  --workpath "$BUILD" \
  --specpath "$BUILD" \
  --add-data "$ROOT/static:static" \
  --add-data "$ROOT/data:data" \
  --add-data "$ROOT/templates:templates" \
  --collect-all webview \
  --hidden-import "uvicorn.logging" \
  --hidden-import "uvicorn.loops.auto" \
  --hidden-import "uvicorn.protocols.http.auto" \
  desktop.py

mkdir -p "$DMG_STAGE"
ditto "$DIST/$APP_NAME.app" "$DMG_STAGE/$APP_NAME.app"
ln -s /Applications "$DMG_STAGE/Applications"

hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_STAGE" \
  -ov -format UDZO "$DIST/$APP_NAME.dmg"
echo "Created: $DIST/$APP_NAME.dmg"
