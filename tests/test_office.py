import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import config
from app.errors import AppError
from app.services import office


def test_officecli_status_disables_background_updates(isolated_data, monkeypatch, tmp_path):
    binary = tmp_path / "officecli"
    binary.write_text("binary", encoding="utf-8")
    monkeypatch.setenv("OFFICECLI_PATH", str(binary))

    def fake_run(command, **kwargs):
        assert kwargs["env"]["OFFICECLI_SKIP_UPDATE"] == "1"
        assert kwargs["env"]["OFFICECLI_RESIDENT_FLUSH"] == "each"
        return SimpleNamespace(returncode=0, stdout=config.OFFICECLI_VERSION, stderr="")

    monkeypatch.setattr(office.subprocess, "run", fake_run)
    status = office.officecli_status()
    assert status["available"] is True
    assert status["version_matches"] is True


def test_officecli_json_failure_becomes_app_error(isolated_data, monkeypatch, tmp_path):
    binary = tmp_path / "officecli"
    binary.write_text("binary", encoding="utf-8")
    monkeypatch.setenv("OFFICECLI_PATH", str(binary))
    monkeypatch.setattr(
        office.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=json.dumps({"success": False, "message": "文档损坏"}, ensure_ascii=False),
            stderr="",
        ),
    )

    with pytest.raises(AppError, match="文档损坏"):
        office.validate_document(Path("bad.docx"))


def test_officecli_validation_warnings_are_returned_without_raw_json(
    isolated_data,
    monkeypatch,
    tmp_path,
):
    binary = tmp_path / "officecli"
    binary.write_text("binary", encoding="utf-8")
    monkeypatch.setenv("OFFICECLI_PATH", str(binary))
    warnings = [{"message": "m:sty schema warning", "code": "warning"}]
    monkeypatch.setattr(
        office.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=json.dumps(
                {"success": False, "warnings": warnings},
                ensure_ascii=False,
            ),
            stderr="",
        ),
    )

    result = office.validate_document(Path("formula.docx"))

    assert result == {
        "ok": False,
        "message": "发现 1 项兼容性提示",
        "warning_count": 1,
    }


def test_missing_officecli_has_clear_status(isolated_data, monkeypatch):
    monkeypatch.delenv("OFFICECLI_PATH", raising=False)
    monkeypatch.setattr(config, "LOCAL_OFFICECLI", Path("/missing/officecli"))
    monkeypatch.setattr(office.shutil, "which", lambda command: None)
    assert office.officecli_status()["available"] is False


def test_officecli_document_operations_use_json_contract(isolated_data, monkeypatch, tmp_path):
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append(arguments)
        if arguments[0] == "view" and arguments[2] == "issues":
            return {
                "success": True,
                "data": {
                    "count": 1,
                    "issues": [{"message": "Body paragraph missing first-line indent"}],
                },
            }
        if arguments[0] == "get":
            return {"success": True, "data": {"type": "document"}}
        return {"success": True, "message": "ok"}

    monkeypatch.setattr(office, "run_officecli", fake_run)
    document = tmp_path / "exam.docx"
    document.write_bytes(b"docx")

    assert office.validate_document(document)["ok"] is True
    assert office.inspect_issues(document)["count"] == 0
    assert office.read_document_structure(document)["type"] == "document"
    assert calls[0][:2] == ["validate", str(document)]
