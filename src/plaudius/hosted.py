"""Hosted engine: Deepgram Nova-3 transcription + Anthropic brief generation."""
import logging

import anthropic
import httpx

from .config import Settings
from .engines import BriefData, Transcript

log = logging.getLogger("plaudius.hosted")

_DG_URL = "https://api.deepgram.com/v1/listen"
_DG_PARAMS = {
    "model": "nova-3",
    "smart_format": "true",
    "paragraphs": "true",
    "punctuate": "true",
}

# claude-haiku-4-5 has a 200K-token context window; ~400K chars stays well inside it.
_MAX_TRANSCRIPT_CHARS = 400_000

_SYSTEM = """You turn raw voice-memo transcripts into structured briefs.
Extract:
- thesis: ONE sentence capturing the memo's central point.
- key_points: the essential points, each concise; no filler, no restating the thesis.
- actions: concrete to-dos the speaker stated or clearly implied (empty if none).
- open_questions: unresolved questions the speaker raised (empty if none).
- tags: 2-5 short lowercase topic tags for filing (e.g. "planning", "health").
Write in the speaker's language. Be faithful to the memo; do not invent content."""


class DeepgramTranscriber:
    def __init__(self, settings: Settings):
        self._key = settings.deepgram_api_key

    def transcribe(self, audio: bytes) -> Transcript:
        if not self._key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        resp = httpx.post(
            _DG_URL,
            params=_DG_PARAMS,
            content=audio,
            headers={
                "Authorization": f"Token {self._key}",
                "Content-Type": "application/octet-stream",
            },
            timeout=httpx.Timeout(600, connect=15),
        )
        resp.raise_for_status()
        data = resp.json()
        alt = data["results"]["channels"][0]["alternatives"][0]
        # paragraphs=true puts the paragraph-formatted text in a nested field;
        # the top-level `transcript` has no paragraph breaks.
        text = ((alt.get("paragraphs") or {}).get("transcript") or alt.get("transcript") or "").strip()
        if not text:
            raise ValueError("Deepgram returned an empty transcript (silent or unreadable audio?)")
        duration = float(data.get("metadata", {}).get("duration") or 0.0)
        return Transcript(text=text, duration_seconds=duration)


class AnthropicSummarizer:
    def __init__(self, settings: Settings):
        self._api_key = settings.anthropic_api_key
        self._model = settings.anthropic_model

    def summarize(self, transcript_text: str) -> BriefData:
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        if len(transcript_text) > _MAX_TRANSCRIPT_CHARS:
            log.warning("transcript truncated for summarisation (%d chars)", len(transcript_text))
            transcript_text = transcript_text[:_MAX_TRANSCRIPT_CHARS] + "\n\n[transcript truncated]"
        # max_retries=0: the worker's retry-once wrapper governs retries.
        client = anthropic.Anthropic(api_key=self._api_key, max_retries=0)
        response = client.messages.parse(
            model=self._model,
            max_tokens=4000,
            system=_SYSTEM,
            messages=[
                {"role": "user", "content": f"<transcript>\n{transcript_text}\n</transcript>"}
            ],
            output_format=BriefData,
        )
        brief = response.parsed_output
        if brief is None or not brief.thesis.strip():
            raise ValueError("model returned no usable brief")
        return brief
