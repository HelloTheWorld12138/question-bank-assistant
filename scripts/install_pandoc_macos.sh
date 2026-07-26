#!/bin/zsh

set -u

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if command -v pandoc >/dev/null 2>&1; then
  pandoc --version | /usr/bin/head -n 1
  exit 0
fi

if [[ -x /opt/homebrew/bin/brew ]]; then
  BREW=/opt/homebrew/bin/brew
elif [[ -x /usr/local/bin/brew ]]; then
  BREW=/usr/local/bin/brew
else
  echo "没有检测到 Homebrew，无法自动安装 Pandoc。" >&2
  exit 1
fi

echo "正在通过 Homebrew 安装 Pandoc……"
HOMEBREW_NO_AUTO_UPDATE=1 "$BREW" install pandoc
pandoc --version | /usr/bin/head -n 1
