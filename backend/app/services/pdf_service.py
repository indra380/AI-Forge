from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import fitz

from app.core.config import settings


@dataclass(slots=True)
class PdfPageText:
    page_number: int
    text: str


@dataclass(slots=True)
class PdfChunk:
    text: str
    page_number: int
    chunk_index: int


class PdfService:
    def extract_pages(self, path: Path) -> list[PdfPageText]:
        document = fitz.open(path)
        pages: list[PdfPageText] = []
        try:
            for page_index in range(len(document)):
                page = document.load_page(page_index)
                text = page.get_text("text") or ""
                cleaned = re.sub(r"\n{3,}", "\n\n", text).strip()
                if cleaned:
                    pages.append(PdfPageText(page_number=page_index + 1, text=cleaned))
        finally:
            document.close()
        return pages

    def chunk_pages(self, pages: list[PdfPageText]) -> list[PdfChunk]:
        chunk_size = max(200, settings.CHUNK_SIZE)
        overlap = max(0, min(settings.CHUNK_OVERLAP, chunk_size - 50))

        chunks: list[PdfChunk] = []
        chunk_index = 0
        for page in pages:
            blocks = [block.strip() for block in page.text.split("\n\n") if block.strip()]
            page_text = "\n\n".join(blocks)
            if not page_text:
                continue

            start = 0
            while start < len(page_text):
                end = min(len(page_text), start + chunk_size)
                piece = page_text[start:end].strip()
                if piece:
                    chunks.append(
                        PdfChunk(
                            text=piece,
                            page_number=page.page_number,
                            chunk_index=chunk_index,
                        )
                    )
                    chunk_index += 1
                if end >= len(page_text):
                    break
                start = max(0, end - overlap)
        return chunks


_pdf_service_singleton: PdfService | None = None


def get_pdf_service() -> PdfService:
    global _pdf_service_singleton
    if _pdf_service_singleton is None:
        _pdf_service_singleton = PdfService()
    return _pdf_service_singleton
