from pathlib import Path
import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.data import router as data_router
from app.api.image import router as image_router
from app.api.rag import router as rag_router
from app.api.agent import router as agent_router
from app.api.research import router as research_router
from app.core.config import settings
from app.db.session import engine
# Ensure all models are imported so Alembic can detect them
import app.models.db_connection  # noqa: F401
import app.models.image_rule  # noqa: F401

# Silence known non-fatal third-party telemetry noise in local/dev runs.
logging.getLogger("chromadb.telemetry.product.posthog").disabled = True


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    # ── startup ──────────────────────────────────────────────────────────────
    yield
    # ── shutdown ─────────────────────────────────────────────────────────────
    # Dispose the connection pool on graceful shutdown *and* on hot-reload.
    # Swallow CancelledError so uvicorn's watchfiles reload doesn't print a
    # spurious traceback.
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


# Ensure upload directory exists and serve files statically
uploads_path = Path(settings.UPLOAD_PATH)
uploads_path.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_path)), name="uploads")

generated_path = Path(settings.IMAGE_OUTPUT_PATH)
generated_path.mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=str(generated_path)), name="generated")

app.include_router(auth_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(image_router, prefix="/api")
app.include_router(rag_router, prefix="/api")
app.include_router(agent_router, prefix="/api")
app.include_router(data_router, prefix="/api")
app.include_router(research_router)
