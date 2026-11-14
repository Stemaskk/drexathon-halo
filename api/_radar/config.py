"""Server-side configuration. Secrets are read from environment variables only."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_dotenv() -> None:
    """Minimal .env loader for local dev (Vercel injects env vars itself)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "" or value.endswith("_here"):  # unset or still the .env.example placeholder
        return default
    return value


def env_float(name: str) -> float | None:
    value = env(name)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class MissingKey(RuntimeError):
    def __init__(self, var: str):
        super().__init__(f"{var} is not configured. Set it in your local .env (see .env.example) or in Vercel project settings.")
        self.var = var


def require(name: str) -> str:
    value = env(name)
    if not value:
        raise MissingKey(name)
    return value


NACE_BASE_URL = env("NACE_BASE_URL", "https://console.nace.ai").rstrip("/")
DREX_MODEL = env("DREX_MODEL", "drex-latest")
DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"
DEEPINFRA_MODEL = env("DEEPINFRA_MODEL", "Qwen/Qwen3.8-27B")
BASELINE_MODEL = env("BASELINE_MODEL", DEEPINFRA_MODEL)
KEENABLE_BASE_URL = "https://api.keenable.ai"


def key_status() -> dict[str, bool]:
    return {k: bool(env(k)) for k in ("NACE_API_KEY", "DEEPINFRA_API_KEY", "KEENABLE_API_KEY")}
