"""Sequential job worker: transcribe -> summarise -> write note -> push."""
import asyncio
import logging
import time
import traceback
from datetime import datetime
from pathlib import Path

from . import notify
from .brief import note_filename, render_brief, write_note
from .config import Settings
from .engines import ENGINE_FACTORIES
from .jobs import JobStore

log = logging.getLogger("plaudius.worker")

_RETRY_DELAY_SECONDS = 3.0


def _retry_once(fn, arg, stage: str):
    """One retry per external call, then the job fails (spec behaviour)."""
    try:
        return fn(arg)
    except Exception:
        log.warning("%s failed; retrying once", stage, exc_info=True)
        time.sleep(_RETRY_DELAY_SECONDS)
        return fn(arg)


def process_job(job, settings: Settings) -> Path:
    transcriber, summarizer = ENGINE_FACTORIES[job["engine"]](settings)
    audio = Path(job["audio_path"]).read_bytes()
    transcript = _retry_once(transcriber.transcribe, audio, "transcription")
    brief = _retry_once(summarizer.summarize, transcript.text, "summarisation")
    now = datetime.now()  # unit sets TZ=Europe/London; filenames use local time
    note_path = write_note(
        settings.vault_dir,
        note_filename(brief.thesis, now),
        render_brief(brief, transcript, job["engine"], now),
    )
    notify.push(
        settings,
        title=brief.thesis,
        message="\n".join(f"• {p}" for p in brief.key_points) or "(no key points)",
        click=notify.obsidian_uri(
            settings.obsidian_vault, f"{settings.vault_dir.name}/{note_path.stem}"
        ),
    )
    Path(job["audio_path"]).unlink(missing_ok=True)
    return note_path


async def worker_loop(store: JobStore, settings: Settings, wake: asyncio.Event) -> None:
    requeued = store.recover_stale()
    if requeued:
        log.info("requeued %d interrupted job(s) from previous run", requeued)
    while True:
        job = store.claim_next()
        if job is None:
            wake.clear()
            try:
                await asyncio.wait_for(wake.wait(), timeout=5.0)
            except TimeoutError:
                pass
            continue
        log.info("processing job %s (engine=%s)", job["id"], job["engine"])
        try:
            note_path = await asyncio.to_thread(process_job, job, settings)
            store.mark_done(job["id"], str(note_path))
            log.info("job %s done -> %s", job["id"], note_path)
        except asyncio.CancelledError:
            raise  # audio stays in spool; recover_stale() requeues on next start
        except Exception as exc:
            log.error("job %s failed: %s\n%s", job["id"], exc, traceback.format_exc())
            store.mark_error(job["id"], f"{type(exc).__name__}: {exc}")
            await asyncio.to_thread(
                notify.push,
                settings,
                title="Plaudius: memo processing failed",
                message=f"job {job['id']}: {type(exc).__name__}: {exc}"[:900],
                tags=["warning"],
            )
