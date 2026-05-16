"""Image rule validation service.

Uses the multimodal vision LLM to extract structured data from images,
then applies the rule engine to produce a validation report.
"""
import base64
import json
import re
from pathlib import Path
from typing import Any, Optional

from openai import OpenAIError

from app.ai.llm import openai_client
from app.core.config import settings
from app.models.image_rule import ImageRule
from app.services.rule_engine_service import apply_rules_to_extracted


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------

def _encode_image_base64(file_path: str) -> tuple[str, str]:
    """Return (base64_data, mime_type) for an image file."""
    path = Path(file_path)
    suffix = path.suffix.lower().lstrip(".")
    mime_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    mime = mime_map.get(suffix, "image/png")
    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return data, mime


# ---------------------------------------------------------------------------
# Vision extraction
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """You are a data extraction assistant. Analyze the provided image carefully.

Extract ALL relevant information from the image as a flat JSON object. Include:
- Any text found (amounts, IDs, names, dates, labels)
- Detected objects or elements (logo, signature, seal, etc.) as boolean flags
- Numeric values parsed as numbers
- Dates in ISO format

Return ONLY valid JSON. Example:
{{"amount": 4500.00, "invoice_number": "INV-2024-001", "has_logo": true, "date": "2024-01-15", "vendor": "Acme Corp"}}
"""


async def extract_from_image(
    file_path: str,
    user_email: str,
    extraction_hint: Optional[str] = None,
) -> dict[str, Any]:
    """Use vision model to extract structured data from an image.

    Returns a dict of extracted fields.
    """
    try:
        img_data, mime_type = _encode_image_base64(file_path)
    except Exception as exc:
        return {"_error": f"Could not read image: {exc}"}

    prompt = _EXTRACTION_PROMPT
    if extraction_hint:
        prompt += f"\n\nPay special attention to: {extraction_hint}"

    try:
        response = openai_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{img_data}"},
                        },
                    ],
                }
            ],
            max_tokens=1000,
            user=user_email,
            extra_body={
                "metadata": {
                    "application": settings.APP_NAME,
                    "environment": settings.ENVIRONMENT,
                }
            },
        )
        raw = response.choices[0].message.content or "{}"
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw_text": raw}
    except OpenAIError as exc:
        return {"_error": str(exc)}
    except Exception as exc:
        return {"_error": str(exc)}


# ---------------------------------------------------------------------------
# Full validation pipeline
# ---------------------------------------------------------------------------

async def validate_image(
    file_path: str,
    rule: ImageRule,
    user_email: str,
    extraction_hint: Optional[str] = None,
) -> dict[str, Any]:
    """Extract data from image and validate against rule set.

    Returns:
        {
            "rule_name": str,
            "extracted": dict,
            "results": [{"rule": str, "field": str, "extracted": any, "passed": bool}, ...],
            "passed": bool,
            "violation_count": int,
            "summary": str,
        }
    """
    extracted = await extract_from_image(file_path, user_email, extraction_hint)

    if "_error" in extracted:
        return {
            "rule_name": rule.name,
            "extracted": {},
            "results": [],
            "passed": False,
            "violation_count": 0,
            "summary": f"Extraction failed: {extracted['_error']}",
        }

    results = apply_rules_to_extracted(extracted, rule.rules)
    violations = [r for r in results if not r["passed"]]
    passed = len(violations) == 0

    summary_parts = []
    if passed:
        summary_parts.append(f"✅ All {len(results)} rule(s) passed.")
    else:
        summary_parts.append(f"❌ {len(violations)} of {len(results)} rule(s) failed.")
        for v in violations:
            summary_parts.append(f"  - **{v['rule']}**: extracted `{v['extracted']}`, expected {v['operator']} `{v['expected']}`")

    return {
        "rule_name": rule.name,
        "extracted": extracted,
        "results": results,
        "passed": passed,
        "violation_count": len(violations),
        "summary": "\n".join(summary_parts),
    }


async def validate_image_freeform(
    file_path: str,
    custom_rules_text: str,
    user_email: str,
) -> dict[str, Any]:
    """Validate an image against free-form rule text using LLM reasoning.

    Used when the user types validation instructions in chat directly.
    """
    try:
        img_data, mime_type = _encode_image_base64(file_path)
    except Exception as exc:
        return {"summary": f"Could not read image: {exc}", "passed": False}

    prompt = f"""You are an image validation expert. Analyze the provided image and validate it against these rules:

{custom_rules_text}

For each rule:
1. Examine whether the image satisfies the rule
2. Extract any relevant values from the image
3. Determine PASS or FAIL

Respond with a JSON object:
{{
  "results": [
    {{"rule": "rule description", "extracted": "what you found", "passed": true/false, "reason": "explanation"}}
  ],
  "passed": true/false,
  "summary": "overall summary"
}}

Return ONLY valid JSON."""

    try:
        response = openai_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{img_data}"},
                        },
                    ],
                }
            ],
            max_tokens=1500,
            user=user_email,
            extra_body={
                "metadata": {
                    "application": settings.APP_NAME,
                    "environment": settings.ENVIRONMENT,
                }
            },
        )
        raw = response.choices[0].message.content or "{}"
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())
        data = json.loads(raw)
        return {
            "rule_name": "Custom Rules",
            "extracted": {},
            "results": data.get("results", []),
            "passed": data.get("passed", False),
            "violation_count": sum(1 for r in data.get("results", []) if not r.get("passed")),
            "summary": data.get("summary", ""),
        }
    except Exception as exc:
        return {
            "rule_name": "Custom Rules",
            "extracted": {},
            "results": [],
            "passed": False,
            "violation_count": 0,
            "summary": f"Validation failed: {exc}",
        }
