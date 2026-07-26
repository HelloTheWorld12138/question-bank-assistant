from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app import config, knowledge, storage
from app.agent import opencode_available
from app.errors import AppError
from app.math_ocr import formula_ocr_available
from app.services import documents, imports as import_service, maintenance, models, office, questions


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
    storage.ensure_dirs()
    return {
        "blocks": [{"code": code, "name": name} for code, name in config.BLOCKS.items()],
        "types": [{"code": code, "name": name} for code, name in config.TYPES.items()],
        "question_types": list(config.QUESTION_TYPES),
        "knowledge_points": knowledge.knowledge_by_block(),
        "pandoc": documents.find_pandoc() is not None,
        "agent": opencode_available(),
        "formula_ocr": formula_ocr_available(),
        "ocr": import_service.ocr_status(),
        "officecli": office.officecli_status(),
        "templates": [
            {
                "key": key,
                "name": spec["name"],
                "filename": spec["filename"],
                "available": config.exam_template_path(key).is_file(),
                "customized": (config.USER_TEMPLATES_DIR / spec["filename"]).is_file(),
            }
            for key, spec in config.EXAM_TEMPLATES.items()
        ],
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
    question_type: str = Form(""),
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
        question_type=question_type,
        remarks=remarks,
        draft_id=draft_id,
        files=files,
    )


@api_router.post("/convert-docx")
async def convert_docx(file: UploadFile = File(...)) -> dict[str, Any]:
    return await documents.convert_docx(file)


@api_router.get("/import/status")
def import_status() -> dict[str, Any]:
    return {"ocr": import_service.ocr_status(), "tasks": import_service.list_import_tasks()}


@api_router.post("/import/analyze")
async def analyze_import(
    file: UploadFile = File(...),
    answer_file: Optional[UploadFile] = File(default=None),
) -> dict[str, Any]:
    return await import_service.create_import_task(file, answer_file)


@api_router.get("/import/tasks/{task_id}")
def get_import_task(task_id: str) -> dict[str, Any]:
    return import_service.load_import_task(task_id)


@api_router.put("/import/tasks/{task_id}")
def update_import_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return import_service.update_import_task(task_id, payload)


@api_router.post("/import/tasks/{task_id}/commit")
async def commit_import_task(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await import_service.commit_import_task(task_id, payload)


@api_router.post("/import/tasks/{task_id}/drafts/{draft_id}/images/{image_name}/process")
def process_import_image(
    task_id: str,
    draft_id: str,
    image_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return import_service.process_draft_image(task_id, draft_id, image_name, payload)


@api_router.post("/import/tasks/{task_id}/merge")
def merge_import_drafts(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return import_service.merge_import_drafts(
        task_id,
        str(payload.get("first_id") or ""),
        str(payload.get("second_id") or ""),
    )


@api_router.post("/import/tasks/{task_id}/drafts/{draft_id}/split")
def split_import_draft(task_id: str, draft_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return import_service.split_import_draft(
        task_id,
        draft_id,
        int(payload.get("position") or 0),
    )


@api_router.get("/questions")
def search_questions(
    block: str = "",
    main_type: str = "",
    difficulty: str = "",
    year: str = "",
    source: str = "",
    knowledge: str = "",
    question_type: str = "",
    query: str = "",
    sort_by: str = "id",
    sort_order: str = "asc",
) -> dict[str, Any]:
    return {
        "items": questions.search_questions(
            block=block,
            main_type=main_type,
            difficulty=difficulty,
            year=year,
            source=source,
            knowledge=knowledge,
            question_type=question_type,
            query=query,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    }


@api_router.get("/questions/{question_id}")
def get_question(question_id: str) -> dict[str, Any]:
    metadata, sections = storage.read_question(question_id)
    return {"metadata": metadata, "sections": sections}


@api_router.put("/questions/{question_id}")
def update_question(question_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return questions.update_question(question_id, payload)


@api_router.post("/questions/{question_id}/copy")
def copy_question(question_id: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return questions.copy_question(question_id, payload)


@api_router.post("/questions/batch-update")
def batch_update_questions(payload: dict[str, Any]) -> dict[str, Any]:
    return questions.batch_update_questions(payload)


@api_router.delete("/questions/{question_id}")
def delete_question(question_id: str) -> dict[str, Any]:
    return maintenance.delete_question(question_id)


@api_router.post("/export")
def export_exam(payload: dict[str, Any]) -> dict[str, Any]:
    return questions.export_exam(payload)


@api_router.post("/export-set")
def export_exam_set(payload: dict[str, Any]) -> dict[str, Any]:
    return questions.export_exam_set(payload)


@api_router.post("/index/rebuild")
def rebuild_index() -> dict[str, Any]:
    return {"index": storage.rebuild_index()}


@api_router.post("/templates/restore")
def restore_default_templates() -> dict[str, Any]:
    return {"restored": storage.restore_default_templates(overwrite=True)}


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


@api_router.get("/models/settings")
def get_model_settings() -> dict[str, Any]:
    return {"settings": models.load_model_settings(), "providers": models.provider_catalog()}


@api_router.put("/models/settings")
def update_model_settings(payload: dict[str, Any]) -> dict[str, Any]:
    return {"settings": models.save_model_settings(payload), "providers": models.provider_catalog()}


@api_router.post("/models/test")
def test_model_connection() -> dict[str, Any]:
    return models.test_model_connection()


@api_router.post("/ai/classify")
def classify_question(payload: dict[str, Any]) -> dict[str, Any]:
    return models.classify_question(payload)


@download_router.get("/download/{filename}")
def download(filename: str) -> FileResponse:
    if filename != Path(filename).name or Path(filename).suffix.lower() not in {".md", ".docx"}:
        raise AppError("不允许下载该文件")
    path = config.EXPORT_DIR / filename
    if not path.exists():
        raise AppError("文件不存在", status_code=404, code="not_found")
    return FileResponse(path, filename=filename)


@download_router.get("/preview/{filename}")
def preview(filename: str) -> FileResponse:
    if filename != Path(filename).name or Path(filename).suffix.lower() != ".html":
        raise AppError("不允许预览该文件")
    path = config.EXPORT_DIR / filename
    if not path.exists():
        raise AppError("预览文件不存在", status_code=404, code="not_found")
    return FileResponse(path, media_type="text/html")
