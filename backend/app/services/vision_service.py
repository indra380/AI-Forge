from __future__ import annotations


class VisionService:
    def build_vision_guidance(self) -> str:
        return (
            "When image/video attachments are present, describe visible content first, "
            "then infer structure, labels, and potential issues. If uncertainty exists, "
            "state assumptions explicitly."
        )


_singleton: VisionService | None = None


def get_vision_service() -> VisionService:
    global _singleton
    if _singleton is None:
        _singleton = VisionService()
    return _singleton
