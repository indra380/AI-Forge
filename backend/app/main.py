from pathlib import Path
import asyncio
import contextlib
import logging
import sys
import time

from fastapi import FastAPI
from fastapi import Request
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
from app.core.logging import configure_application_logging
from app.db.session import engine
# Ensure all models are imported so Alembic can detect them
import app.models.db_connection  # noqa: F401
import app.models.image_rule  # noqa: F401

# Silence known non-fatal third-party telemetry noise in local/dev runs.
logging.getLogger("chromadb.telemetry.product.posthog").disabled = True
configure_application_logging()
logger = logging.getLogger("uvicorn.error")


def _install_windows_asyncio_exception_filter() -> None:
    """Suppress known non-fatal Proactor shutdown noise on Windows."""
    if sys.platform != "win32":
        return

    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def _handler(loop_obj: asyncio.AbstractEventLoop, context: dict) -> None:
        exc = context.get("exception")
        message = str(context.get("message") or "")

        # Ignore noisy but harmless socket shutdown race during connection close.
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10038:
            if "_call_connection_lost" in message or "Proactor" in message:
                logger.debug("Suppressed non-fatal Windows Proactor close error: %s", exc)
                return

        if previous_handler is not None:
            previous_handler(loop_obj, context)
        else:
            loop_obj.default_exception_handler(context)

    loop.set_exception_handler(_handler)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    # ── startup ──────────────────────────────────────────────────────────────
    _install_windows_asyncio_exception_filter()
    startup_msg = f"app_startup | env={settings.ENVIRONMENT} | app={settings.APP_NAME}"
    logger.info(startup_msg)
    print(startup_msg, flush=True)
    try:
        yield
    except asyncio.CancelledError:
        # Expected during watchfiles reload and process restarts on Windows.
        # Suppress to avoid noisy traceback in local dev logs.
        return
    finally:
        # ── shutdown ─────────────────────────────────────────────────────────
        # Dispose the connection pool on graceful shutdown *and* on hot-reload.
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


@app.middleware("http")
async def log_tictactoe_requests(request: Request, call_next):
    path = request.url.path
    if "/tictactoe" in path:
        msg = f"ttt_http_request | method={request.method} | path={path}"
        logger.info(msg)
        print(msg, flush=True)
    response = await call_next(request)
    if "/tictactoe" in path:
        msg = (
            f"ttt_http_response | method={request.method} | path={path} "
            f"| status={response.status_code}"
        )
        logger.info(msg)
        print(msg, flush=True)
    return response


@app.middleware("http")
async def log_api_requests(request: Request, call_next):
    if not request.url.path.startswith("/api"):
        return await call_next(request)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        msg = (
            f"api_request_error | method={request.method} | path={request.url.path} "
            f"| elapsed_ms={elapsed_ms:.1f}"
        )
        logger.exception(msg)
        print(msg, flush=True)
        raise

    elapsed_ms = (time.perf_counter() - start) * 1000
    msg = (
        f"api_request | method={request.method} | path={request.url.path} "
        f"| status={response.status_code} | elapsed_ms={elapsed_ms:.1f}"
    )
    logger.info(msg)
    print(msg, flush=True)
    return response


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
