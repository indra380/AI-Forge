from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import uuid

from fastapi import UploadFile

from app.core.config import settings


@dataclass(slots=True)
class StoredAttachment:
    file_name: str
    storage_path: str
    file_url: str
    file_size: int


class AttachmentStorage:
    async def save(self, upload: UploadFile, category: str, safe_stem: str) -> StoredAttachment:
        raise NotImplementedError


class LocalAttachmentStorage(AttachmentStorage):
    def __init__(self, base_path: str):
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    async def save(self, upload: UploadFile, category: str, safe_stem: str) -> StoredAttachment:
        target_dir = self._base_path / category
        target_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(upload.filename or "").suffix.lower()
        file_name = f"{safe_stem}-{uuid.uuid4().hex}{suffix}"
        target_path = target_dir / file_name

        size = 0
        with target_path.open("wb") as destination:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                destination.write(chunk)

        await upload.seek(0)

        relative = target_path.relative_to(self._base_path).as_posix()
        return StoredAttachment(
            file_name=file_name,
            storage_path=str(target_path),
            file_url=f"/uploads/{relative}",
            file_size=size,
        )


class S3AttachmentStorage(AttachmentStorage):
    async def save(self, upload: UploadFile, category: str, safe_stem: str) -> StoredAttachment:
        raise NotImplementedError("S3 upload storage is not configured yet")


def get_attachment_storage() -> AttachmentStorage:
    if settings.UPLOAD_STORAGE == "local":
        return LocalAttachmentStorage(settings.UPLOAD_PATH)
    if settings.UPLOAD_STORAGE == "s3":
        return S3AttachmentStorage()
    raise RuntimeError(f"Unsupported upload storage backend: {settings.UPLOAD_STORAGE}")


def ensure_upload_directories() -> None:
    base = Path(settings.UPLOAD_PATH)
    base.mkdir(parents=True, exist_ok=True)
    for child in ("images", "videos", "tables", "documents", "code", "formulas"):
        (base / child).mkdir(parents=True, exist_ok=True)
