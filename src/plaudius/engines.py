"""Engine interfaces: a pipeline engine is a (Transcriber, Summarizer) pair.

New engines register a factory in ENGINE_FACTORIES; nothing else changes.
(A "local" engine was planned but dropped for now -- this host has no GPU.)
"""
from typing import Protocol

from pydantic import BaseModel

from .config import Settings


class Transcript(BaseModel):
    text: str  # paragraph-formatted: blank line between paragraphs
    duration_seconds: float


class BriefData(BaseModel):
    thesis: str
    key_points: list[str]
    actions: list[str]
    open_questions: list[str]
    tags: list[str]


class Transcriber(Protocol):
    def transcribe(self, audio: bytes) -> Transcript: ...


class Summarizer(Protocol):
    def summarize(self, transcript_text: str) -> BriefData: ...


def _hosted(settings: Settings) -> tuple[Transcriber, Summarizer]:
    from .hosted import AnthropicSummarizer, DeepgramTranscriber

    return DeepgramTranscriber(settings), AnthropicSummarizer(settings)


ENGINE_FACTORIES = {"hosted": _hosted}
