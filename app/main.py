from fastapi import FastAPI

from app.api.routes import router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    fastapi_app = FastAPI(title=settings.app_name, version="0.2.0")
    fastapi_app.include_router(router, prefix=settings.api_prefix)
    return fastapi_app


app = create_app()
