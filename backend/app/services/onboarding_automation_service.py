from __future__ import annotations

import uuid

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def trigger_user_onboarding_webhook(
    *,
    user_id: uuid.UUID,
    email: str,
    source: str,
) -> bool:
    """Trigger n8n onboarding webhook; fail-open so auth flow is never blocked."""
    if not settings.N8N_ONBOARDING_ENABLED:
        return False

    url = (settings.N8N_ONBOARDING_WEBHOOK_URL or "").strip()
    if not url:
        logger.info("[ONBOARDING_AUTOMATION] skipped reason=missing_webhook_url user_id=%s", user_id)
        return False

    auth_user = (settings.N8N_WEBHOOK_USER or "").strip()
    auth_password = settings.N8N_WEBHOOK_PASSWORD or ""
    auth: tuple[str, str] | None = None
    if auth_user and auth_password:
        auth = (auth_user, auth_password)

    payload = {
        "user_id": str(user_id),
        "email": email,
        "source": source,
    }

    try:
        timeout_s = max(1, int(settings.N8N_WEBHOOK_TIMEOUT_SECONDS))
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(url, json=payload, auth=auth)
            response.raise_for_status()
        logger.info(
            "[ONBOARDING_AUTOMATION] webhook_success user_id=%s source=%s",
            user_id,
            source,
        )
        return True
    except Exception as exc:
        logger.warning(
            "[ONBOARDING_AUTOMATION] webhook_failed user_id=%s source=%s error=%s",
            user_id,
            source,
            exc,
        )
        return False
