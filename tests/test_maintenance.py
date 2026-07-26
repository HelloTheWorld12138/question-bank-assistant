from app import config, storage
from app.services import maintenance


def write_sample_question(question_id: str = "LXJC0001", text: str = "原题") -> None:
    storage.write_question(
        question_id,
        {
            "id": question_id,
            "板块": "力学",
            "主类型": "基础题",
            "类型": ["基础题"],
            "知识点": ["速度"],
            "图片": [f"{question_id}_01.png"],
        },
        {"题目": text, "答案": "A", "解析": "解析", "备注": ""},
    )
    (config.ASSETS_DIR / f"{question_id}_01.png").write_bytes(b"image")


def test_delete_to_trash_and_restore(isolated_data):
    write_sample_question()

    deleted = maintenance.delete_question("LXJC0001")
    assert not storage.question_path("LXJC0001").exists()
    assert not (config.ASSETS_DIR / "LXJC0001_01.png").exists()
    assert maintenance.list_trash()[0]["trash_id"] == deleted["trash_id"]

    restored = maintenance.restore_trash(deleted["trash_id"])
    assert restored["restored"] == "LXJC0001"
    assert storage.question_path("LXJC0001").exists()
    assert (config.ASSETS_DIR / "LXJC0001_01.png").exists()
    assert storage.load_index()["LXJC"] == 1


def test_image_integrity_reports_missing_and_orphaned(isolated_data):
    write_sample_question()
    (config.ASSETS_DIR / "LXJC0001_01.png").unlink()
    (config.ASSETS_DIR / "orphan.png").write_bytes(b"orphan")

    result = maintenance.check_image_integrity()
    assert result["ok"] is False
    assert result["missing"] == [{"image": "LXJC0001_01.png", "question_ids": ["LXJC0001"]}]
    assert result["orphaned"] == ["orphan.png"]


def test_backup_can_restore_question_content(isolated_data):
    write_sample_question(text="备份版本")
    backup = maintenance.create_backup("测试")
    assert (config.BACKUPS_DIR / backup["filename"]).exists()

    metadata, sections = storage.read_question("LXJC0001")
    sections["题目"] = "修改版本"
    storage.write_question("LXJC0001", metadata, sections)

    result = maintenance.restore_backup(backup["filename"])
    _, restored_sections = storage.read_question("LXJC0001")
    assert restored_sections["题目"] == "备份版本"
    assert (config.BACKUPS_DIR / result["safety_backup"]).exists()


def test_automatic_backup_respects_interval(isolated_data):
    first = maintenance.ensure_automatic_backup()
    second = maintenance.ensure_automatic_backup()
    assert first["created"] is True
    assert second == {"created": False, "filename": first["filename"]}
