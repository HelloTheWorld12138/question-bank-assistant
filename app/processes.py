"""Cross-platform helpers for launching bundled command-line tools."""

from __future__ import annotations

import os
import subprocess


def hidden_process_kwargs() -> dict[str, int]:
    """Prevent command-line helpers from flashing a console window on Windows."""
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
