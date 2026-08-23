import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plaudius import engines
from plaudius.app import create_app
from plaudius.config import Settings
from plaudius.engines import BriefData, Transcript

AUTH = {"Authorization": "Bearer sekrit"}


class FakeTranscriber:
    def transcribe(self, audio: bytes) -> Transcript:
        return Transcript(text="First paragraph.\n\nSecond paragraph.", duration_seconds=42.5)


class FakeSummarizer:
    def summarize(self, transcript_text: str) -> BriefData:
        return BriefData(
            thesis="Testing the pipeline end to end",
            key_points=["it works"],
            actions=[],
            open_questions=[],
            tags=["test"],
        )


class ExplodingSummarizer:
    def summarize(self, transcript_text: str) -> BriefData:
        raise RuntimeError("api down")


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        token="sekrit",
        deepgram_api_key="",
        anthropic_api_key="",
        anthropic_model="claude-haiku-4-5",
        ntfy_url="",
        ntfy_topic="",
        ntfy_token="",
        obsidian_vault="vault",
        vault_dir=tmp_path / "vault" / "briefs",
        data_dir=tmp_path / "data",
        host="127.0.0.1",
        port=0,
        max_upload_bytes=1024,
    )


@pytest.fixture()
def client(settings, monkeypatch):
    monkeypatch.setitem(
        engines.ENGINE_FACTORIES, "hosted", lambda s: (FakeTranscriber(), FakeSummarizer())
    )
    with TestClient(create_app(settings)) as c:
        yield c


def wait_for_job(client, url, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.get(url, headers=AUTH).json()
        if status["status"] in ("done", "error"):
            return status
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def test_auth_missing(client):
    assert client.post("/memo", content=b"x").status_code == 401


def test_auth_wrong_token(client):
    r = client.post("/memo", content=b"x", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_oversize_rejected(client):
    r = client.post("/memo", content=b"x" * 2048, headers=AUTH)
    assert r.status_code == 413


def test_empty_rejected(client):
    assert client.post("/memo", content=b"", headers=AUTH).status_code == 400


def test_unknown_engine(client):
    r = client.post("/memo", params={"engine": "bogus"}, content=b"x", headers=AUTH)
    assert r.status_code == 400


def test_local_engine_501(client):
    r = client.post("/memo", params={"engine": "local"}, content=b"x", headers=AUTH)
    assert r.status_code == 501


def test_job_not_found(client):
    assert client.get("/jobs/nope", headers=AUTH).status_code == 404


def test_healthz_no_auth(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_happy_path(client, settings):
    r = client.post("/memo", content=b"fake-audio", headers=AUTH)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"

    status = wait_for_job(client, body["status_url"])
    assert status["status"] == "done", status
    note = Path(status["note_path"])
    assert note.exists()
    assert note.name.endswith("testing-the-pipeline-end-to-end.md")
    text = note.read_text(encoding="utf-8")
    for heading in ("## Thesis", "## Key Points", "## Actions", "## Open Questions", "## Transcript"):
        assert heading in text
    assert "Second paragraph." in text
    # audio removed from spool on success
    assert list((settings.data_dir / "spool").glob("*")) == []


def test_multipart_upload(client):
    r = client.post(
        "/memo", files={"file": ("memo.m4a", b"fake-audio", "audio/x-m4a")}, headers=AUTH
    )
    assert r.status_code == 202
    status = wait_for_job(client, r.json()["status_url"])
    assert status["status"] == "done"


def test_engine_failure_marks_error_and_keeps_audio(settings, monkeypatch):
    monkeypatch.setitem(
        engines.ENGINE_FACTORIES, "hosted", lambda s: (FakeTranscriber(), ExplodingSummarizer())
    )
    with TestClient(create_app(settings)) as client:
        r = client.post("/memo", content=b"fake-audio", headers=AUTH)
        status = wait_for_job(client, r.json()["status_url"], timeout=15.0)
        assert status["status"] == "error"
        assert "api down" in status["error"]
        # failed audio is kept in the spool for manual retry
        assert len(list((settings.data_dir / "spool").glob("*.m4a"))) == 1
