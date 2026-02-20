import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache

_OPENROUTER_PLACEHOLDER_VALUES = {
    "replace_me",
    "changeme",
    "change-me",
    "your_api_key_here",
    "your_openrouter_api_key",
}


def _read_env(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key)
    return value if value is not None else default


def _read_bool_env(key: str, default: bool) -> bool:
    raw = _read_env(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_choice_env(key: str, default: str, allowed: set[str]) -> str:
    raw = _read_env(key, default)
    value = (raw or default).strip().lower()
    return value if value in allowed else default


def _read_csv_env(key: str) -> tuple[str, ...]:
    raw = _read_env(key)
    if not raw:
        return ()
    values: list[str] = []
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate or candidate in values:
            continue
        values.append(candidate)
    return tuple(values)


def _read_openrouter_api_key() -> str | None:
    # 1) Explicit env vars have highest priority, except known placeholders.
    for explicit in (_read_env("LS_OPENROUTER_API_KEY"), _read_env("OPENROUTER_API_KEY")):
        candidate = (explicit or "").strip()
        if not candidate:
            continue
        if candidate.lower() in _OPENROUTER_PLACEHOLDER_VALUES:
            continue
        return candidate

    # 2) Fallback to keyring if available.
    try:
        import keyring  # type: ignore
    except Exception:
        return None

    service_candidates = [
        _read_env("LS_OPENROUTER_KEYRING_SERVICE", "OPENROUTER_API_KEY") or "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY",
        "openrouter",
    ]
    user_candidates = [
        _read_env("LS_OPENROUTER_KEYRING_USERNAME"),
        "default",
        "OPENROUTER_API_KEY",
        "api_key",
        os.getenv("USERNAME"),
        os.getenv("USER"),
    ]

    # Preserve order and remove empties/duplicates.
    service_candidates = [s for i, s in enumerate(service_candidates) if s and s not in service_candidates[:i]]
    user_candidates = [u for i, u in enumerate(user_candidates) if u and u not in user_candidates[:i]]

    # 3) On Windows, discover matching generic credentials from Credential Manager.
    for uname in user_candidates:
        for discovered_service in _discover_windows_keyring_services(uname):
            if discovered_service not in service_candidates:
                service_candidates.append(discovered_service)

    for service in service_candidates:
        for username in user_candidates:
            try:
                secret = keyring.get_password(service, username)
            except Exception:
                continue
            if secret:
                return secret
    return None


def _discover_windows_keyring_services(username: str) -> list[str]:
    if os.name != "nt" or not username:
        return []

    try:
        result = subprocess.run(
            ["cmdkey", "/list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return []

    if result.returncode != 0 or not result.stdout:
        return []

    services: list[str] = []
    current_target: str | None = None

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if lower.startswith("ziel:") or lower.startswith("target:"):
            current_target = line.split(":", 1)[1].strip()
            continue
        if lower.startswith("benutzer:") or lower.startswith("user:"):
            current_user = line.split(":", 1)[1].strip()
            if current_user != username or not current_target:
                continue

            cleaned = current_target
            for prefix in ("LegacyGeneric:target=", "target="):
                if cleaned.lower().startswith(prefix.lower()):
                    cleaned = cleaned[len(prefix) :]
                    break
            cleaned = cleaned.strip()
            if cleaned and cleaned not in services:
                services.append(cleaned)

    return services


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str | None = None
    openrouter_site_name: str = "last-strawberry-v2"
    analysis_model: str = "meta-llama/llama-3.3-70b-instruct"
    narrative_model: str = "meta-llama/llama-3.3-70b-instruct"
    analysis_fallback_models: tuple[str, ...] = ()
    narrative_fallback_models: tuple[str, ...] = ()
    analysis_temperature: float = 0.1
    narrative_temperature: float = 0.7
    analysis_max_tokens: int = 700
    narrative_max_tokens: int = 1200
    request_timeout_seconds: int = 45
    turn_timeout_seconds: int = 60
    database_url: str = "sqlite:///backend_v2/data/last_strawberry_v2.db"
    database_auto_init: bool = True
    jwt_secret: str = "change-me-in-production-please-use-32-plus-chars"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    memory_context_limit: int = 5
    memory_min_importance: float = 0.6
    memory_retrieval_strategy: str = "hybrid"
    embeddings_provider: str = "hash"
    embeddings_dimensions: int = 64
    embeddings_model: str = "openai/text-embedding-3-small"
    embeddings_timeout_seconds: int = 20
    retrieval_vector_weight: float = 1.2
    retrieval_semantic_min_similarity: float = 0.2
    turn_rate_limit_enabled: bool = True
    turn_rate_limit_requests: int = 20
    turn_rate_limit_window_seconds: int = 60
    turn_ip_rate_limit_enabled: bool = True
    turn_ip_rate_limit_requests: int = 60
    turn_ip_rate_limit_window_seconds: int = 60
    login_rate_limit_enabled: bool = True
    login_rate_limit_requests: int = 200
    login_rate_limit_window_seconds: int = 60
    max_request_body_bytes: int = 262144
    slo_window: str = "300s"
    slo_max_5xx_percent: float = 1.0
    slo_max_429_percent: float = 5.0
    metrics_api_key: str | None = None
    metrics_api_key_header: str = "X-Metrics-Key"
    environment: str = "development"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openrouter_api_key=_read_openrouter_api_key(),
            openrouter_base_url=_read_env("LS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1") or "https://openrouter.ai/api/v1",
            openrouter_site_url=_read_env("LS_OPENROUTER_SITE_URL"),
            openrouter_site_name=_read_env("LS_OPENROUTER_SITE_NAME", "last-strawberry-v2") or "last-strawberry-v2",
            analysis_model=_read_env("LS_ANALYSIS_MODEL", "meta-llama/llama-3.3-70b-instruct") or "meta-llama/llama-3.3-70b-instruct",
            narrative_model=_read_env("LS_NARRATIVE_MODEL", "meta-llama/llama-3.3-70b-instruct") or "meta-llama/llama-3.3-70b-instruct",
            analysis_fallback_models=_read_csv_env("LS_ANALYSIS_FALLBACK_MODELS"),
            narrative_fallback_models=_read_csv_env("LS_NARRATIVE_FALLBACK_MODELS"),
            analysis_temperature=float(_read_env("LS_ANALYSIS_TEMPERATURE", "0.1") or "0.1"),
            narrative_temperature=float(_read_env("LS_NARRATIVE_TEMPERATURE", "0.7") or "0.7"),
            analysis_max_tokens=int(_read_env("LS_ANALYSIS_MAX_TOKENS", "700") or "700"),
            narrative_max_tokens=int(_read_env("LS_NARRATIVE_MAX_TOKENS", "1200") or "1200"),
            request_timeout_seconds=int(_read_env("LS_REQUEST_TIMEOUT_SECONDS", "45") or "45"),
            turn_timeout_seconds=max(1, int(_read_env("LS_TURN_TIMEOUT_SECONDS", "60") or "60")),
            database_url=_read_env("LS_DATABASE_URL", "sqlite:///backend_v2/data/last_strawberry_v2.db")
            or "sqlite:///backend_v2/data/last_strawberry_v2.db",
            database_auto_init=_read_bool_env("LS_DATABASE_AUTO_INIT", True),
            jwt_secret=_read_env("LS_JWT_SECRET", "change-me-in-production-please-use-32-plus-chars")
            or "change-me-in-production-please-use-32-plus-chars",
            jwt_algorithm=_read_env("LS_JWT_ALGORITHM", "HS256") or "HS256",
            jwt_expire_minutes=int(_read_env("LS_JWT_EXPIRE_MINUTES", "120") or "120"),
            memory_context_limit=int(_read_env("LS_MEMORY_CONTEXT_LIMIT", "5") or "5"),
            memory_min_importance=float(_read_env("LS_MEMORY_MIN_IMPORTANCE", "0.6") or "0.6"),
            memory_retrieval_strategy=_read_choice_env(
                "LS_MEMORY_RETRIEVAL_STRATEGY",
                "hybrid",
                {"hybrid", "lexical"},
            ),
            embeddings_provider=_read_choice_env(
                "LS_EMBEDDINGS_PROVIDER",
                "hash",
                {"hash", "none", "openrouter"},
            ),
            embeddings_dimensions=int(_read_env("LS_EMBEDDINGS_DIMENSIONS", "64") or "64"),
            embeddings_model=_read_env("LS_EMBEDDINGS_MODEL", "openai/text-embedding-3-small")
            or "openai/text-embedding-3-small",
            embeddings_timeout_seconds=int(_read_env("LS_EMBEDDINGS_TIMEOUT_SECONDS", "20") or "20"),
            retrieval_vector_weight=float(_read_env("LS_RETRIEVAL_VECTOR_WEIGHT", "1.2") or "1.2"),
            retrieval_semantic_min_similarity=float(
                _read_env("LS_RETRIEVAL_SEMANTIC_MIN_SIMILARITY", "0.2") or "0.2"
            ),
            turn_rate_limit_enabled=_read_bool_env("LS_TURN_RATE_LIMIT_ENABLED", True),
            turn_rate_limit_requests=max(1, int(_read_env("LS_TURN_RATE_LIMIT_REQUESTS", "20") or "20")),
            turn_rate_limit_window_seconds=max(1, int(_read_env("LS_TURN_RATE_LIMIT_WINDOW_SECONDS", "60") or "60")),
            turn_ip_rate_limit_enabled=_read_bool_env("LS_TURN_IP_RATE_LIMIT_ENABLED", True),
            turn_ip_rate_limit_requests=max(1, int(_read_env("LS_TURN_IP_RATE_LIMIT_REQUESTS", "60") or "60")),
            turn_ip_rate_limit_window_seconds=max(
                1,
                int(_read_env("LS_TURN_IP_RATE_LIMIT_WINDOW_SECONDS", "60") or "60"),
            ),
            login_rate_limit_enabled=_read_bool_env("LS_LOGIN_RATE_LIMIT_ENABLED", True),
            login_rate_limit_requests=max(1, int(_read_env("LS_LOGIN_RATE_LIMIT_REQUESTS", "200") or "200")),
            login_rate_limit_window_seconds=max(1, int(_read_env("LS_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60") or "60")),
            max_request_body_bytes=max(1024, int(_read_env("LS_MAX_REQUEST_BODY_BYTES", "262144") or "262144")),
            slo_window=(_read_env("LS_SLO_WINDOW", "300s") or "300s").strip() or "300s",
            slo_max_5xx_percent=max(0.0, float(_read_env("LS_SLO_MAX_5XX_PERCENT", "1.0") or "1.0")),
            slo_max_429_percent=max(0.0, float(_read_env("LS_SLO_MAX_429_PERCENT", "5.0") or "5.0")),
            metrics_api_key=_read_env("LS_METRICS_API_KEY"),
            metrics_api_key_header=_read_env("LS_METRICS_API_KEY_HEADER", "X-Metrics-Key") or "X-Metrics-Key",
            environment=_read_env("LS_ENVIRONMENT", "development") or "development",
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
