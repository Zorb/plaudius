"""ntfy pushes. JSON publish mode (UTF-8-safe titles); failures log, never raise."""
import logging
from urllib.parse import quote

import httpx

from .config import Settings

log = logging.getLogger("plaudius.notify")


def obsidian_uri(vault: str, file_in_vault: str) -> str:
    """obsidian://open URI; params percent-encoded ourselves (ntfy passes Click through untouched)."""
    return f"obsidian://open?vault={quote(vault, safe='')}&file={quote(file_in_vault, safe='')}"


def push(
    settings: Settings,
    *,
    title: str,
    message: str,
    click: str | None = None,
    tags: list[str] | None = None,
) -> None:
    if not settings.ntfy_url or not settings.ntfy_topic:
        log.info("ntfy not configured; skipping push (%s)", title)
        return
    payload: dict = {"topic": settings.ntfy_topic, "title": title, "message": message}
    if click:
        payload["click"] = click
    if tags:
        payload["tags"] = tags
    headers = {}
    if settings.ntfy_token:
        headers["Authorization"] = f"Bearer {settings.ntfy_token}"
    try:
        httpx.post(settings.ntfy_url, json=payload, headers=headers, timeout=15).raise_for_status()
    except Exception:
        log.exception("ntfy push failed (%s)", title)
