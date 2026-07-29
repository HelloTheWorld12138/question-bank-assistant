#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv-build"
DIST="$ROOT/dist"
BUILD="$ROOT/build/macos"
APP_NAME="题搭子"
DMG_STAGE="$BUILD/dmg-root"

cd "$ROOT"
"$ROOT/scripts/download_macos_tools.sh"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r requirements-build.txt
APP_VERSION="$("$VENV/bin/python" -c 'from app.config import APP_VERSION; print(APP_VERSION)')"

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
  --add-data "$ROOT/tools:tools" \
  --add-data "$ROOT/third_party/mathtype_to_mathml:third_party/mathtype_to_mathml" \
  --add-data "$ROOT/third_party/OfficeCLI:licenses/OfficeCLI" \
  --collect-all webview \
  --hidden-import "uvicorn.logging" \
  --hidden-import "uvicorn.loops.auto" \
  --hidden-import "uvicorn.protocols.http.auto" \
  desktop.py

APP_BUNDLE="$DIST/$APP_NAME.app"
PLIST="$APP_BUNDLE/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_VERSION" "$PLIST"
"$ROOT/scripts/test_macos_bundle.sh" "$APP_BUNDLE" "$APP_NAME" "$VENV/bin/python"
codesign --force --deep --sign - "$APP_BUNDLE"
codesign --verify --deep --strict "$APP_BUNDLE"

mkdir -p "$DMG_STAGE"
ditto "$APP_BUNDLE" "$DMG_STAGE/$APP_NAME.app"
ln -s /Applications "$DMG_STAGE/Applications"

hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_STAGE" \
  -ov -format UDZO "$DIST/$APP_NAME.dmg"
echo "Created: $DIST/$APP_NAME.dmg"
