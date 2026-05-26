import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.generated_image import GeneratedImage
from app.models.user import User
from app.schemas.image import ImageGenerateRequest, ImageGenerateResponse
from app.services.auth_service import get_current_user
from app.services.image_generation_service import (
    ImageGenerationService,
    get_image_generation_service,
)

router = APIRouter(prefix="/image", tags=["image"])


@router.post("/generate", response_model=ImageGenerateResponse)
async def generate_image(
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


@router.get("/{image_id}/download")
async def download_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    stmt = select(GeneratedImage).where(
        GeneratedImage.id == image_id,
        GeneratedImage.user_id == current_user.id,
    )
    image = (await db.execute(stmt)).scalar_one_or_none()
    if image is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Generated image not found"},
        )

    image_path = Path(settings.IMAGE_OUTPUT_PATH) / image.storage_path
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"error": "file_missing", "message": "Image file is no longer available"},
        )

    return FileResponse(
        path=str(image_path),
        media_type="image/png",
        filename=f"generated-{image.id}.png",
    )
