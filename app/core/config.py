import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


def load_env_file(path: str | Path = BASE_DIR / ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    return float(raw_value)


def _int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def _csv_env(name: str) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return ()
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str
    api_prefix: str
    database_url: str
    postas_service_token: str | None
    service_token_header_name: str
    service_source_header_name: str
    ai_provider: str
    fallback_ai_provider: str | None
    max_ai_attempts: int
    google_api_key: str | None
    google_model: str
    accepted_confidence_threshold: float
    minimum_confidence_threshold: float
    input_token_cost_per_million: float
    output_token_cost_per_million: float
    postas_ai_api_token: str | None
    require_api_token: bool
    token_header_name: str
    source_header_name: str
    allowed_request_sources: tuple[str, ...]
    image_download_timeout_seconds: float
    max_image_bytes: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env_file()
    fallback_provider = os.getenv("FALLBACK_AI_PROVIDER")
    fallback_provider = fallback_provider.strip() if fallback_provider else None
    api_token = os.getenv("POSTAS_AI_API_TOKEN") or os.getenv("API_SHARED_TOKEN")
    api_token = api_token.strip() if api_token else None
    service_token = os.getenv("POSTAS_SERVICE_TOKEN")
    service_token = service_token.strip() if service_token else None

    return Settings(
        app_name=os.getenv("APP_NAME", "Postas Platform API"),
        api_prefix=os.getenv("API_PREFIX", "/api/v1"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./postas_platform.db"),
        postas_service_token=service_token,
        service_token_header_name=os.getenv("POSTAS_SERVICE_TOKEN_HEADER", "X-Postas-Service-Token"),
        service_source_header_name=os.getenv("POSTAS_SERVICE_SOURCE_HEADER", "X-Postas-Source"),
        ai_provider=os.getenv("AI_PROVIDER", "google_genai").strip(),
        fallback_ai_provider=fallback_provider or None,
        max_ai_attempts=max(1, _int_env("MAX_AI_ATTEMPTS", 1)),
        google_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY"),
        google_model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash-lite"),
        accepted_confidence_threshold=_float_env("ACCEPTED_CONFIDENCE_THRESHOLD", 0.85),
        minimum_confidence_threshold=_float_env("MINIMUM_CONFIDENCE_THRESHOLD", 0.60),
        input_token_cost_per_million=_float_env("INPUT_TOKEN_COST_PER_MILLION", 0.0),
        output_token_cost_per_million=_float_env("OUTPUT_TOKEN_COST_PER_MILLION", 0.0),
        postas_ai_api_token=api_token,
        require_api_token=_bool_env("REQUIRE_API_TOKEN", False),
        token_header_name=os.getenv("POSTAS_AI_TOKEN_HEADER", "X-Postas-AI-Token"),
        source_header_name=os.getenv("POSTAS_AI_SOURCE_HEADER", "X-Postas-Source"),
        allowed_request_sources=_csv_env("ALLOWED_REQUEST_SOURCES"),
        image_download_timeout_seconds=_float_env("IMAGE_DOWNLOAD_TIMEOUT_SECONDS", 15.0),
        max_image_bytes=max(1, _int_env("MAX_IMAGE_BYTES", 10 * 1024 * 1024)),
    )
