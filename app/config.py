from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    admin_password: str
    session_secret: str
    database_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            admin_password=os.getenv("ADMIN_PASSWORD", "admin"),
            session_secret=os.getenv("SESSION_SECRET", "dev-session-secret-change-me"),
            database_url=os.getenv("DATABASE_URL", "sqlite:///data/despesas.db"),
        )
