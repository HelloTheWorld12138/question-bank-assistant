#!/bin/zsh

set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR" || exit 1

APP_URL="http://127.0.0.1:8000"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/server.log"
PID_FILE="$LOG_DIR/question-bank.pid"
VENV_DIR="$ROOT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

mkdir -p "$LOG_DIR"

show_error() {
  /usr/bin/osascript -e "display dialog \"$1\" with title \"高中物理题库助手\" buttons {\"知道了\"} default button 1 with icon stop" >/dev/null 2>&1
}

app_is_ready() {
  /usr/bin/curl --silent --fail --max-time 2 "$APP_URL/api/health" 2>/dev/null |
    /usr/bin/grep --quiet '"app":"高中物理题库助手"'
}

if app_is_ready; then
  /usr/bin/open "$APP_URL"
  /usr/bin/osascript -e 'display notification "题库已经在运行，已为你打开。" with title "高中物理题库助手"' >/dev/null 2>&1
  exit 0
fi

if [[ ! -x "$VENV_PYTHON" ]]; then
  SYSTEM_PYTHON="$(command -v python3 || true)"
  if [[ -z "$SYSTEM_PYTHON" ]]; then
    show_error "没有找到 Python 3，暂时无法启动题库。"
    exit 1
  fi
  echo "首次运行：正在创建本地环境……"
  "$SYSTEM_PYTHON" -m venv "$VENV_DIR" || {
    show_error "创建本地运行环境失败，请查看终端中的错误。"
    exit 1
  }
fi

if ! "$VENV_PYTHON" -c "import fastapi, uvicorn, pymupdf, PIL" >/dev/null 2>&1; then
  echo "首次运行：正在安装必要组件，请保持网络连接……"
  "$VENV_PYTHON" -m pip install -r "$ROOT_DIR/requirements.txt" || {
    show_error "必要组件安装失败，请检查网络后重新双击启动文件。"
    exit 1
  }
fi

echo "正在启动高中物理题库助手……"
nohup "$VENV_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  >>"$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" >"$PID_FILE"

for attempt in {1..40}; do
  if app_is_ready; then
    /usr/bin/open "$APP_URL"
    /usr/bin/osascript -e 'display notification "题库已启动，可以开始使用。" with title "高中物理题库助手"' >/dev/null 2>&1
    exit 0
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    break
  fi
  sleep 0.25
done

show_error "题库没有成功启动。即将打开运行日志，方便检查原因。"
/usr/bin/open -a TextEdit "$LOG_FILE"
exit 1
