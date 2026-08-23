"""Smoke test: POST a sample memo to a running Plaudius, wait for the job,
and check the brief landed in the vault.

Run on the VM from the project root:  uv run scripts/smoke_test.py
"""
import argparse
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

REQUIRED_HEADINGS = ("## Thesis", "## Key Points", "## Actions", "## Open Questions", "## Transcript")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(Path(__file__).parent / "sample-memo.mp3"))
    parser.add_argument("--base", default=None, help="service base URL (default: local port from .env)")
    parser.add_argument("--engine", default="hosted")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    load_dotenv()
    token = os.getenv("PLAUDIUS_TOKEN")
    if not token:
        sys.exit("PLAUDIUS_TOKEN not set (run from the project root with a filled .env)")
    base = args.base or f"http://127.0.0.1:{os.getenv('PORT', '8321')}"
    auth = {"Authorization": f"Bearer {token}"}

    audio = Path(args.file).read_bytes()
    print(f"POST {base}/memo ({len(audio)} bytes, engine={args.engine})")
    r = httpx.post(f"{base}/memo", params={"engine": args.engine}, content=audio, headers=auth, timeout=60)
    r.raise_for_status()
    job = r.json()
    print(f"job accepted: {job['job_id']}")

    deadline = time.time() + args.timeout
    status = None
    while time.time() < deadline:
        status = httpx.get(f"{base}{job['status_url']}", headers=auth, timeout=15).json()
        if status["status"] in ("done", "error"):
            break
        time.sleep(3)
    else:
        sys.exit(f"TIMEOUT: job still {status['status'] if status else 'unknown'} after {args.timeout}s")

    if status["status"] != "done":
        sys.exit(f"FAIL: job errored: {status['error']}")

    note = Path(status["note_path"])
    if not note.exists():
        sys.exit(f"FAIL: note not found at {note}")
    text = note.read_text(encoding="utf-8")
    missing = [h for h in REQUIRED_HEADINGS if h not in text]
    if missing or not text.startswith("---"):
        sys.exit(f"FAIL: note malformed (missing {missing or 'frontmatter'})")

    print(f"SMOKE OK: {note}")
    print("-" * 60)
    print(text[:600])


if __name__ == "__main__":
    main()
