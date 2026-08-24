# Plaudius

Press a button on your iPhone, talk, and a structured brief of what you said
appears in Obsidian — with a push notification that opens it.

The Shortcut POSTs the recording over Tailscale to a FastAPI service on
ubuntu-main. The service transcribes it with **Deepgram Nova-3**, distills a
brief with **claude-haiku-4-5**, writes a markdown note into the synced vault,
and pushes via **self-hosted ntfy**; tapping the push opens the note via an
`obsidian://` URI.

```
iPhone Shortcut (side/Action button)
      │ POST /memo  (bearer token, Tailscale)
      ▼
plaudius service ── 202 + job id, then in the background:
      │  SQLite queue · sequential worker · survives restarts
      ▼
Deepgram Nova-3 ──> claude-haiku-4-5 ──> /data/vault/briefs/*.md ──> ntfy push
                                              │                        │
                              obsidian-sync container            ntfy container
                              (Obsidian app + paid Sync)         (tailnet :8322)
                                              ▼                        ▼
                                        iPhone Obsidian    ── tap ──  ntfy app
```

Three pieces run on the VM:

| Piece | What | Where |
|---|---|---|
| `plaudius` | The service (systemd unit, port 8321) | `src/`, `deploy/plaudius.service` |
| `obsidian-sync` | Obsidian desktop app in a container, signed into Obsidian Sync, vault `Plaudius` mounted from `/data/vault` — the bridge that gets notes to devices | `deploy/obsidian-sync/` |
| `ntfy` | Self-hosted push server, tailnet-bound `:8322`, topic `plaudius` | `deploy/ntfy/` |

## API

- `POST /memo?engine=hosted` — body = audio bytes (raw or multipart), header
  `Authorization: Bearer $PLAUDIUS_TOKEN`. Returns `202 {job_id, status_url}`.
  Over 500MB → 413. `engine=local` → 501 (dropped — no GPU; a local engine would
  register in `src/plaudius/engines.py`).
- `GET /jobs/{id}` — job status (auth required).
- `GET /healthz` — liveness + queue counts (no auth).

## Brief format

Filename `YYYY-MM-DD HHmm - {slug of thesis}.md` (UK-local time; collisions get
` 2`, ` 3`…). YAML frontmatter: `date`, `duration_seconds`, `engine`, `tags`
(LLM-suggested, lowercased). Sections: Thesis / Key Points / Actions / Open
Questions / Transcript (paragraph-formatted). The LLM only returns JSON; the
markdown is rendered in code, so the structure is guaranteed.

## .env

Copy `env.example` to `.env` on the VM (first deploy does this and generates a
random `PLAUDIUS_TOKEN`). Deploys never overwrite an existing `.env`.

| Key | Meaning |
|---|---|
| `PLAUDIUS_TOKEN` | Bearer token the Shortcut sends; restart after changing |
| `DEEPGRAM_API_KEY` / `ANTHROPIC_API_KEY` | Hosted engine credentials |
| `ANTHROPIC_MODEL` | Default `claude-haiku-4-5` |
| `NTFY_URL` / `NTFY_TOPIC` / `NTFY_TOKEN` | `http://__TAILNET_IP__:8322` / `plaudius` / empty (no auth) |
| `OBSIDIAN_VAULT` | `Plaudius` — must match the vault name in the Obsidian app |
| `VAULT_DIR` / `DATA_DIR` | `/data/vault/briefs` / `data` (spool + queue db) |
| `HOST` / `PORT` / `MAX_UPLOAD_MB` | `0.0.0.0` / `8321` / `500` |

## Setting up from scratch

On a fresh VM: install Docker; `sudo mkdir -p /data/vault/briefs && sudo chown -R <user>: /data/vault`.

1. `bash deploy/deploy.sh` — ships the tree, installs uv, syncs deps, installs
   the systemd unit via `systemctl link`, starts it.
2. Fill the API keys in `~/plaudius/.env`, `sudo systemctl restart plaudius`.
3. `docker compose -f ~/plaudius/deploy/obsidian-sync/compose.yaml up -d`, open
   **https**://__TAILNET_IP__:**3001** (self-signed cert; port 3000 gives a black
   screen — Selkies refuses to stream without a secure context). Inside Obsidian:
   Open folder as vault → `/vault` (Ctrl+L to type the path), sign in to Obsidian
   Sync, create/connect the remote vault, enable sync. Add the same vault on the
   phone (same E2E encryption password).
4. `docker compose -f ~/plaudius/deploy/ntfy/compose.yaml up -d`. On the phone,
   ntfy app → add server `http://__TAILNET_IP__:8322` → subscribe `plaudius`.
   iOS delivery is instant via `NTFY_UPSTREAM_BASE_URL=https://ntfy.sh` — a
   content-free wake ping goes through Apple's pipeline and the phone fetches the
   message from this server, so brief content never leaves the box. Auth is off
   (tailnet-only); hardening commands are commented in the compose file.
5. iPhone Shortcut: Record Audio (Finish Recording: On Tap) → Get Contents of URL
   → `http://__TAILNET_IP__:8321/memo`, POST, header `Authorization: Bearer <token>`,
   body File = the recording. Map it to the Action Button (Settings → Action
   Button → Shortcut) or Back Tap on older phones.

## Operations

- Tests (hosted APIs stubbed): `uv run pytest`
- Smoke test (on VM, real APIs): `cd ~/plaudius && uv run scripts/smoke_test.py`
- Logs: `journalctl -u plaudius -f`
- Redeploy after changes: `bash deploy/deploy.sh`
- Failures: each Deepgram/Anthropic call is retried once; a job that still fails
  is marked `error`, sends a warning push, and keeps its audio in `data/spool/`
  — re-POST or delete it. Jobs mid-flight during a restart are requeued.
