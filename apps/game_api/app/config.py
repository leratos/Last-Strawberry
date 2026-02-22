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

    @classmethod
    def from_env(cls) -> "Settings":
        db_path = (os.getenv("LS_GREENFIELD_DB_PATH") or "apps/game_api/data/greenfield_game.db").strip()
        normalized_db_path = str(Path(db_path))
        return cls(
            environment=(os.getenv("LS_GREENFIELD_ENV") or "development").strip() or "development",
            database_path=normalized_db_path,
            public_game_domain=(os.getenv("LS_PUBLIC_GAME_DOMAIN") or "last-strawberry.com").strip() or "last-strawberry.com",
        )


settings = Settings.from_env()
