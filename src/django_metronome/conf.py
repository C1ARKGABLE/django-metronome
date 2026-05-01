from __future__ import annotations

import os
from dataclasses import dataclass

from django.conf import settings

DEFAULT_TIMEOUT_MS = 10_000
DEFAULT_MAX_RETRIES = 2
DEFAULT_ENV = "sandbox"


@dataclass(frozen=True, slots=True)
class MetronomeSettings:
    api_key: str | None
    webhook_secret: str | None
    environment: str
    timeout_ms: int
    max_retries: int
    strict_schema_mode: bool
    use_live_queries: bool

    @property
    def is_enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def base_url(self) -> str:
        if self.environment == "production":
            return "https://api.metronome.com"
        if self.environment == "sandbox":
            return "https://sandbox.api.metronome.com"
        return "http://localhost:4010"


def _read_setting(name: str, default: object) -> object:
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value
    return getattr(settings, name, default)


def _as_int(value: object, *, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _as_bool(value: object, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_metronome_settings() -> MetronomeSettings:
    return MetronomeSettings(
        api_key=_read_setting("METRONOME_API_KEY", None),
        webhook_secret=_read_setting("METRONOME_WEBHOOK_SECRET", None),
        environment=str(_read_setting("METRONOME_ENV", DEFAULT_ENV)),
        timeout_ms=_as_int(
            _read_setting("METRONOME_TIMEOUT_MS", DEFAULT_TIMEOUT_MS),
            default=DEFAULT_TIMEOUT_MS,
        ),
        max_retries=_as_int(
            _read_setting("METRONOME_MAX_RETRIES", DEFAULT_MAX_RETRIES),
            default=DEFAULT_MAX_RETRIES,
        ),
        strict_schema_mode=_as_bool(
            _read_setting("METRONOME_STRICT_SCHEMA_MODE", False),
            default=False,
        ),
        use_live_queries=_as_bool(
            _read_setting("METRONOME_USE_LIVE_QUERIES", False),
            default=False,
        ),
    )
