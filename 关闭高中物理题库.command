#!/bin/zsh

set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT_DIR/logs/question-bank.pid"

if [[ ! -f "$PID_FILE" ]]; then
  /usr/bin/osascript -e 'display notification "没有发现由启动文件打开的题库服务。" with title "高中物理题库助手"' >/dev/null 2>&1
  exit 0
fi

SERVER_PID="$(/bin/cat "$PID_FILE" 2>/dev/null || true)"
if [[ "$SERVER_PID" == <-> ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
  kill "$SERVER_PID" 2>/dev/null || true
  for attempt in {1..20}; do
    kill -0 "$SERVER_PID" 2>/dev/null || break
    sleep 0.1
  done
fi

: >"$PID_FILE"
/usr/bin/osascript -e 'display notification "题库服务已关闭。" with title "高中物理题库助手"' >/dev/null 2>&1
