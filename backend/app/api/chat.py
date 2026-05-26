import json
import re
import uuid
from pathlib import Path
from collections.abc import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import llm
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.user import User
from app.schemas.chat import (
    ChatHistoryItem,
    ChatRequest,
    TicTacToeMoveRequest,
    TicTacToeStateResponse,
    ThreadCreate,
    ThreadResponse,
    ThreadUpdate,
    UnifiedChatMessageRequest,
    UploadResponse,
)
from app.schemas.image import ImageGenerateRequest, ImageGenerateResponse
from app.services.attachment_service import AttachmentService, get_attachment_service
from app.services.auth_service import get_current_user
from app.services.chat_service import (
    generate_thread_title,
    list_chat_messages,
    load_chat_system_prompt,
    save_chat_message,
)
from app.services.in_chat_rag_service import InChatRagService, get_in_chat_rag_service
from app.services.image_generation_service import ImageGenerationService, get_image_generation_service
from app.services.tic_tac_toe_service import TicTacToeService, get_tic_tac_toe_service
from app.core.logging import get_logger
from app.services.thread_service import (
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    rename_thread,
    touch_thread,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = get_logger("uvicorn.error")

# ---------------------------------------------------------------------------
# Intent detection helpers
# ---------------------------------------------------------------------------

def _is_image_request(text: str) -> bool:
    lowered = text.lower()
    image_patterns = [
        r"\bgenerate\b.*\bimage\b",
        r"\bcreate\b.*\bimage\b",
        r"\bmake\b.*\bimage\b",
        r"\bimage\b.*\bof\b",
        r"^/image\b",
        r"^/imagine\b",
    ]
    return any(re.search(pattern, lowered) for pattern in image_patterns)


def _is_connect_db_command(text: str) -> bool:
    return bool(re.match(r"^/connect[\-_]?db\b", text.strip(), re.IGNORECASE))


def _is_agent_command(text: str) -> bool:
    return text.strip().lower().startswith("/agent ")


def _is_validate_command(text: str, has_images: bool) -> bool:
    lowered = text.lower()
    validation_keywords = ["validate", "check rules", "verify", "compliance", "rule check"]
    return has_images and any(k in lowered for k in validation_keywords)


def _is_excel_question(text: str, has_table: bool) -> bool:
    """Return True if session has table/spreadsheet and message looks like data question."""
    if not has_table:
        return False
    data_keywords = [
        "total", "sum", "average", "mean", "count", "how many", "highest", "lowest",
        "maximum", "minimum", "top", "bottom", "trend", "sales", "revenue", "profit",
        "column", "row", "sheet", "filter", "sort", "group", "pivot",
    ]
    lowered = text.lower()
    return any(k in lowered for k in data_keywords)


def _is_db_question(text: str, has_db: bool) -> bool:
    """Return True if thread has DB and message looks like a database question."""
    if not has_db:
        return False
    db_keywords = [
        "how many", "count", "show me", "list", "find", "what are", "which",
        "total", "sum", "average", "top", "recent", "latest", "oldest",
        "users", "customers", "orders", "products", "revenue", "sales",
    ]
    lowered = text.lower()
    # Skip generic conversational messages
    skip_patterns = [r"^(hi|hello|hey|thanks|thank you|ok|okay|sure|yes|no)\b"]
    if any(re.match(p, lowered) for p in skip_patterns):
        return False
    return any(k in lowered for k in db_keywords)


def _extract_image_prompt(text: str) -> str:
    stripped = text.strip()
    if stripped.lower().startswith("/image"):
        return stripped[6:].strip() or "creative image"
    if stripped.lower().startswith("/imagine"):
        return stripped[8:].strip() or "creative image"

    cleaned = re.sub(r"\b(generate|create|make)\b", "", stripped, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(image|picture|photo|artwork|art)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(of|for|about)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;")
    return cleaned or stripped


def _render_attachment_markdown(
    *,
    base_url: str,
    file_url: str,
    original_name: str,
    attachment_type: str,
) -> str:
    absolute_url = f"{base_url}{file_url}" if file_url.startswith("/") else file_url
    if attachment_type == "image":
        return f"![{original_name}]({absolute_url})"
    if attachment_type == "video":
        return f"[{original_name} (video)]({absolute_url})"
    return f"[{original_name}]({absolute_url})"


def _message_with_attachment_previews(
    *,
    message_text: str,
    previews: list[str],
) -> str:
    cleaned = message_text.strip()
    if not previews:
        return cleaned
    joined = "\n\n".join(previews)
    if not cleaned:
        return joined
    return f"{cleaned}\n\n{joined}"


# ---------------------------------------------------------------------------
# Thread CRUD
# ---------------------------------------------------------------------------

@router.get("/threads", response_model=list[ThreadResponse])
async def get_threads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ThreadResponse]:
    threads = await list_threads(db, current_user.id)
    return [ThreadResponse.model_validate(t, from_attributes=True) for t in threads]


@router.post("/threads", response_model=ThreadResponse, status_code=201)
async def post_thread(
    body: ThreadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThreadResponse:
    thread = await create_thread(db, current_user.id, body.title)
    return ThreadResponse.model_validate(thread, from_attributes=True)


@router.patch("/threads/{thread_id}", response_model=ThreadResponse)
async def patch_thread(
    thread_id: uuid.UUID,
    body: ThreadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThreadResponse:
    thread = await rename_thread(db, thread_id, current_user.id, body.title)
    if thread is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "message": "Thread not found"}
        )
    return ThreadResponse.model_validate(thread, from_attributes=True)


@router.delete("/threads/{thread_id}", status_code=204)
async def remove_thread(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    deleted = await delete_thread(db, thread_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "message": "Thread not found"}
        )


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@router.get("/threads/{thread_id}/messages", response_model=list[ChatHistoryItem])
async def get_messages(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatHistoryItem]:
    thread = await get_thread(db, thread_id, current_user.id)
    if thread is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "message": "Thread not found"}
        )
    messages = await list_chat_messages(db, current_user.id, thread_id)
    return [ChatHistoryItem.model_validate(m, from_attributes=True) for m in messages]


def _tictactoe_state_payload(thread_context: dict | None, message: str | None = None) -> TicTacToeStateResponse:
    state = dict((thread_context or {}).get("tic_tac_toe") or {})
    board = state.get("board")
    if not isinstance(board, list) or len(board) != 9:
        board = [" "] * 9
    return TicTacToeStateResponse(
        active=bool(state.get("active", False)),
        board=[str(cell) for cell in board],
        winner=state.get("winner"),
        move_count=int(state.get("move_count", 0)),
        message=message,
    )


@router.get("/threads/{thread_id}/tictactoe", response_model=TicTacToeStateResponse)
async def get_tictactoe_state(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicTacToeStateResponse:
    logger.info(
        "ttt_api_get_state | user=%s | thread_id=%s",
        current_user.email,
        str(thread_id),
    )
    thread = await get_thread(db, thread_id, current_user.id)
    if thread is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "message": "Thread not found"}
        )
    return _tictactoe_state_payload(thread.context)


@router.post("/threads/{thread_id}/tictactoe/start", response_model=TicTacToeStateResponse)
async def start_tictactoe(
    thread_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tic_tac_toe_service: TicTacToeService = Depends(get_tic_tac_toe_service),
) -> TicTacToeStateResponse:
    logger.info(
        "ttt_api_start | user=%s | thread_id=%s",
        current_user.email,
        str(thread_id),
    )
    thread = await get_thread(db, thread_id, current_user.id)
    if thread is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "message": "Thread not found"}
        )

    result = tic_tac_toe_service.process_message(
        "/ttt start",
        thread.context,
        user_email=current_user.email,
        thread_id=str(thread_id),
    )
    thread.context = result.context
    await db.commit()
    return _tictactoe_state_payload(thread.context, result.response)


@router.post("/threads/{thread_id}/tictactoe/move", response_model=TicTacToeStateResponse)
async def move_tictactoe(
    thread_id: uuid.UUID,
    body: TicTacToeMoveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tic_tac_toe_service: TicTacToeService = Depends(get_tic_tac_toe_service),
) -> TicTacToeStateResponse:
    logger.info(
        "ttt_api_move | user=%s | thread_id=%s | position=%s",
        current_user.email,
        str(thread_id),
        body.position,
    )
    thread = await get_thread(db, thread_id, current_user.id)
    if thread is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "message": "Thread not found"}
        )

    result = tic_tac_toe_service.process_message(
        f"/ttt {body.position}",
        thread.context,
        user_email=current_user.email,
        thread_id=str(thread_id),
    )
    thread.context = result.context
    await db.commit()
    await touch_thread(db, thread)
    return _tictactoe_state_payload(thread.context, result.response)


# ---------------------------------------------------------------------------
# File upload (PDF → auto-indexed into session RAG collection)
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_file(
    background_tasks: BackgroundTasks,
    session_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    rag_service: InChatRagService = Depends(get_in_chat_rag_service),
    attachment_service: AttachmentService = Depends(get_attachment_service),
) -> UploadResponse:
    attachment = await attachment_service.upload_attachment(
        db,
        user_id=current_user.id,
        session_id=session_id,
        upload=file,
    )
    response = attachment_service.to_response(attachment)

    # Auto-index PDFs in the background — non-blocking, idempotent
    suffix = Path(attachment.original_name).suffix.lower()
    is_pdf = attachment.attachment_type == "document" and suffix == ".pdf"
    if is_pdf:
        background_tasks.add_task(
            rag_service.index_pdf,
            session_id=session_id,
            document_id=attachment.id,
            file_path=Path(attachment.storage_path),
            filename=attachment.original_name,
        )

    return UploadResponse(
        file_id=str(attachment.id),
        filename=attachment.original_name,
        content_type=attachment.content_type,
        size=attachment.file_size,
        is_indexed=is_pdf,
        file_url=response.file_url,
        attachment_type=response.attachment_type,
    )


@router.delete("/upload/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    attachment_service: AttachmentService = Depends(get_attachment_service),
) -> None:
    await attachment_service.delete_pending_attachment(
        db,
        user_id=current_user.id,
        session_id=session_id,
        attachment_id=file_id,
    )


@router.post("/image/generate", response_model=ImageGenerateResponse)
async def generate_image_from_chat(
    body: ImageGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    image_service: ImageGenerationService = Depends(get_image_generation_service),
) -> ImageGenerateResponse:
    session_id = body.session_id or uuid.uuid4()
    result = await image_service.generate(
        db=db,
        user_id=current_user.id,
        user_email=current_user.email,
        prompt=body.prompt,
        size=body.size,
        style=body.style,
        image_count=body.image_count,
        session_id=session_id,
        thread_id=body.thread_id,
        negative_prompt=body.negative_prompt,
        seed=body.seed,
    )

    images = [image_service.to_response(img) for img in result.images]
    primary_image_url = images[0].image_url if images else ""

    return ImageGenerateResponse(
        image_url=primary_image_url,
        prompt=body.prompt,
        images=images,
        assistant_message=result.assistant_message,
    )


@router.post("/message")
async def post_message(
    body: UnifiedChatMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    rag_service: InChatRagService = Depends(get_in_chat_rag_service),
    image_service: ImageGenerationService = Depends(get_image_generation_service),
    attachment_service: AttachmentService = Depends(get_attachment_service),
    tic_tac_toe_service: TicTacToeService = Depends(get_tic_tac_toe_service),
) -> StreamingResponse:
    proxied = ChatRequest(
        message=body.message,
        session_id=body.session_id,
        attachment_ids=body.attachment_ids,
    )
    return await stream_thread(
        thread_id=body.thread_id,
        body=proxied,
        request=request,
        db=db,
        current_user=current_user,
        rag_service=rag_service,
        image_service=image_service,
        attachment_service=attachment_service,
        tic_tac_toe_service=tic_tac_toe_service,
    )



# ---------------------------------------------------------------------------
# Streaming chat (with automatic multi-PDF RAG injection)
# ---------------------------------------------------------------------------

@router.post("/threads/{thread_id}/stream")
async def stream_thread(
    thread_id: uuid.UUID,
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    rag_service: InChatRagService = Depends(get_in_chat_rag_service),
    image_service: ImageGenerationService = Depends(get_image_generation_service),
    attachment_service: AttachmentService = Depends(get_attachment_service),
    tic_tac_toe_service: TicTacToeService = Depends(get_tic_tac_toe_service),
) -> StreamingResponse:
    thread = await get_thread(db, thread_id, current_user.id)
    if thread is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "message": "Thread not found"}
        )

    existing = await list_chat_messages(db, current_user.id, thread_id)
    is_first = len(existing) == 0

    user_text = body.message.strip()
    session_id = body.session_id
    attachment_ids = body.attachment_ids
    if attachment_ids and session_id is None:
        raise HTTPException(
            status_code=422,
            detail={"error": "missing_session", "message": "session_id is required when attachment_ids are provided"},
        )

    # ── Gather attachment metadata ──────────────────────────────────────────
    attachment_context = ""
    multimodal_user_text: str | list[dict[str, object]] = user_text
    has_images = False
    has_tables = False
    image_attachment_paths: list[str] = []
    table_attachment_paths: list[str] = []

    if attachment_ids and session_id is not None:
        attachment_context = await attachment_service.build_attachment_context(
            db,
            user_id=current_user.id,
            session_id=session_id,
            attachment_ids=attachment_ids,
        )
        multimodal_user_text = await attachment_service.build_multimodal_user_content(
            db,
            user_id=current_user.id,
            session_id=session_id,
            attachment_ids=attachment_ids,
            message_text=user_text,
        )
        # Collect attachment types and paths for advanced routing
        for att_id in attachment_ids:
            att_uuid = uuid.UUID(str(att_id))
            result = await db.execute(
                select(Attachment).where(
                    Attachment.id == att_uuid,
                    Attachment.user_id == current_user.id,
                )
            )
            att = result.scalar_one_or_none()
            if att:
                if att.attachment_type == "image":
                    has_images = True
                    image_attachment_paths.append(att.storage_path)
                elif att.attachment_type == "table":
                    has_tables = True
                    table_attachment_paths.append(att.storage_path)

    # Thread context (DB connection)
    thread_context: dict = thread.context or {}
    active_db_id: str | None = thread_context.get("db_connection_id")

    # ── Helper: save user message & link attachments ────────────────────────
    async def _save_user_message(text: str) -> None:
        user_row = await save_chat_message(db, current_user.id, thread_id, "user", text)
        if attachment_ids and session_id is not None:
            linked = await attachment_service.attach_uploaded_files_to_message(
                db,
                user_id=current_user.id,
                session_id=session_id,
                message_id=user_row.id,
                attachment_ids=attachment_ids,
            )
            base_url = str(request.base_url).rstrip("/")
            previews = [
                _render_attachment_markdown(
                    base_url=base_url,
                    file_url=attachment_service.to_response(item).file_url,
                    original_name=item.original_name,
                    attachment_type=item.attachment_type,
                )
                for item in linked
            ]
            user_row.content = _message_with_attachment_previews(
                message_text=text, previews=previews
            )
            await db.commit()

    # ── Helper: stream a prebuilt response ───────────────────────────────────
    async def _simple_stream(response_text: str, is_first_msg: bool = is_first) -> AsyncGenerator[str, None]:
        await save_chat_message(db, current_user.id, thread_id, "assistant", response_text)
        await touch_thread(db, thread)
        yield f"data: {json.dumps({'type': 'token', 'content': response_text})}\n\n"
        if is_first_msg and thread.title in ("New Chat", ""):
            try:
                new_title = await generate_thread_title(body.message, current_user.email)
                renamed = await rename_thread(db, thread_id, current_user.id, new_title)
                if renamed:
                    yield f"data: {json.dumps({'type': 'thread_renamed', 'content': renamed.title})}\n\n"
            except Exception:
                pass
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    if tic_tac_toe_service.should_handle(user_text, thread_context):
        await _save_user_message(body.message)
        game_result = tic_tac_toe_service.process_message(
            user_text,
            thread_context,
            user_email=current_user.email,
            thread_id=str(thread_id),
        )
        thread.context = game_result.context
        await db.commit()
        return StreamingResponse(_simple_stream(game_result.response), media_type="text/event-stream")

    # ── /connect-db command ───────────────────────────────────────────────────
    if _is_connect_db_command(user_text):
        from app.services.database_service import parse_connect_command, save_db_connection, SUPPORTED_DB_TYPES
        await _save_user_message(body.message)
        try:
            params = parse_connect_command(user_text)
            conn = await save_db_connection(
                db,
                user_id=current_user.id,
                name=params.get("name", "My Database"),
                db_type=params.get("db_type", "postgresql"),
                host=params.get("host"),
                port=int(params["port"]) if "port" in params else None,
                database=params.get("database"),
                username=params.get("username"),
                password=params.get("password"),
                full_url=params.get("full_url"),
            )
            # Activate for current thread
            ctx = thread.context or {}
            ctx["db_connection_id"] = str(conn.id)
            thread.context = ctx
            await db.commit()
            response = (
                f"✅ Database **{conn.name}** ({conn.db_type}) connected successfully!\n\n"
                f"I've activated this connection for this thread. "
                f"You can now ask questions about your data in plain English.\n\n"
                f"**Connection ID:** `{conn.id}`\n\n"
                f"Try asking: *\"Show me all tables\"* or *\"How many records are in the users table?\"*"
            )
        except Exception as exc:
            response = (
                f"❌ Failed to connect: {exc}\n\n"
                "Use the format:\n"
                "```\n/connect-db type=postgresql host=localhost port=5432 database=mydb user=admin password=secret name=\"My DB\"\n```\n"
                "Or with a full URL:\n"
                "```\n/connect-db postgresql://user:pass@host:5432/dbname name=\"My DB\"\n```"
            )
        return StreamingResponse(_simple_stream(response), media_type="text/event-stream")

    # ── /agent command ────────────────────────────────────────────────────────
    if _is_agent_command(user_text):
        from app.services.agent_service import run_agent

        await _save_user_message(body.message)
        task = re.sub(r"^/agent\s+", "", user_text, flags=re.IGNORECASE).strip()
        chat_history = "\n".join(
            f"{'User' if m.role == 'user' else 'Assistant'}: {m.content[:300]}"
            for m in existing[-6:]
        )
        result = await run_agent(task, user_email=current_user.email, chat_history=chat_history)

        parts = [f"**Task:** {task}\n"]
        if result["steps"]:
            parts.append("**Reasoning steps:**")
            for step in result["steps"]:
                parts.append(f"> {step}")
        parts.append(f"\n**Answer:** {result['answer']}")
        response = "\n\n".join(parts)

        return StreamingResponse(_simple_stream(response), media_type="text/event-stream")

    # ── Image validation ──────────────────────────────────────────────────────
    if _is_validate_command(user_text, has_images) and image_attachment_paths:
        from app.services.image_validation_service import validate_image, validate_image_freeform
        from app.services.rule_engine_service import list_rules

        await _save_user_message(body.message)

        # Check if user referenced a rule by name, else do freeform validation
        user_rules = await list_rules(db, current_user.id)
        matched_rule = None
        for r in user_rules:
            if r.name.lower() in user_text.lower():
                matched_rule = r
                break

        all_responses: list[str] = []
        for img_path in image_attachment_paths:
            if matched_rule:
                result = await validate_image(img_path, matched_rule, current_user.email)
            else:
                result = await validate_image_freeform(img_path, user_text, current_user.email)

            # Format as structured block for frontend rendering
            result_json = json.dumps(result)
            all_responses.append(f"```validation\n{result_json}\n```")

        response = "\n\n".join(all_responses)
        return StreamingResponse(_simple_stream(response), media_type="text/event-stream")

    # ── Excel / CSV analysis ──────────────────────────────────────────────────
    if _is_excel_question(user_text, has_tables) and table_attachment_paths:
        from app.services.excel_service import analyze_dataframe

        await _save_user_message(body.message)
        file_path = table_attachment_paths[0]  # Use first table attachment
        result = await analyze_dataframe(file_path, user_text, current_user.email)

        parts: list[str] = []
        if result["data_summary"]:
            parts.append(f"**Dataset overview:**\n{result['data_summary']}")
        parts.append(f"**Analysis:**\n{result['answer']}")
        if result.get("error"):
            parts.append(f"⚠️ Note: {result['error']}")
        response = "\n\n".join(parts)

        return StreamingResponse(_simple_stream(response), media_type="text/event-stream")

    # ── NL-to-SQL (if DB connected to thread) ─────────────────────────────────
    if active_db_id and _is_db_question(user_text, has_db=True):
        from app.services.database_service import get_db_connection
        from app.services.sql_agent_service import run_nl_to_sql

        conn = await get_db_connection(db, uuid.UUID(active_db_id), current_user.id)
        if conn:
            await _save_user_message(body.message)
            result = await run_nl_to_sql(conn, user_text, current_user.email)

            parts = []
            if result.get("error"):
                parts.append(f"⚠️ Error: {result['error']}")
            else:
                if result["answer"]:
                    parts.append(result["answer"])
                if result["sql"]:
                    parts.append(f"The SQL query used for this is:\n```sql\n{result['sql']}\n```")
                else:
                    parts.append("The SQL query used for this is: _Not available._")
            response = "\n\n".join(parts)

            return StreamingResponse(_simple_stream(response), media_type="text/event-stream")

    # ── Unified mode: image generation from the same chat box ───────────────
    if _is_image_request(user_text):
        image_session_id = session_id or uuid.uuid4()
        image_prompt = _extract_image_prompt(user_text)

        user_message_row = await save_chat_message(db, current_user.id, thread_id, "user", body.message)

        attachment_previews: list[str] = []
        if attachment_ids and session_id is not None:
            linked = await attachment_service.attach_uploaded_files_to_message(
                db,
                user_id=current_user.id,
                session_id=session_id,
                message_id=user_message_row.id,
                attachment_ids=attachment_ids,
            )
            base_url = str(request.base_url).rstrip("/")
            attachment_previews = [
                _render_attachment_markdown(
                    base_url=base_url,
                    file_url=attachment_service.to_response(item).file_url,
                    original_name=item.original_name,
                    attachment_type=item.attachment_type,
                )
                for item in linked
            ]
            user_message_row.content = _message_with_attachment_previews(
                message_text=body.message,
                previews=attachment_previews,
            )
            await db.commit()

        try:
            image_result = await image_service.generate(
                db=db,
                user_id=current_user.id,
                user_email=current_user.email,
                prompt=image_prompt,
                size="1024x1024",
                style="realistic",
                image_count=1,
                session_id=image_session_id,
                thread_id=thread_id,
                negative_prompt=None,
                seed=None,
            )
        except HTTPException as exc:
            error_message = "Image generation failed"
            if isinstance(exc.detail, dict):
                error_message = str(exc.detail.get("message", error_message))

            async def error_stream() -> AsyncGenerator[str, None]:
                yield f"data: {json.dumps({'type': 'error', 'message': error_message})}\n\n"

            return StreamingResponse(error_stream(), media_type="text/event-stream")

        base_url = str(request.base_url).rstrip("/")
        image_lines = [f"Generated image for: **{image_prompt}**"]
        for img in image_result.images:
            full_url = f"{base_url}{img.image_url}" if img.image_url.startswith("/") else img.image_url
            image_lines.append(f"![Generated image]({full_url})")
            image_lines.append(f"[Open image]({full_url})")
            image_lines.append(f"[Download image]({base_url}/api/image/{img.id}/download)")

        assistant_markdown = "\n\n".join(image_lines)
        await save_chat_message(db, current_user.id, thread_id, "assistant", assistant_markdown)
        await touch_thread(db, thread)

        async def image_stream() -> AsyncGenerator[str, None]:
            yield f"data: {json.dumps({'type': 'token', 'content': assistant_markdown})}\n\n"
            if is_first and thread.title in ("New Chat", ""):
                try:
                    new_title = await generate_thread_title(body.message, current_user.email)
                    renamed = await rename_thread(db, thread_id, current_user.id, new_title)
                    if renamed:
                        yield f"data: {json.dumps({'type': 'thread_renamed', 'content': renamed.title})}\n\n"
                except Exception:
                    pass
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(image_stream(), media_type="text/event-stream")

    # ── RAG: retrieve context across all PDFs uploaded in this session ──────
    rag_context = ""
    if session_id:
        try:
            rag_context, _ = await rag_service.retrieve_context(
                session_id=session_id,
                query=user_text or "summary",
            )
        except Exception:
            rag_context = ""  # RAG failure must never break the chat

    # ── Build message list for the LLM ──────────────────────────────────────
    system_content = load_chat_system_prompt()
    if rag_context:
        system_content += (
            "\n\n---\n"
            "The user has uploaded PDF documents. The following excerpts are the most "
            "relevant sections retrieved from those documents. Use this context to answer "
            "accurately. Always cite the source filename and page number.\n\n"
            f"{rag_context}\n---"
        )
    if attachment_context:
        system_content += (
            "\n\n---\n"
            "The user has uploaded additional files in this same chat session. "
            "Use the extracted attachment context below when relevant.\n\n"
            f"{attachment_context}\n---"
        )

    lc_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=system_content)
    ]
    # Include prior conversation history (last 20 turns)
    for msg in existing[-20:]:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        else:
            lc_messages.append(AIMessage(content=msg.content))
    lc_messages.append(HumanMessage(content=multimodal_user_text))

    user_message_row = await save_chat_message(db, current_user.id, thread_id, "user", body.message)
    if attachment_ids and session_id is not None:
        linked = await attachment_service.attach_uploaded_files_to_message(
            db,
            user_id=current_user.id,
            session_id=session_id,
            message_id=user_message_row.id,
            attachment_ids=attachment_ids,
        )
        base_url = str(request.base_url).rstrip("/")
        previews = [
            _render_attachment_markdown(
                base_url=base_url,
                file_url=attachment_service.to_response(item).file_url,
                original_name=item.original_name,
                attachment_type=item.attachment_type,
            )
            for item in linked
        ]
        user_message_row.content = _message_with_attachment_previews(
            message_text=body.message,
            previews=previews,
        )
        await db.commit()

    async def event_stream() -> AsyncGenerator[str, None]:
        full_response: list[str] = []
        try:
            config = {"metadata": {"user_email": current_user.email}}
            async for chunk in llm.astream(lc_messages, config=config):
                content = getattr(chunk, "content", "")
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    )
                if content:
                    full_response.append(str(content))
                    yield f"data: {json.dumps({'type': 'token', 'content': str(content)})}\n\n"

            assembled = "".join(full_response)
            await save_chat_message(db, current_user.id, thread_id, "assistant", assembled)
            await touch_thread(db, thread)

            if is_first and thread.title in ("New Chat", ""):
                try:
                    new_title = await generate_thread_title(body.message, current_user.email)
                    renamed = await rename_thread(db, thread_id, current_user.id, new_title)
                    if renamed:
                        yield f"data: {json.dumps({'type': 'thread_renamed', 'content': renamed.title})}\n\n"
                except Exception:
                    pass

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
