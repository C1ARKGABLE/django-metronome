from django_metronome.conf import (
    DEFAULT_ENV,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_MS,
    get_metronome_settings,
)


def test_metronome_settings_defaults(settings):
    settings.METRONOME_API_KEY = None
    settings.METRONOME_WEBHOOK_SECRET = None

    cfg = get_metronome_settings()

    assert cfg.api_key is None
    assert cfg.webhook_secret is None
    assert cfg.environment == DEFAULT_ENV
    assert cfg.timeout_ms == DEFAULT_TIMEOUT_MS
    assert cfg.max_retries == DEFAULT_MAX_RETRIES
    assert cfg.strict_schema_mode is False
    assert cfg.use_live_queries is False
    assert cfg.is_enabled is False


def test_metronome_settings_env_overrides(settings, monkeypatch):
    monkeypatch.delattr(settings, "METRONOME_API_KEY", raising=False)
    monkeypatch.delattr(settings, "METRONOME_WEBHOOK_SECRET", raising=False)
    settings.METRONOME_TIMEOUT_MS = 100
    settings.METRONOME_MAX_RETRIES = 1

    monkeypatch.setenv("METRONOME_API_KEY", "live_key")
    monkeypatch.setenv("METRONOME_WEBHOOK_SECRET", "whsec")
    monkeypatch.setenv("METRONOME_ENV", "production")
    monkeypatch.setenv("METRONOME_TIMEOUT_MS", "2500")
    monkeypatch.setenv("METRONOME_MAX_RETRIES", "7")
    monkeypatch.setenv("METRONOME_STRICT_SCHEMA_MODE", "true")
    monkeypatch.setenv("METRONOME_USE_LIVE_QUERIES", "1")

    cfg = get_metronome_settings()

    assert cfg.api_key == "live_key"
    assert cfg.webhook_secret == "whsec"
    assert cfg.environment == "production"
    assert cfg.timeout_ms == 2500
    assert cfg.max_retries == 7
    assert cfg.strict_schema_mode is True
    assert cfg.use_live_queries is True
    assert cfg.is_enabled is True
