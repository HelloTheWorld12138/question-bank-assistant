from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app import config, storage
from app.agent import opencode_available
from app.errors import AppError
from app.math_ocr import formula_ocr_available
from app.services import documents, maintenance, questions


api_router = APIRouter(prefix="/api")
download_router = APIRouter()


@api_router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "schema_version": config.SCHEMA_VERSION,
    }


@api_router.get("/options")
def options() -> dict[str, Any]:
    return {
        "blocks": [{"code": code, "name": name} for code, name in config.BLOCKS.items()],
        "types": [{"code": code, "name": name} for code, name in config.TYPES.items()],
        "pandoc": documents.find_pandoc() is not None,
        "agent": opencode_available(),
        "formula_ocr": formula_ocr_available(),
        "app_version": config.APP_VERSION,
        "schema_version": config.SCHEMA_VERSION,
    }


@api_router.post("/questions")
async def create_question(
    block_code: str = Form(...),
    type_code: str = Form(...),
    difficulty: str = Form(""),
    difficulty_coefficient: str = Form(""),
    year: str = Form(""),
    source: str = Form(""),
    question_text: str = Form(...),
    answer_text: str = Form(""),
    analysis_text: str = Form(""),
    knowledge_points: str = Form(""),
    extra_types: str = Form(""),
    remarks: str = Form(""),
    draft_id: str = Form(""),
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    return await questions.create_question(
        block_code=block_code,
        type_code=type_code,
        difficulty=difficulty,
        difficulty_coefficient=difficulty_coefficient,
        year=year,
        source=source,
        question_text=question_text,
        answer_text=answer_text,
        analysis_text=analysis_text,
        knowledge_points=knowledge_points,
        extra_types=extra_types,
        remarks=remarks,
        draft_id=draft_id,
        files=files,
    )


@api_router.post("/convert-docx")
async def convert_docx(file: UploadFile = File(...)) -> dict[str, Any]:
    return await documents.convert_docx(file)


@api_router.get("/questions")
def search_questions(
    block: str = "",
    main_type: str = "",
    difficulty: str = "",
    year: str = "",
    source: str = "",
    knowledge: str = "",
) -> dict[str, Any]:
    return {
        "items": questions.search_questions(
            block=block,
            main_type=main_type,
            difficulty=difficulty,
            year=year,
            source=source,
            knowledge=knowledge,
        )
    }


@api_router.get("/questions/{question_id}")
def get_question(question_id: str) -> dict[str, Any]:
    metadata, sections = storage.read_question(question_id)
    return {"metadata": metadata, "sections": sections}


@api_router.put("/questions/{question_id}")
def update_question(question_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return questions.update_question(question_id, payload)


@api_router.delete("/questions/{question_id}")
def delete_question(question_id: str) -> dict[str, Any]:
    return maintenance.delete_question(question_id)


@api_router.post("/export")
def export_exam(payload: dict[str, Any]) -> dict[str, Any]:
    return questions.export_exam(payload)


@api_router.post("/index/rebuild")
def rebuild_index() -> dict[str, Any]:
    return {"index": storage.rebuild_index()}


@api_router.get("/integrity")
def image_integrity() -> dict[str, Any]:
    return maintenance.check_image_integrity()


@api_router.get("/trash")
def list_trash() -> dict[str, Any]:
    return {"items": maintenance.list_trash()}


@api_router.post("/trash/{trash_id}/restore")
def restore_trash(trash_id: str) -> dict[str, Any]:
    return maintenance.restore_trash(trash_id)


@api_router.get("/backups")
def list_backups() -> dict[str, Any]:
    return {"items": maintenance.list_backups()}


@api_router.post("/backups")
def create_backup(payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return maintenance.create_backup(str((payload or {}).get("label") or "手动备份"))


@api_router.post("/backups/{filename}/restore")
def restore_backup(filename: str) -> dict[str, Any]:
    return maintenance.restore_backup(filename)


@download_router.get("/download/{filename}")
def download(filename: str) -> FileResponse:
    if filename != Path(filename).name or Path(filename).suffix.lower() not in {".md", ".docx"}:
        raise AppError("不允许下载该文件")
    path = config.EXPORT_DIR / filename
    if not path.exists():
        raise AppError("文件不存在", status_code=404, code="not_found")
    return FileResponse(path, filename=filename)
