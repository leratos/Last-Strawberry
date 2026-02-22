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
    llm_mode: str = "preview"
    llm_fallback_to_preview: bool = True
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_intent_model: str = "meta-llama/llama-3.3-70b-instruct"
    openrouter_narrator_model: str = "meta-llama/llama-3.3-70b-instruct"
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
        fallback_raw = (os.getenv("LS_GREENFIELD_LLM_FALLBACK_TO_PREVIEW") or "true").strip().lower()
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
            llm_mode=(os.getenv("LS_GREENFIELD_LLM_MODE") or "preview").strip().lower() or "preview",
            llm_fallback_to_preview=fallback_raw not in {"0", "false", "no", "off"},
            openrouter_api_key=(os.getenv("OPENROUTER_API_KEY") or "").strip(),
            openrouter_base_url=(os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip()
            or "https://openrouter.ai/api/v1",
            openrouter_intent_model=(
                os.getenv("LS_GREENFIELD_OPENROUTER_INTENT_MODEL") or "meta-llama/llama-3.3-70b-instruct"
            ).strip()
            or "meta-llama/llama-3.3-70b-instruct",
            openrouter_narrator_model=(
                os.getenv("LS_GREENFIELD_OPENROUTER_NARRATOR_MODEL") or "meta-llama/llama-3.3-70b-instruct"
            ).strip()
            or "meta-llama/llama-3.3-70b-instruct",
            cors_allowed_origins=cors_allowed_origins,
        )


settings = Settings.from_env()
