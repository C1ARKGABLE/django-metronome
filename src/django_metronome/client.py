from __future__ import annotations

from metronome import Metronome

from .conf import MetronomeSettings, get_metronome_settings


class MetronomeClientDisabledError(RuntimeError):
    """Raised when the integration is used without an API key."""


def build_metronome_client(
    config: MetronomeSettings | None = None,
) -> Metronome:
    cfg = config or get_metronome_settings()
    if not cfg.api_key:
        raise MetronomeClientDisabledError(
            "METRONOME_API_KEY is not configured for this environment."
        )

    timeout_seconds = cfg.timeout_ms / 1000
    return Metronome(
        bearer_token=cfg.api_key,
        webhook_secret=cfg.webhook_secret,
        base_url=cfg.base_url,
        timeout=timeout_seconds,
        max_retries=cfg.max_retries,
        _strict_response_validation=cfg.strict_schema_mode,
    )
