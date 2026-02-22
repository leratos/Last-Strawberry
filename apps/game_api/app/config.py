from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    api_title: str = "Last Strawberry Game API (Greenfield)"
    api_version: str = "0.2.0-g1"
    database_path: str = "apps/game_api/data/greenfield_game.db"
    public_game_domain: str = "last-strawberry.com"
    cors_allowed_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        db_path = (os.getenv("LS_GREENFIELD_DB_PATH") or "apps/game_api/data/greenfield_game.db").strip()
        normalized_db_path = str(Path(db_path))
        cors_raw = (os.getenv("LS_GREENFIELD_CORS_ORIGINS") or "").strip()
        cors_allowed_origins: tuple[str, ...]
        if cors_raw:
            cors_allowed_origins = tuple(origin.strip() for origin in cors_raw.split(",") if origin.strip())
        else:
            cors_allowed_origins = (
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3001",
                "http://127.0.0.1:3001",
            )
        return cls(
            environment=(os.getenv("LS_GREENFIELD_ENV") or "development").strip() or "development",
            database_path=normalized_db_path,
            public_game_domain=(os.getenv("LS_PUBLIC_GAME_DOMAIN") or "last-strawberry.com").strip() or "last-strawberry.com",
            cors_allowed_origins=cors_allowed_origins,
        )


settings = Settings.from_env()
