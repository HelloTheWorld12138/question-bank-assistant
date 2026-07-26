from pathlib import Path

import pytest

from app import config, storage


@pytest.fixture()
def isolated_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "vault"
    exports = tmp_path / "exports"
    monkeypatch.setattr(config, "VAULT", vault)
    monkeypatch.setattr(config, "QUESTIONS_DIR", vault / "题目")
    monkeypatch.setattr(config, "ASSETS_DIR", vault / "assets")
    monkeypatch.setattr(config, "DRAFT_ASSETS_DIR", vault / "assets" / "_drafts")
    monkeypatch.setattr(config, "INDEX_FILE", vault / "index.json")
    monkeypatch.setattr(config, "INDEX_LOCK_FILE", vault / ".index.lock")
    monkeypatch.setattr(config, "TRASH_DIR", vault / ".trash")
    monkeypatch.setattr(config, "BACKUPS_DIR", vault / "backups")
    monkeypatch.setattr(config, "USER_TEMPLATES_DIR", vault / "templates")
    monkeypatch.setattr(config, "SETTINGS_FILE", vault / "settings.json")
    monkeypatch.setattr(config, "AI_DRAFTS_DIR", vault / "ai_drafts")
    monkeypatch.setattr(config, "IMPORT_TASKS_DIR", vault / "import_tasks")
    monkeypatch.setattr(config, "EXPORT_DIR", exports)
    storage.ensure_dirs()
    return vault
