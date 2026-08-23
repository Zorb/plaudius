from plaudius.jobs import JobStore


def make_store(tmp_path) -> JobStore:
    return JobStore(tmp_path / "jobs.db")


def test_enqueue_and_claim_fifo(tmp_path):
    store = make_store(tmp_path)
    store.enqueue("aaa", "hosted", "/spool/aaa.m4a")
    store.enqueue("bbb", "hosted", "/spool/bbb.m4a")
    first = store.claim_next()
    assert first["id"] == "aaa"
    assert first["status"] == "processing"
    assert store.claim_next()["id"] == "bbb"
    assert store.claim_next() is None


def test_mark_done(tmp_path):
    store = make_store(tmp_path)
    store.enqueue("aaa", "hosted", "/spool/aaa.m4a")
    store.claim_next()
    store.mark_done("aaa", "/vault/note.md")
    row = store.get("aaa")
    assert row["status"] == "done"
    assert row["note_path"] == "/vault/note.md"


def test_mark_error(tmp_path):
    store = make_store(tmp_path)
    store.enqueue("aaa", "hosted", "/spool/aaa.m4a")
    store.claim_next()
    store.mark_error("aaa", "boom")
    assert store.get("aaa")["status"] == "error"
    assert store.get("aaa")["error"] == "boom"


def test_recover_stale_requeues_processing(tmp_path):
    """A job mid-flight during a crash must be picked up again after restart."""
    store = make_store(tmp_path)
    store.enqueue("aaa", "hosted", "/spool/aaa.m4a")
    store.claim_next()
    # simulate restart: new store over the same db file
    store2 = JobStore(tmp_path / "jobs.db")
    assert store2.recover_stale() == 1
    assert store2.claim_next()["id"] == "aaa"


def test_counts(tmp_path):
    store = make_store(tmp_path)
    store.enqueue("aaa", "hosted", "x")
    store.enqueue("bbb", "hosted", "y")
    store.claim_next()
    assert store.counts() == {"processing": 1, "queued": 1}


def test_get_unknown(tmp_path):
    assert make_store(tmp_path).get("nope") is None
