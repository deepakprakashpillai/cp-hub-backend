"""Transactional email boundary. Local development never sends external mail."""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_password_setup_email(email: str, token: str) -> None:
    await _send_password_link(email, token, "set-password", "Set up your CP Hub password")


async def send_password_reset_email(email: str, token: str) -> None:
    await _send_password_link(email, token, "reset-password", "Reset your CP Hub password")


async def _send_password_link(email: str, token: str, page: str, subject: str) -> None:
    url = f"{settings.frontend_base_url.rstrip('/')}/{page}?token={token}"
    if not settings.resend_api_key or not settings.resend_from_email:
        logger.info("Password setup link for %s: %s", email, url)
        return
    import httpx

    response = await httpx.AsyncClient().post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json={
            "from": settings.resend_from_email,
            "to": [email],
            "subject": subject,
            "html": f'<p><a href="{url}">{subject}</a></p>',
        },
        timeout=10,
    )
    response.raise_for_status()
