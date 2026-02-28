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
    hybrid_intent_llm_for_complex_inputs: bool = False
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 20.0
    openrouter_json_repair_attempts: int = 1
    openrouter_intent_model: str = "qwen/qwen3-next-80b-a3b-instruct"
    openrouter_narrator_model: str = "meta-llama/llama-3.3-70b-instruct"
    openrouter_bootstrap_model: str = "meta-llama/llama-3.3-70b-instruct"
    cors_allowed_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    )
    cors_allow_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    @classmethod
    def from_env(cls) -> "Settings":
        db_path = (os.getenv("LS_GREENFIELD_DB_PATH") or "apps/game_api/data/greenfield_game.db").strip()
        normalized_db_path = str(Path(db_path))
        fallback_raw = (os.getenv("LS_GREENFIELD_LLM_FALLBACK_TO_PREVIEW") or "true").strip().lower()
        hybrid_intent_complex_raw = (
            os.getenv("LS_GREENFIELD_HYBRID_INTENT_LLM_FOR_COMPLEX_INPUTS") or "false"
        ).strip().lower()
        openrouter_timeout_raw = (os.getenv("LS_GREENFIELD_OPENROUTER_TIMEOUT_SECONDS") or "20").strip()
        openrouter_json_repair_attempts_raw = (
            os.getenv("LS_GREENFIELD_OPENROUTER_JSON_REPAIR_ATTEMPTS") or "1"
        ).strip()
        cors_raw = (os.getenv("LS_GREENFIELD_CORS_ORIGINS") or "").strip()
        cors_regex_raw = (
            os.getenv("LS_GREENFIELD_CORS_ALLOW_ORIGIN_REGEX")
            or r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
        ).strip()
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
            hybrid_intent_llm_for_complex_inputs=hybrid_intent_complex_raw in {"1", "true", "yes", "on"},
            openrouter_api_key=(os.getenv("OPENROUTER_API_KEY") or "").strip(),
            openrouter_base_url=(os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip()
            or "https://openrouter.ai/api/v1",
            openrouter_timeout_seconds=max(1.0, float(openrouter_timeout_raw or "20")),
            openrouter_json_repair_attempts=max(0, int(openrouter_json_repair_attempts_raw or "1")),
            openrouter_intent_model=(
                os.getenv("LS_GREENFIELD_OPENROUTER_INTENT_MODEL") or "qwen/qwen3-next-80b-a3b-instruct"
            ).strip()
            or "qwen/qwen3-next-80b-a3b-instruct",
            openrouter_narrator_model=(
                os.getenv("LS_GREENFIELD_OPENROUTER_NARRATOR_MODEL") or "meta-llama/llama-3.3-70b-instruct"
            ).strip()
            or "meta-llama/llama-3.3-70b-instruct",
            openrouter_bootstrap_model=(
                os.getenv("LS_GREENFIELD_OPENROUTER_BOOTSTRAP_MODEL") or "meta-llama/llama-3.3-70b-instruct"
            ).strip()
            or "meta-llama/llama-3.3-70b-instruct",
            cors_allowed_origins=cors_allowed_origins,
            cors_allow_origin_regex=cors_regex_raw,
        )


settings = Settings.from_env()
