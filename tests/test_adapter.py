from datetime import UTC, datetime

import pytest

from django_metronome.client import (
    MetronomeClientDisabledError,
    build_metronome_client,
)
from django_metronome.conf import MetronomeSettings
from django_metronome.services.metronome_adapter import (
    MetronomeAdapter,
    MetronomeApiVersion,
    format_metronome_usage_timestamp,
    normalize_metronome_usage_window_bound,
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
        "base_url": "https://api.metronome.com",
        "timeout": 2.5,
        "max_retries": 5,
        "_strict_response_validation": True,
    }


def test_list_rate_cards_page():
    class Row:
        def to_dict(self):
            return {"id": "rc-1", "name": "Default pricing"}

    class Page:
        next_page = None

        def __iter__(self):
            return iter([Row()])

    class RateCards:
        def list(self, **kwargs):
            assert kwargs["limit"] == 25
            assert kwargs["body"] == {}
            return Page()

    class Contracts:
        rate_cards = RateCards()

    class V1:
        contracts = Contracts()

    class Client:
        v1 = V1()

    adapter = MetronomeAdapter(client=Client())
    items, nxt = adapter.list_rate_cards_page(limit=25)
    assert items == [{"id": "rc-1", "name": "Default pricing"}]
    assert nxt is None


def test_list_billable_metrics_page():
    class Row:
        def to_dict(self):
            return {"id": "metric-1", "name": "events"}

    class Page:
        next_page = "cursor-2"

        def __iter__(self):
            return iter([Row()])

    class BillableMetrics:
        def list(self, **kwargs):
            assert kwargs["limit"] == 50
            assert kwargs["include_archived"] is True
            return Page()

    class V1:
        billable_metrics = BillableMetrics()

    class Client:
        v1 = V1()

    adapter = MetronomeAdapter(client=Client())
    items, nxt = adapter.list_billable_metrics_page(
        limit=50,
        include_archived=True,
    )
    assert items == [{"id": "metric-1", "name": "events"}]
    assert nxt == "cursor-2"


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


def test_format_metronome_usage_timestamp_datetime_truncates_to_millis():
    dt = datetime(2025, 4, 30, 12, 0, 0, 661083, tzinfo=UTC)
    assert format_metronome_usage_timestamp(dt) == "2025-04-30T12:00:00.661Z"


def test_format_metronome_usage_timestamp_string_with_offset_and_micros():
    s = "2025-04-30T12:00:00.661083+00:00"
    assert format_metronome_usage_timestamp(s) == "2025-04-30T12:00:00.661Z"


def test_format_metronome_usage_timestamp_z_suffix_no_fraction():
    assert (
        format_metronome_usage_timestamp("2025-04-30T12:00:00Z")
        == "2025-04-30T12:00:00Z"
    )


def test_format_metronome_usage_timestamp_naive_assumed_utc():
    dt = datetime(2025, 4, 30, 12, 0, 0)
    assert format_metronome_usage_timestamp(dt) == "2025-04-30T12:00:00Z"


def test_format_metronome_usage_timestamp_rejects_empty():
    with pytest.raises(ValueError, match="non-empty"):
        format_metronome_usage_timestamp("  ")


def test_normalize_metronome_usage_window_bound_truncates_to_utc_midnight():
    dt = datetime(2025, 4, 30, 15, 30, 45, 123456, tzinfo=UTC)
    assert normalize_metronome_usage_window_bound(dt) == "2025-04-30T00:00:00Z"


def test_normalize_metronome_usage_window_bound_string_offsets():
    assert (
        normalize_metronome_usage_window_bound("2025-05-01T02:00:00+09:00")
        == "2025-04-30T00:00:00Z"
    )
