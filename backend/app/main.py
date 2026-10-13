from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, folders, notes, structuring
from app.core.config import get_settings
from app.core.logging import configure_logging, log_operation
from app.infrastructure.database.session import close_db, init_db

settings = get_settings()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(folders.router, prefix="/api/v1")
    app.include_router(structuring.router, prefix="/api/v1")
    app.include_router(notes.router, prefix="/api/v1")

    @app.on_event("startup")
    @log_operation("database.startup")
    async def startup():
        await init_db()

    @app.on_event("shutdown")
    @log_operation("database.shutdown")
    async def shutdown():
        await close_db()

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
