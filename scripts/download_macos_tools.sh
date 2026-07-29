#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PANDOC_VERSION="3.6.3"
OFFICECLI_VERSION="1.0.142"
MACHINE="$(uname -m)"

case "$MACHINE" in
  arm64|aarch64)
    PANDOC_ARCH="arm64"
    PANDOC_SHA256="1d76cd76b703ff758f90f6929bd5f634bc50fc76ad375a9d19a5d365cd8233fc"
    OFFICECLI_ASSET="officecli-mac-arm64"
    OFFICECLI_SHA256="684ce214bb8d750003d521eea044a9199bcbdb870817dba5d3191b35715ea38c"
    ;;
  x86_64|amd64)
    PANDOC_ARCH="x86_64"
    PANDOC_SHA256="cf6b8543d04f4162ebe4e3b1ff006018ea395eb3ed8fc97b880d760e3be0a1a9"
    OFFICECLI_ASSET="officecli-mac-x64"
    OFFICECLI_SHA256="d2d27d8203ec8fc178a6a55eb4ce0ca63696e4ceddb7f85eab359da77f343a91"
    ;;
  *)
    echo "Unsupported macOS architecture: $MACHINE" >&2
    exit 1
    ;;
esac

PANDOC_DIR="$ROOT/tools/pandoc"
PANDOC="$PANDOC_DIR/pandoc"
if [[ ! -x "$PANDOC" ]] || ! "$PANDOC" --version | head -n 1 | grep -Fq "pandoc $PANDOC_VERSION"; then
  TEMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TEMP_DIR"' EXIT
  ARCHIVE="$TEMP_DIR/pandoc.zip"
  ASSET="pandoc-$PANDOC_VERSION-$PANDOC_ARCH-macOS.zip"
  curl --fail --location --retry 3 \
    "https://github.com/jgm/pandoc/releases/download/$PANDOC_VERSION/$ASSET" \
    --output "$ARCHIVE"
  ACTUAL_SHA256="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
  if [[ "$ACTUAL_SHA256" != "$PANDOC_SHA256" ]]; then
    echo "Pandoc checksum verification failed." >&2
    exit 1
  fi
  ditto -x -k "$ARCHIVE" "$TEMP_DIR/pandoc"
  EXTRACTED="$(find "$TEMP_DIR/pandoc" -type f -path '*/bin/pandoc' -print -quit)"
  if [[ -z "$EXTRACTED" ]]; then
    echo "Pandoc archive did not contain the executable." >&2
    exit 1
  fi
  mkdir -p "$PANDOC_DIR"
  ditto "$EXTRACTED" "$PANDOC"
  chmod 755 "$PANDOC"
fi
echo "Pandoc $PANDOC_VERSION is ready: $PANDOC"

OFFICECLI_DIR="$ROOT/tools/officecli"
OFFICECLI="$OFFICECLI_DIR/$OFFICECLI_ASSET"
if [[ ! -x "$OFFICECLI" ]] || \
   [[ "$(shasum -a 256 "$OFFICECLI" | awk '{print $1}')" != "$OFFICECLI_SHA256" ]]; then
  mkdir -p "$OFFICECLI_DIR"
  curl --fail --location --retry 3 \
    "https://github.com/iOfficeAI/OfficeCLI/releases/download/v$OFFICECLI_VERSION/$OFFICECLI_ASSET" \
    --output "$OFFICECLI.download"
  ACTUAL_SHA256="$(shasum -a 256 "$OFFICECLI.download" | awk '{print $1}')"
  if [[ "$ACTUAL_SHA256" != "$OFFICECLI_SHA256" ]]; then
    echo "OfficeCLI checksum verification failed." >&2
    exit 1
  fi
  mv "$OFFICECLI.download" "$OFFICECLI"
  chmod 755 "$OFFICECLI"
fi
echo "OfficeCLI $OFFICECLI_VERSION is ready: $OFFICECLI"
