import re
from datetime import datetime

from plaudius.brief import note_filename, render_brief, slugify, write_note
from plaudius.engines import BriefData, Transcript

NOW = datetime(2026, 8, 23, 14, 32)


def make_brief(**overrides) -> BriefData:
    base = dict(
        thesis="The pipeline is ready for daily use",
        key_points=["Transcription quality is strong", "Notes land within a minute"],
        actions=["Set up the iPhone Shortcut"],
        open_questions=["Tag by project or by topic?"],
        tags=["Planning", "plaudius"],
    )
    return BriefData(**{**base, **overrides})


TRANSCRIPT = Transcript(text="First paragraph.\n\nSecond paragraph.", duration_seconds=42.6)


def test_slugify_basic():
    assert slugify("Hello, World! 123") == "hello-world-123"


def test_slugify_fallback():
    assert slugify("???") == "memo"
    assert slugify("") == "memo"


def test_slugify_truncates_on_word_boundary():
    slug = slugify("word " * 40)
    assert len(slug) <= 60
    assert not slug.endswith("-")


def test_note_filename_format():
    assert note_filename("My Great Idea!", NOW) == "2026-08-23 1432 - my-great-idea.md"


def test_render_sections_in_order():
    text = render_brief(make_brief(), TRANSCRIPT, "hosted", NOW)
    headings = ["## Thesis", "## Key Points", "## Actions", "## Open Questions", "## Transcript"]
    positions = [text.index(h) for h in headings]
    assert positions == sorted(positions)
    assert "Second paragraph." in text


def test_render_frontmatter():
    text = render_brief(make_brief(), TRANSCRIPT, "hosted", NOW)
    head = text.split("---")[1]
    assert "date: 2026-08-23T14:32" in head
    assert "duration_seconds: 43" in head  # round(42.6)
    assert "engine: hosted" in head
    assert "  - planning" in head  # lowercased tag
    assert "  - plaudius" in head


def test_render_empty_lists():
    text = render_brief(make_brief(actions=[], open_questions=[], tags=[]), TRANSCRIPT, "x", NOW)
    assert "## Actions\n\n_None._" in text
    assert "## Open Questions\n\n_None._" in text
    assert "tags: []" in text


def test_render_sanitises_tags():
    text = render_brief(make_brief(tags=["Deep Work!", "deep-work"]), TRANSCRIPT, "x", NOW)
    assert text.count("  - deep-work") == 1  # sanitised + deduped


def test_write_note_collision(tmp_path):
    first = write_note(tmp_path, "2026-08-23 1432 - idea.md", "one")
    second = write_note(tmp_path, "2026-08-23 1432 - idea.md", "two")
    assert first.name == "2026-08-23 1432 - idea.md"
    assert second.name == "2026-08-23 1432 - idea 2.md"
    assert second.read_text() == "two"


def test_filename_matches_expected_pattern():
    name = note_filename("Anything at all", NOW)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{4} - [a-z0-9-]+\.md", name)
