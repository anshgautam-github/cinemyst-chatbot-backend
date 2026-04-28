from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .routes.chat import router as chat_router
from .routes.recommendation import router as recommendation_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Placeholder startup/shutdown hook so app lifecycle logic has a home when needed."""
    yield


def create_app() -> FastAPI:
    """Build the FastAPI application and register feature routers."""
    settings = get_settings()
    app = FastAPI(
        title="CineMyst Chatbot Backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(chat_router)
    app.include_router(recommendation_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Lightweight health endpoint for local checks and hosting platform probes."""
        return {"status": "ok", "environment": settings.app_env}

    return app


app = create_app()
