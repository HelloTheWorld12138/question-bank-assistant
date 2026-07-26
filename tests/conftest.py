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
    monkeypatch.setattr(config, "EXPORT_DIR", exports)
    storage.ensure_dirs()
    return vault

