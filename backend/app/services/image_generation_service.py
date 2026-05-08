from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat_thread import ChatThread
from app.models.generated_image import GeneratedImage
from app.schemas.image import GeneratedImageResponse
from app.services.chat_service import save_chat_message
from app.services.image_generation_provider import (
    ImageGenerationOptions,
    get_image_provider,
)
from app.services.image_generation_storage import get_generated_image_storage

_ALLOWED_SIZES = {"1024x1024", "1024x1536", "1536x1024"}
_ALLOWED_STYLES = {"realistic", "anime", "digital-art", "cinematic"}
_MAX_PROMPT_LENGTH = 1000


@dataclass(slots=True)
class ImageGenerateResult:
    images: list[GeneratedImage]
    assistant_message: str


class PromptModerator:
    _blocked_patterns = [
        re.compile(r"\b(child\s*porn|csam|rape|bestiality)\b", re.IGNORECASE),
    ]

    @classmethod
    def validate(cls, prompt: str) -> None:
        if len(prompt.strip()) < 3:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_prompt", "message": "Prompt must be at least 3 characters"},
            )
        if len(prompt) > _MAX_PROMPT_LENGTH:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_prompt", "message": "Prompt exceeds maximum length"},
            )

        for pattern in cls._blocked_patterns:
            if pattern.search(prompt):
                raise HTTPException(
                    status_code=400,
                    detail={"error": "unsafe_prompt", "message": "Prompt violates safety policy"},
                )


class InMemoryImageRateLimiter:
    def __init__(self) -> None:
        self._window = timedelta(minutes=1)
        self._max_requests = settings.IMAGE_RATE_LIMIT_PER_MINUTE
        self._requests: dict[uuid.UUID, deque[datetime]] = defaultdict(deque)

    def check_or_raise(self, user_id: uuid.UUID) -> None:
        now = datetime.now(timezone.utc)
        bucket = self._requests[user_id]

        while bucket and (now - bucket[0]) > self._window:
            bucket.popleft()

        if len(bucket) >= self._max_requests:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "message": "Image generation rate limit exceeded. Try again in a minute.",
                },
            )

        bucket.append(now)


class ImageGenerationService:
    def __init__(self) -> None:
        self.provider = get_image_provider()
        self.storage = get_generated_image_storage()
        self.rate_limiter = InMemoryImageRateLimiter()

    async def generate(
        self,
        *,
        db: AsyncSession,
        user_id: uuid.UUID,
        user_email: str,
        prompt: str,
        size: str,
        style: str,
        image_count: int,
        session_id: uuid.UUID,
        thread_id: uuid.UUID | None,
        negative_prompt: str | None,
        seed: int | None,
    ) -> ImageGenerateResult:
        PromptModerator.validate(prompt)
        self._validate_generation_options(size=size, style=style)
        self.rate_limiter.check_or_raise(user_id)

        thread: ChatThread | None = None
        if thread_id is not None:
            thread = await self._load_user_thread(db=db, user_id=user_id, thread_id=thread_id)

        options = ImageGenerationOptions(
            prompt=prompt.strip(),
            size=size,
            style=style,
            negative_prompt=negative_prompt,
            seed=seed,
        )

        try:
            provider_images = await asyncio.wait_for(
                self.provider.generate_images(
                    options=options,
                    count=image_count,
                    user_email=user_email,
                ),
                timeout=settings.IMAGE_GENERATION_TIMEOUT,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail={"error": "generation_timeout", "message": "Image generation timed out"},
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail={"error": "provider_failure", "message": str(exc)},
            ) from exc

        assistant_message_text = f"Generated {len(provider_images)} image(s) for: {prompt.strip()}"

        message_id: uuid.UUID | None = None
        if thread is not None:
            await save_chat_message(db, user_id=user_id, thread_id=thread.id, role="user", content=prompt.strip())
            assistant_message = await save_chat_message(
                db,
                user_id=user_id,
                thread_id=thread.id,
                role="assistant",
                content=assistant_message_text,
            )
            message_id = assistant_message.id
            thread.updated_at = datetime.now(timezone.utc)

        generated_rows: list[GeneratedImage] = []
        for image in provider_images:
            stored = self.storage.save_png(session_id=session_id, image_bytes=image.image_bytes)
            row = GeneratedImage(
                user_id=user_id,
                thread_id=thread.id if thread is not None else None,
                message_id=message_id,
                session_id=session_id,
                prompt=prompt.strip(),
                negative_prompt=negative_prompt,
                provider=self.provider.provider_name,
                style=style,
                size=size,
                seed=seed,
                image_url=stored.image_url,
                storage_path=stored.storage_path,
            )
            db.add(row)
            generated_rows.append(row)

        await db.commit()

        for row in generated_rows:
            await db.refresh(row)

        return ImageGenerateResult(images=generated_rows, assistant_message=assistant_message_text)

    async def list_message_images(
        self,
        *,
        db: AsyncSession,
        message_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[GeneratedImageResponse]]:
        if not message_ids:
            return {}

        stmt = (
            select(GeneratedImage)
            .where(GeneratedImage.message_id.in_(message_ids))
            .order_by(GeneratedImage.created_at.asc())
        )
        rows = (await db.execute(stmt)).scalars().all()

        grouped: dict[uuid.UUID, list[GeneratedImageResponse]] = defaultdict(list)
        for row in rows:
            if row.message_id is None:
                continue
            grouped[row.message_id].append(self.to_response(row))
        return grouped

    def _validate_generation_options(self, *, size: str, style: str) -> None:
        if size not in _ALLOWED_SIZES:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_size",
                    "message": f"Unsupported size '{size}'. Use one of: {sorted(_ALLOWED_SIZES)}",
                },
            )
        if style not in _ALLOWED_STYLES:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_style",
                    "message": f"Unsupported style '{style}'. Use one of: {sorted(_ALLOWED_STYLES)}",
                },
            )

    async def _load_user_thread(
        self,
        *,
        db: AsyncSession,
        user_id: uuid.UUID,
        thread_id: uuid.UUID,
    ) -> ChatThread:
        stmt = select(ChatThread).where(ChatThread.id == thread_id, ChatThread.user_id == user_id)
        thread = (await db.execute(stmt)).scalar_one_or_none()
        if thread is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Thread not found"},
            )
        return thread

    def to_response(self, image: GeneratedImage) -> GeneratedImageResponse:
        return GeneratedImageResponse(
            image_id=image.id,
            session_id=image.session_id,
            prompt=image.prompt,
            provider=image.provider,
            style=image.style,
            size=image.size,
            image_url=image.image_url,
            created_at=image.created_at,
        )


_service_instance: ImageGenerationService | None = None


def get_image_generation_service() -> ImageGenerationService:
    global _service_instance
    if _service_instance is None:
        _service_instance = ImageGenerationService()
    return _service_instance
