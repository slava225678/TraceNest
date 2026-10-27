import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.events import router
from app.groups import router as groups_router
from app.middleware import BodySizeLimitMiddleware
from app.migrations import upgrade_database
from app.ui import render_error
from app.ui import router as ui_router


def create_app(
    database_url: str | None = None, api_key: str | None = None
) -> FastAPI:
    database_url = (
        database_url
        if database_url is not None
        else os.environ["DATABASE_URL"]
    )
    api_key = (
        api_key if api_key is not None else os.environ["TRACENEST_API_KEY"]
    )
    if not api_key.strip():
        raise ValueError("TRACENEST_API_KEY must not be empty")
    engine = create_engine(database_url, pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            upgrade_database(engine)
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="TraceNest Lite", lifespan=lifespan)
    app.state.engine = engine
    app.state.api_key = api_key
    app.add_middleware(BodySizeLimitMiddleware)
    app.include_router(router)
    app.include_router(groups_router)
    app.include_router(ui_router)
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        path = request.url.path
        if path == "/" or path.startswith("/groups/"):
            return render_error(request, 503, "Database unavailable.")
        return JSONResponse(
            status_code=503, content={"detail": "Database unavailable"}
        )

    @app.get("/health")
    def health():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise HTTPException(
                status_code=503, detail="Database unavailable"
            ) from None
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
