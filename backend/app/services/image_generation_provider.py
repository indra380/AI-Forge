from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass

import httpx
from openai import OpenAIError

from app.ai.llm import openai_client
from app.core.config import settings


@dataclass(slots=True)
class ImageGenerationOptions:
    prompt: str
    size: str
    style: str
    negative_prompt: str | None = None
    seed: int | None = None


@dataclass(slots=True)
class ProviderImageResult:
    image_bytes: bytes
    mime_type: str = "image/png"


class ImageProvider:
    provider_name: str

    async def generate_images(
        self,
        *,
        options: ImageGenerationOptions,
        count: int,
        user_email: str,
    ) -> list[ProviderImageResult]:
        raise NotImplementedError


class OpenAIImageProvider(ImageProvider):
    provider_name = "openai"

    async def generate_images(
        self,
        *,
        options: ImageGenerationOptions,
        count: int,
        user_email: str,
    ) -> list[ProviderImageResult]:
        def _call_provider() -> list[ProviderImageResult]:
            payload_prompt = options.prompt
            if options.style.lower() != "realistic":
                payload_prompt = f"Style: {options.style}. {payload_prompt}"
            if options.negative_prompt:
                payload_prompt = f"{payload_prompt}\n\nAvoid: {options.negative_prompt}"

            response = openai_client.images.generate(
                model=settings.IMAGE_GEN_MODEL,
                prompt=payload_prompt,
                size=options.size,
                n=count,
                response_format="b64_json",
                user=user_email,
                extra_body={
                    "metadata": {
                        "application": settings.APP_NAME,
                        "environment": settings.ENVIRONMENT,
                        "user_email": user_email,
                    }
                },
            )

            results: list[ProviderImageResult] = []
            for item in response.data:
                b64_payload = getattr(item, "b64_json", None)
                if b64_payload:
                    results.append(
                        ProviderImageResult(image_bytes=base64.b64decode(b64_payload), mime_type="image/png")
                    )
                    continue

                source_url = getattr(item, "url", None)
                if source_url:
                    downloaded = httpx.get(source_url, timeout=30.0)
                    downloaded.raise_for_status()
                    results.append(ProviderImageResult(image_bytes=downloaded.content, mime_type="image/png"))
                    continue

                raise RuntimeError("Image provider returned empty image payload")

            return results

        try:
            return await asyncio.to_thread(_call_provider)
        except OpenAIError as exc:
            raise RuntimeError(f"Image provider request failed: {exc}") from exc


class UnsupportedImageProvider(ImageProvider):
    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    async def generate_images(
        self,
        *,
        options: ImageGenerationOptions,
        count: int,
        user_email: str,
    ) -> list[ProviderImageResult]:
        raise RuntimeError(
            "Selected image provider is not implemented yet. "
            "Supported currently: openai. Planned: stability, replicate, bedrock, local"
        )


_provider_instance: ImageProvider | None = None


def get_image_provider() -> ImageProvider:
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    provider = settings.IMAGE_PROVIDER.lower()
    if provider == "openai":
        _provider_instance = OpenAIImageProvider()
    else:
        _provider_instance = UnsupportedImageProvider(provider_name=provider)
    return _provider_instance
