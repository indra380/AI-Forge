"""Dataset store with disk-backed persistence.

Datasets are cached in memory for speed and persisted on disk so they survive
uvicorn hot-reload and process restarts.

Per-user isolation: every entry keeps the owning user_id so query endpoints
can reject cross-user access.
"""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from app.core.config import settings


@dataclass
class StoredDataset:
    dataset_id: str
    user_id: str
    filename: str
    frames: Dict[str, pd.DataFrame]          # {sheet_name: DataFrame}
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_url: Optional[str] = None          # set for Google Sheet datasets


class DatasetStore:
    """Thread-safe dataset store with memory + disk persistence."""

    def __init__(self) -> None:
        self._store: Dict[str, StoredDataset] = {}
        self._lock = threading.Lock()
        self._cache_root = Path(settings.UPLOAD_PATH) / "dataset_cache"
        self._cache_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(
        self,
        *,
        user_id: str,
        filename: str,
        frames: Dict[str, pd.DataFrame],
        source_url: Optional[str] = None,
    ) -> StoredDataset:
        dataset_id = str(uuid.uuid4())
        entry = StoredDataset(
            dataset_id=dataset_id,
            user_id=user_id,
            filename=filename,
            frames=frames,
            source_url=source_url,
        )
        with self._lock:
            self._store[dataset_id] = entry
        self._persist_to_disk(entry)
        return entry

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, dataset_id: str, user_id: str) -> Optional[StoredDataset]:
        """Return the dataset if it exists and belongs to *user_id*."""
        with self._lock:
            entry = self._store.get(dataset_id)
        if entry is None:
            entry = self._load_from_disk(dataset_id)
            if entry is not None:
                with self._lock:
                    self._store[dataset_id] = entry
        if entry is None or entry.user_id != user_id:
            return None
        return entry

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, dataset_id: str, user_id: str) -> bool:
        # Ensure we can delete entries that only exist on disk after reload.
        entry = self.get(dataset_id, user_id)
        if entry is None:
            return False

        with self._lock:
            self._store.pop(dataset_id, None)

        cache_dir = self._entry_dir(dataset_id)
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        return True

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_for_user(self, user_id: str) -> list[StoredDataset]:
        # Start with in-memory entries.
        with self._lock:
            result = [e for e in self._store.values() if e.user_id == user_id]
            seen = {e.dataset_id for e in result}

        # Merge disk entries that are not yet loaded in-memory.
        for cache_dir in self._cache_root.iterdir():
            if not cache_dir.is_dir():
                continue
            dataset_id = cache_dir.name
            if dataset_id in seen:
                continue
            entry = self._load_from_disk(dataset_id)
            if entry is None or entry.user_id != user_id:
                continue
            with self._lock:
                self._store[dataset_id] = entry
            result.append(entry)
            seen.add(dataset_id)

        # Most recent first.
        result.sort(key=lambda e: e.created_at, reverse=True)
        return result

    # ------------------------------------------------------------------
    # Disk persistence helpers
    # ------------------------------------------------------------------

    def _entry_dir(self, dataset_id: str) -> Path:
        return self._cache_root / dataset_id

    def _persist_to_disk(self, entry: StoredDataset) -> None:
        cache_dir = self._entry_dir(entry.dataset_id)
        cache_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "dataset_id": entry.dataset_id,
            "user_id": entry.user_id,
            "filename": entry.filename,
            "created_at": entry.created_at.isoformat(),
            "source_url": entry.source_url,
        }
        (cache_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        pd.to_pickle(entry.frames, cache_dir / "frames.pkl")

    def _load_from_disk(self, dataset_id: str) -> Optional[StoredDataset]:
        cache_dir = self._entry_dir(dataset_id)
        meta_path = cache_dir / "metadata.json"
        frames_path = cache_dir / "frames.pkl"
        if not meta_path.exists() or not frames_path.exists():
            return None

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            frames = pd.read_pickle(frames_path)
            if not isinstance(frames, dict):
                return None
            created_at = datetime.fromisoformat(meta["created_at"])
            return StoredDataset(
                dataset_id=meta["dataset_id"],
                user_id=meta["user_id"],
                filename=meta["filename"],
                frames=frames,
                created_at=created_at,
                source_url=meta.get("source_url"),
            )
        except Exception:
            return None


# Module-level singleton – import and use directly
dataset_store = DatasetStore()
