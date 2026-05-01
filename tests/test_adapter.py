import pytest

from django_metronome.client import (
    MetronomeClientDisabledError,
    build_metronome_client,
)
from django_metronome.conf import MetronomeSettings
from django_metronome.services.metronome_adapter import (
    MetronomeAdapter,
    MetronomeApiVersion,
)


def test_build_metronome_client_requires_api_key():
    cfg = MetronomeSettings(
        api_key=None,
        webhook_secret=None,
        environment="sandbox",
        timeout_ms=1000,
        max_retries=1,
        strict_schema_mode=False,
        use_live_queries=False,
    )

    with pytest.raises(MetronomeClientDisabledError):
        build_metronome_client(cfg)


def test_build_metronome_client_passes_expected_options(monkeypatch):
    seen: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr("django_metronome.client.Metronome", FakeClient)
    cfg = MetronomeSettings(
        api_key="mtr_test",
        webhook_secret="whsec_test",
        environment="sandbox",
        timeout_ms=2500,
        max_retries=5,
        strict_schema_mode=True,
        use_live_queries=False,
    )

    client = build_metronome_client(cfg)

    assert isinstance(client, FakeClient)
    assert seen == {
        "bearer_token": "mtr_test",
        "webhook_secret": "whsec_test",
        "base_url": "https://sandbox.api.metronome.com",
        "timeout": 2.5,
        "max_retries": 5,
        "_strict_response_validation": True,
    }


def test_adapter_helpers(monkeypatch):
    class FakeClient:
        v1 = "v1-resource"
        v2 = "v2-resource"

    monkeypatch.setattr(
        "django_metronome.services.metronome_adapter.build_metronome_client",
        lambda: FakeClient(),
    )

    adapter = MetronomeAdapter()
    items = adapter.collect_paginated(lambda **_: iter([1, 2, 3]))

    assert adapter.version_resource(MetronomeApiVersion.V1) == "v1-resource"
    assert adapter.version_resource(MetronomeApiVersion.V2) == "v2-resource"
    assert items == [1, 2, 3]
