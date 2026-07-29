"""Desktop entry point used by the macOS application bundle."""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import uvicorn
import webview


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _prepare_user_directories() -> None:
    """Never write teacher data inside the read-only application bundle."""
    documents = Path.home() / "Documents" / "高中物理题库"
    os.environ.setdefault("QUESTION_BANK_DATA_DIR", str(documents))
    os.environ.setdefault("QUESTION_BANK_EXPORT_DIR", str(documents / "exports"))
    os.environ.setdefault("QUESTION_BANK_LOG_DIR", str(documents / "logs"))


def main() -> None:
    _prepare_user_directories()
    # Import after data-directory setup; the direct import also ensures the
    # backend package is included when PyInstaller analyzes this entry point.
    from app.main import app

    port = _free_local_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()

    deadline = time.monotonic() + 10
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("题库服务未能启动，请检查应用日志。")

    # Desktop webviews disable file downloads by default. Enable the native
    # save dialog so generated Word files can be downloaded on macOS and Windows.
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.create_window(
        "题搭子",
        f"http://127.0.0.1:{port}",
        width=1440,
        height=920,
        min_size=(1080, 720),
    )
    webview.start()
    server.should_exit = True
    worker.join(timeout=3)


if __name__ == "__main__":
    main()
