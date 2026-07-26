from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app import config, storage
from app.errors import AppError, NotFoundError


def timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def delete_question(question_id: str) -> dict[str, Any]:
    metadata, _ = storage.read_question(question_id)
    source_question = storage.question_path(question_id)
    trash_id = f"{question_id}_{timestamp()}_{uuid.uuid4().hex[:8]}"
    target_dir = config.TRASH_DIR / trash_id
    assets_dir = target_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=False)

    moved_assets: list[str] = []
    candidates = {str(name) for name in metadata.get("图片", []) or []}
    candidates.update(path.name for path in config.ASSETS_DIR.glob(f"{question_id}_*"))
    try:
        os.replace(source_question, target_dir / "question.md")
        for name in sorted(candidates):
            source = config.ASSETS_DIR / Path(name).name
            if source.is_file():
                os.replace(source, assets_dir / source.name)
                moved_assets.append(source.name)
        manifest = {
            "trash_id": trash_id,
            "question_id": question_id,
            "deleted_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "assets": moved_assets,
        }
        storage.atomic_write_text(
            target_dir / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
    except Exception:
        if (target_dir / "question.md").exists():
            os.replace(target_dir / "question.md", source_question)
        for name in moved_assets:
            source = assets_dir / name
            if source.exists():
                os.replace(source, config.ASSETS_DIR / name)
        shutil.rmtree(target_dir, ignore_errors=True)
        raise
    return manifest


def list_trash() -> list[dict[str, Any]]:
    storage.ensure_dirs()
    items = []
    for manifest_path in sorted(config.TRASH_DIR.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        items.append(manifest)
    return items


def restore_trash(trash_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Z]{4}\d{4}_\d{8}_\d{6}_[a-f0-9]{8}", trash_id):
        raise AppError("回收站条目标识无效")
    source_dir = config.TRASH_DIR / trash_id
    manifest_path = source_dir / "manifest.json"
    question_file = source_dir / "question.md"
    if not manifest_path.exists() or not question_file.exists():
        raise NotFoundError("回收站条目不存在")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    question_id = str(manifest["question_id"])
    target_question = storage.question_path(question_id)
    if target_question.exists():
        raise AppError("正式题库中已经存在同题号题目，无法恢复")
    for name in manifest.get("assets", []):
        if (config.ASSETS_DIR / Path(name).name).exists():
            raise AppError(f"图片已存在，无法恢复：{name}")

    os.replace(question_file, target_question)
    for name in manifest.get("assets", []):
        source = source_dir / "assets" / Path(name).name
        if source.exists():
            os.replace(source, config.ASSETS_DIR / source.name)
    shutil.rmtree(source_dir, ignore_errors=True)
    storage.rebuild_index()
    return {"restored": question_id, "trash_id": trash_id}


def check_image_integrity() -> dict[str, Any]:
    referenced: dict[str, list[str]] = {}
    for item in storage.read_all_questions():
        for raw_name in item.get("图片", []) or []:
            name = Path(str(raw_name)).name
            referenced.setdefault(name, []).append(str(item["id"]))
    existing = {
        path.name
        for path in config.ASSETS_DIR.iterdir()
        if path.is_file() and path.name != ".gitkeep" and path.suffix.lower() in config.IMAGE_EXTENSIONS
    }
    missing = [
        {"image": name, "question_ids": ids}
        for name, ids in sorted(referenced.items())
        if name not in existing
    ]
    orphaned = sorted(existing - set(referenced))
    return {
        "ok": not missing and not orphaned,
        "referenced_count": len(referenced),
        "existing_count": len(existing),
        "missing": missing,
        "orphaned": orphaned,
    }


def create_backup(label: str = "手动备份") -> dict[str, Any]:
    storage.ensure_dirs()
    safe_label = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", label).strip("_") or "备份"
    filename = f"题库备份_{timestamp()}_{uuid.uuid4().hex[:6]}_{safe_label}.zip"
    target = config.BACKUPS_DIR / filename
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if config.INDEX_FILE.exists():
            archive.write(config.INDEX_FILE, "index.json")
        for root, prefix in ((config.QUESTIONS_DIR, "题目"), (config.ASSETS_DIR, "assets")):
            for path in root.rglob("*"):
                if not path.is_file() or config.DRAFT_ASSETS_DIR in path.parents:
                    continue
                archive.write(path, f"{prefix}/{path.relative_to(root).as_posix()}")
    return {"filename": filename, "created_at": datetime.now().astimezone().isoformat(), "size": target.stat().st_size}


def ensure_automatic_backup(interval_hours: int = 24, keep: int = 10) -> dict[str, Any]:
    storage.ensure_dirs()
    automatic = sorted(
        config.BACKUPS_DIR.glob("*_自动备份.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    minimum_age = max(interval_hours, 1) * 60 * 60
    if automatic and datetime.now().timestamp() - automatic[0].stat().st_mtime < minimum_age:
        return {"created": False, "filename": automatic[0].name}

    created = create_backup("自动备份")
    for expired in automatic[max(keep - 1, 0):]:
        expired.unlink(missing_ok=True)
    return {"created": True, "filename": created["filename"]}


def list_backups() -> list[dict[str, Any]]:
    storage.ensure_dirs()
    return [
        {"filename": path.name, "size": path.stat().st_size, "modified_at": path.stat().st_mtime}
        for path in sorted(config.BACKUPS_DIR.glob("*.zip"), reverse=True)
    ]


def restore_backup(filename: str) -> dict[str, Any]:
    if Path(filename).name != filename or not filename.endswith(".zip"):
        raise AppError("备份文件名无效")
    backup = config.BACKUPS_DIR / filename
    if not backup.exists():
        raise NotFoundError("备份文件不存在")
    safety_backup = create_backup("恢复前自动备份")

    with tempfile.TemporaryDirectory() as temp_dir:
        staging = Path(temp_dir)
        with zipfile.ZipFile(backup) as archive:
            for member in archive.infolist():
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise AppError("备份文件包含不安全路径")
                if member_path.parts and member_path.parts[0] not in {"题目", "assets", "index.json"}:
                    raise AppError("备份文件结构不受支持")
            archive.extractall(staging)
        if not (staging / "题目").exists():
            raise AppError("备份中缺少题目目录")

        shutil.rmtree(config.QUESTIONS_DIR, ignore_errors=True)
        shutil.rmtree(config.ASSETS_DIR, ignore_errors=True)
        shutil.copytree(staging / "题目", config.QUESTIONS_DIR)
        if (staging / "assets").exists():
            shutil.copytree(staging / "assets", config.ASSETS_DIR)
        else:
            config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        config.DRAFT_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        if (staging / "index.json").exists():
            storage.atomic_write_text(config.INDEX_FILE, (staging / "index.json").read_text(encoding="utf-8"))
        else:
            storage.rebuild_index()

    return {"restored": filename, "safety_backup": safety_backup["filename"]}
