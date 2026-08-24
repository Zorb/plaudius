# Plaudius

Voice-memo-to-brief pipeline. An iPhone Shortcut POSTs a voice memo (m4a) over
Tailscale; Plaudius transcribes it (Deepgram Nova-3), generates a structured
brief (claude-haiku-4-5), writes a markdown note into the Obsidian vault, and
pushes a ntfy notification whose click opens the note in Obsidian.

```
iPhone Shortcut ──POST /memo──> FastAPI (202 + job id)
                                   │  SQLite queue (sequential, survives restarts)
                                   ▼
                     Deepgram ──> Claude ──> /data/vault/briefs/*.md ──> ntfy push
```

## API

- `POST /memo?engine=hosted` — body = audio bytes (raw or multipart). Auth:
  `Authorization: Bearer $PLAUDIUS_TOKEN`. Returns `202 {job_id, status_url}`.
  Uploads over 500MB are rejected; `engine=local` returns 501 (dropped — no GPU;
  the engine interface in `src/plaudius/engines.py` is where it would slot in).
- `GET /jobs/{id}` — job status (auth required).
- `GET /healthz` — liveness + queue counts (no auth).

## .env keys

Copy `env.example` to `.env` (deploy.sh does this on first deploy and generates
a random `PLAUDIUS_TOKEN`).

| Key | Meaning |
|---|---|
| `PLAUDIUS_TOKEN` | Static bearer token the Shortcut must send |
| `DEEPGRAM_API_KEY` | Deepgram API key (Nova-3 prerecorded) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `ANTHROPIC_MODEL` | Default `claude-haiku-4-5` |
| `NTFY_URL` / `NTFY_TOPIC` / `NTFY_TOKEN` | Self-hosted ntfy; empty URL disables pushes |
| `OBSIDIAN_VAULT` | Vault name as shown in the Obsidian app (for the obsidian:// click URI) |
| `VAULT_DIR` | Where briefs are written (default `/data/vault/briefs`) |
| `DATA_DIR` | Spool + SQLite queue (default `data/`) |
| `HOST` / `PORT` / `MAX_UPLOAD_MB` | Server binding (default 0.0.0.0:8321) and upload cap |

## Deploy (ubuntu-main)

```bash
bash deploy/deploy.sh          # tar -> ssh, uv sync, (re)start systemd unit
```

The systemd unit lives at `deploy/plaudius.service` and is installed by symlink
(`systemctl link`), so redeploys update it in place; `daemon-reload` + `restart`
are part of the script. It runs as `__DEPLOY_USER__`, `WorkingDirectory=~/plaudius`, with
`TZ=Europe/London` so note filenames use UK-local time. Logs go to journald:

```bash
journalctl -u plaudius -f
```

## Notes & error handling

- Filename: `YYYY-MM-DD HHmm - {slug of thesis}.md`; collisions get ` 2`, ` 3`…
- Frontmatter: `date`, `duration_seconds`, `engine`, `tags` (LLM-suggested, lowercased).
- Deepgram/Anthropic calls are retried once; a job that still fails is marked
  `error`, triggers a ntfy warning push, and its audio stays in `data/spool/`
  for manual retry (re-POST it or delete it).
- Jobs process sequentially; anything mid-flight during a restart is requeued.

## Smoke test

On the VM, with `.env` filled:

```bash
cd ~/plaudius && uv run scripts/smoke_test.py
```

Posts `scripts/sample-memo.mp3`, polls the job, and asserts the brief appears
in the vault with the right structure.

## Vault sync (Obsidian Sync via container)

`/data/vault` reaches the iPhone through official Obsidian Sync, relayed by the
Obsidian desktop app running in a container on the VM (`deploy/obsidian-sync/`).
One-time setup: `docker compose -f ~/plaudius/deploy/obsidian-sync/compose.yaml up -d`,
open `http://__TAILNET_IP__:3000`, open `/vault` as a folder-vault, sign in to
Obsidian Sync, create/connect the dedicated remote vault, enable sync. The
remote vault's name must match `OBSIDIAN_VAULT` in `.env`, and the same vault
must be added on the iPhone. The container auto-starts with Docker.

## iPhone Shortcut (not in this repo)

"Get Contents of URL": `http://__TAILNET_IP__:8321/memo`, method POST, header
`Authorization: Bearer <PLAUDIUS_TOKEN>`, request body = the recorded audio
file. The phone must be on the Tailscale network.
