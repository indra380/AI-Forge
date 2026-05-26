from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import settings


@dataclass(slots=True)
class StoredGeneratedImage:
    file_name: str
    storage_path: str
    image_url: str


class GeneratedImageStorage:
    def save_png(self, *, session_id: UUID, image_bytes: bytes) -> StoredGeneratedImage:
        raise NotImplementedError


class LocalGeneratedImageStorage(GeneratedImageStorage):
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def save_png(self, *, session_id: UUID, image_bytes: bytes) -> StoredGeneratedImage:
        session_dir = self.base_dir / str(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        file_name = f"generated-{uuid4().hex}.png"
        abs_path = session_dir / file_name
        abs_path.write_bytes(image_bytes)

        relative_path = Path(str(session_id)) / file_name
        image_url = f"/generated/{relative_path.as_posix()}"
        return StoredGeneratedImage(
            file_name=file_name,
            storage_path=relative_path.as_posix(),
            image_url=image_url,
        )


class CloudGeneratedImageStorage(GeneratedImageStorage):
    def save_png(self, *, session_id: UUID, image_bytes: bytes) -> StoredGeneratedImage:
        raise NotImplementedError("Cloud generated-image storage is not implemented yet")


_storage_instance: GeneratedImageStorage | None = None


def get_generated_image_storage() -> GeneratedImageStorage:
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    if settings.IMAGE_STORAGE.lower() == "local":
        _storage_instance = LocalGeneratedImageStorage(Path(settings.IMAGE_OUTPUT_PATH))
    else:
        _storage_instance = CloudGeneratedImageStorage()
    return _storage_instance


def ensure_generated_image_directories() -> None:
    if settings.IMAGE_STORAGE.lower() != "local":
        return
    Path(settings.IMAGE_OUTPUT_PATH).mkdir(parents=True, exist_ok=True)
