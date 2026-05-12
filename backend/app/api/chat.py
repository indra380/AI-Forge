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
from app.services.thread_service import (
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    rename_thread,
    touch_thread,
)

router = APIRouter(prefix="/chat", tags=["chat"])

# ---------------------------------------------------------------------------
# Helpers
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

    attachment_context = ""
    multimodal_user_text: str | list[dict[str, object]] = user_text
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
