import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    token: str
    deepgram_api_key: str
    anthropic_api_key: str
    anthropic_model: str
    ntfy_url: str
    ntfy_topic: str
    ntfy_token: str
    obsidian_vault: str
    vault_dir: Path
    data_dir: Path
    host: str
    port: int
    max_upload_bytes: int


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        token=os.getenv("PLAUDIUS_TOKEN", ""),
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
        ntfy_url=os.getenv("NTFY_URL", "").rstrip("/"),
        ntfy_topic=os.getenv("NTFY_TOPIC", ""),
        ntfy_token=os.getenv("NTFY_TOKEN", ""),
        obsidian_vault=os.getenv("OBSIDIAN_VAULT", ""),
        vault_dir=Path(os.getenv("VAULT_DIR", "/data/vault/briefs")),
        data_dir=Path(os.getenv("DATA_DIR", "data")).absolute(),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8321")),
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_MB", "500")) * 1024 * 1024,
    )
