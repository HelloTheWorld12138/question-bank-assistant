from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import config, storage
from app.api.routes import api_router, download_router
from app.errors import register_exception_handlers
from app.logging_config import configure_logging
from app.services.maintenance import ensure_automatic_backup


configure_logging()
storage.ensure_dirs()


class FreshStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict):
        response = await super().get_response(path, scope)
        if path.endswith((".html", ".css", ".js", ".mjs")):
            response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    storage.ensure_dirs()
    ensure_automatic_backup()
    yield


app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, lifespan=lifespan)
register_exception_handlers(app)
app.include_router(api_router)
app.include_router(download_router)


app.mount(
    "/draft-assets",
    StaticFiles(directory=str(config.DRAFT_ASSETS_DIR)),
    name="draft-assets",
)
app.mount("/assets", StaticFiles(directory=str(config.ASSETS_DIR)), name="assets")
app.mount("/", FreshStaticFiles(directory=str(config.STATIC_DIR), html=True), name="static")
