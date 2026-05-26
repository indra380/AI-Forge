from __future__ import annotations

import re


class CodeAnalysisService:
    _keywords = {
        "code",
        "bug",
        "debug",
        "refactor",
        "optimize",
        "architecture",
        "stack trace",
        "exception",
    }

    def should_focus_code_analysis(self, prompt: str) -> bool:
        lowered = prompt.lower()
        return any(keyword in lowered for keyword in self._keywords) or bool(
            re.search(r"```[a-zA-Z0-9_+-]*", prompt)
        )


_singleton: CodeAnalysisService | None = None


def get_code_analysis_service() -> CodeAnalysisService:
    global _singleton
    if _singleton is None:
        _singleton = CodeAnalysisService()
    return _singleton
