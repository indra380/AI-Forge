import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatHistoryItem,
    ChatRequest,
    ThreadCreate,
    ThreadResponse,
    ThreadUpdate,
)
from app.services.auth_service import get_current_user
from app.services.chat_service import (
    generate_thread_title,
    list_chat_messages,
    save_chat_message,
    stream_chat_response,
)
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
# Streaming chat
# ---------------------------------------------------------------------------

@router.post("/threads/{thread_id}/stream")
async def stream_thread(
    thread_id: uuid.UUID,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    thread = await get_thread(db, thread_id, current_user.id)
    if thread is None:
        raise HTTPException(
            status_code=404, detail={"error": "not_found", "message": "Thread not found"}
        )

    # Determine whether this is the first message (triggers auto-naming)
    existing = await list_chat_messages(db, current_user.id, thread_id)
    is_first = len(existing) == 0

    await save_chat_message(db, current_user.id, thread_id, "user", body.message)

    async def event_stream() -> AsyncGenerator[str, None]:
        full_response: list[str] = []
        try:
            async for token in stream_chat_response(body.message, current_user.email):
                full_response.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            assembled = "".join(full_response)
            await save_chat_message(db, current_user.id, thread_id, "assistant", assembled)
            await touch_thread(db, thread)

            # Auto-name thread on first message
            if is_first and thread.title in ("New Chat", ""):
                try:
                    new_title = await generate_thread_title(body.message, current_user.email)
                    renamed = await rename_thread(db, thread_id, current_user.id, new_title)
                    if renamed:
                        yield f"data: {json.dumps({'type': 'thread_renamed', 'content': renamed.title})}\n\n"
                except Exception:
                    pass  # Title generation failure must never break the chat response

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
