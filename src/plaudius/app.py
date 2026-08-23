"""FastAPI app: receives memos, exposes job status, hosts the worker."""
import asyncio
import hmac
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request

from .config import Settings, load_settings
from .engines import ENGINE_FACTORIES
from .jobs import JobStore
from .worker import worker_loop

log = logging.getLogger("plaudius")


def _require_auth(request: Request) -> None:
    token = request.app.state.settings.token
    supplied = request.headers.get("authorization", "")
    if not token or not hmac.compare_digest(supplied, f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")


async def _save_upload(request: Request, dest: Path, limit: int) -> int:
    """Stream the body (raw, or multipart from clients that send forms) to dest."""
    size = 0
    content_type = request.headers.get("content-type", "")
    with dest.open("wb") as out:
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            upload = next((v for v in form.values() if hasattr(v, "read")), None)
            if upload is None:
                raise HTTPException(status_code=400, detail="multipart body contains no file field")
            while chunk := await upload.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail="upload exceeds size limit")
                out.write(chunk)
        else:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail="upload exceeds size limit")
                out.write(chunk)
    return size


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.store = JobStore(settings.data_dir / "plaudius.db")
        app.state.wake = asyncio.Event()
        worker = asyncio.create_task(worker_loop(app.state.store, settings, app.state.wake))
        log.info("plaudius up (vault=%s, data=%s)", settings.vault_dir, settings.data_dir)
        yield
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

    app = FastAPI(title="plaudius", lifespan=lifespan)

    @app.post("/memo", status_code=202, dependencies=[Depends(_require_auth)])
    async def memo(request: Request, engine: str = "hosted"):
        if engine == "local":
            raise HTTPException(
                status_code=501, detail="local engine is not configured on this host (hosted only)"
            )
        if engine not in ENGINE_FACTORIES:
            raise HTTPException(status_code=400, detail=f"unknown engine '{engine}'")
        state = request.app.state
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > state.settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="upload exceeds size limit")
        spool = state.settings.data_dir / "spool"
        spool.mkdir(parents=True, exist_ok=True)
        job_id = uuid.uuid4().hex[:12]
        dest = spool / f"{job_id}.m4a"
        try:
            size = await _save_upload(request, dest, state.settings.max_upload_bytes)
        except HTTPException:
            dest.unlink(missing_ok=True)
            raise
        if size == 0:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="empty upload")
        state.store.enqueue(job_id, engine, str(dest))
        state.wake.set()
        log.info("accepted memo %s (%d bytes, engine=%s)", job_id, size, engine)
        return {"job_id": job_id, "status": "queued", "status_url": f"/jobs/{job_id}"}

    @app.get("/jobs/{job_id}", dependencies=[Depends(_require_auth)])
    async def job_status(job_id: str, request: Request):
        row = request.app.state.store.get(job_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown job id")
        return {
            k: row[k]
            for k in ("id", "status", "engine", "note_path", "error", "created_at", "updated_at")
        }

    @app.get("/healthz")
    async def healthz(request: Request):
        return {"status": "ok", "jobs": request.app.state.store.counts()}

    return app


app = create_app()
