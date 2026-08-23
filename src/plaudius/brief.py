"""Render the brief markdown and write it into the vault."""
import re
from datetime import datetime
from pathlib import Path

from .engines import BriefData, Transcript


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0] or slug[:max_len]
    return slug or "memo"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item.strip()}" for item in items if item.strip()) or "_None._"


def render_brief(brief: BriefData, transcript: Transcript, engine: str, now: datetime) -> str:
    tags = sorted({re.sub(r"[^a-z0-9-]+", "-", t.strip().lower()).strip("-") for t in brief.tags})
    tags = [t for t in tags if t]
    tag_block = "tags:\n" + "\n".join(f"  - {t}" for t in tags) if tags else "tags: []"
    frontmatter = "\n".join(
        [
            "---",
            f"date: {now.strftime('%Y-%m-%dT%H:%M')}",
            f"duration_seconds: {round(transcript.duration_seconds)}",
            f"engine: {engine}",
            tag_block,
            "---",
        ]
    )
    return (
        f"{frontmatter}\n\n"
        f"## Thesis\n\n{brief.thesis.strip()}\n\n"
        f"## Key Points\n\n{_bullets(brief.key_points)}\n\n"
        f"## Actions\n\n{_bullets(brief.actions)}\n\n"
        f"## Open Questions\n\n{_bullets(brief.open_questions)}\n\n"
        f"## Transcript\n\n{transcript.text.strip()}\n"
    )


def note_filename(thesis: str, now: datetime) -> str:
    return f"{now.strftime('%Y-%m-%d %H%M')} - {slugify(thesis)}.md"


def write_note(vault_dir: Path, filename: str, content: str) -> Path:
    vault_dir.mkdir(parents=True, exist_ok=True)
    path, n = vault_dir / filename, 2
    while path.exists():
        path = vault_dir / f"{filename.removesuffix('.md')} {n}.md"
        n += 1
    path.write_text(content, encoding="utf-8")
    return path
