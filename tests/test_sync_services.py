from datetime import timedelta

import pytest
from django.utils import timezone

from django_metronome.models import (
    MetronomeContract,
    MetronomeCustomer,
    MetronomeInvoice,
    MetronomeUsageAggregate,
    SyncCheckpoint,
)
from django_metronome.services.sync import (
    sync_contracts,
    sync_customers,
    sync_rate_cards,
    sync_usage,
    sync_usage_with_groups,
    upsert_customer,
    upsert_usage_aggregate,
)


@pytest.mark.django_db
def test_sync_customers_handles_pagination_and_checkpoint_resume():
    now = timezone.now()

    class FakeAdapter:
        def __init__(self):
            self.calls = []

        def list_customers_page(self, *, limit, next_page):
            self.calls.append(next_page)
            if not next_page:
                return (
                    [
                        {
                            "id": "customer_1",
                            "name": "Acme",
                            "ingest_aliases": ["acme"],
                            "archived_at": None,
                            "livemode": False,
                            "created_at": now.isoformat(),
                            "updated_at": now.isoformat(),
                        }
                    ],
                    "cursor_1",
                )
            return (
                [
                    {
                        "id": "customer_2",
                        "name": "Globex",
                        "ingest_aliases": ["globex"],
                        "archived_at": None,
                        "livemode": False,
                        "created_at": now.isoformat(),
                        "updated_at": now.isoformat(),
                    }
                ],
                None,
            )

    adapter = FakeAdapter()
    summary = sync_customers(adapter=adapter, environment="sandbox", limit=1)

    assert summary["processed"] == 2
    assert MetronomeCustomer.objects.count() == 2
    checkpoint = SyncCheckpoint.objects.get(
        entity="customers", metronome_environment="sandbox"
    )
    assert checkpoint.status == "ok"
    assert checkpoint.cursor == ""
    assert checkpoint.metadata == {}
    assert adapter.calls == [None, "cursor_1"]


@pytest.mark.django_db
def test_upsert_customer_is_idempotent_and_keeps_unknown_fields():
    payload = {
        "id": "customer_1",
        "name": "Acme",
        "ingest_aliases": ["acme"],
        "livemode": False,
        "future_field": {"shape": "v2"},
    }

    upsert_customer(payload, environment="sandbox")
    upsert_customer(payload, environment="sandbox")

    assert MetronomeCustomer.objects.count() == 1
    row = MetronomeCustomer.objects.get()
    assert row.raw_payload["future_field"] == {"shape": "v2"}


@pytest.mark.django_db
def test_contract_and_invoice_query_helpers():
    customer = MetronomeCustomer.objects.create(
        metronome_id="customer_1",
        metronome_environment="sandbox",
        name="Acme",
    )
    now = timezone.now()
    active_contract = MetronomeContract.objects.create(
        metronome_id="contract_active",
        metronome_environment="sandbox",
        customer=customer,
        status="active",
        starting_at=now - timedelta(days=1),
        ending_before=now + timedelta(days=30),
    )
    MetronomeContract.objects.create(
        metronome_id="contract_old",
        metronome_environment="sandbox",
        customer=customer,
        status="ended",
        starting_at=now - timedelta(days=60),
        ending_before=now - timedelta(days=2),
    )

    MetronomeInvoice.objects.create(
        metronome_id="inv_1",
        metronome_environment="sandbox",
        customer=customer,
        status="draft",
        total=100,
        start_timestamp=now - timedelta(days=7),
    )
    MetronomeInvoice.objects.create(
        metronome_id="inv_2",
        metronome_environment="sandbox",
        customer=customer,
        status="issued",
        total=150,
        start_timestamp=now - timedelta(days=1),
    )

    current = MetronomeContract.objects.current_for_customer(customer)
    issued = list(
        MetronomeInvoice.objects.timeline_for_customer(customer, statuses=["issued"])
    )

    assert current == active_contract
    assert [inv.metronome_id for inv in issued] == ["inv_2"]


@pytest.mark.django_db
def test_upsert_usage_aggregate_accepts_null_value_and_metric_timestamps():
    MetronomeCustomer.objects.create(
        metronome_id="c6dca996-f549-4ba5-90a0-855ac95a5031",
        metronome_environment="sandbox",
        name="Acme",
    )
    payload = {
        "customer_id": "c6dca996-f549-4ba5-90a0-855ac95a5031",
        "billable_metric_name": "output_tokens",
        "start_timestamp": "2026-04-26T00:00:00+00:00",
        "end_timestamp": "2026-04-27T00:00:00+00:00",
        "value": None,
    }
    upsert_usage_aggregate(payload, environment="sandbox")
    row = MetronomeUsageAggregate.objects.get()
    assert row.value == 0
    assert row.event_type == "output_tokens"
    assert row.window_start.isoformat().startswith("2026-04-26")
    assert row.window_end.isoformat().startswith("2026-04-27")


@pytest.mark.django_db
def test_sync_contracts_resumes_failed_checkpoint():
    MetronomeCustomer.objects.create(
        metronome_id="c1",
        metronome_environment="sandbox",
        name="A",
    )

    class FakeAdapter:
        def __init__(self):
            self.calls: list[tuple[str | None, str | None]] = []

        def list_contracts_page(self, *, customer_id, limit, next_page):
            self.calls.append((customer_id, next_page))
            if customer_id == "c1" and not next_page:
                return (
                    [{"id": "ct1", "customer_id": "c1", "status": "active"}],
                    "page2",
                )
            if customer_id == "c1" and next_page == "page2":
                return ([{"id": "ct2", "customer_id": "c1", "status": "active"}], None)
            return ([], None)

    SyncCheckpoint.objects.create(
        entity="contracts",
        metronome_environment="sandbox",
        status="failed",
        cursor="page2",
        metadata={"customer_metronome_id": "c1"},
    )

    adapter = FakeAdapter()
    summary = sync_contracts(adapter=adapter, environment="sandbox", limit=50)

    assert summary["processed"] == 1
    assert MetronomeContract.objects.filter(metronome_id="ct2").exists()
    cp = SyncCheckpoint.objects.get(entity="contracts", metronome_environment="sandbox")
    assert cp.status == "ok"
    assert cp.cursor == ""
    assert cp.metadata == {}
    assert adapter.calls == [("c1", "page2")]


@pytest.mark.django_db
def test_sync_usage_persists_window_and_clears_cursor_on_success():
    class FakeAdapter:
        def __init__(self):
            base = {
                "billable_metric_name": "api",
                "window_size": "day",
            }
            self.pages = [
                [
                    {
                        **base,
                        "customer_id": "x",
                        "start_timestamp": "2026-04-01T00:00:00Z",
                        "end_timestamp": "2026-04-02T00:00:00Z",
                        "value": 1,
                    }
                ],
                [
                    {
                        **base,
                        "customer_id": "y",
                        "start_timestamp": "2026-04-02T00:00:00Z",
                        "end_timestamp": "2026-04-03T00:00:00Z",
                        "value": 2,
                    }
                ],
            ]

        def list_usage_page(
            self, *, starting_on, ending_before, window_size, next_page
        ):
            _ = starting_on, ending_before, window_size
            if next_page == "p1":
                return self.pages[1], None
            return self.pages[0], "p1"

    adapter = FakeAdapter()
    summary = sync_usage(
        adapter=adapter,
        environment="sandbox",
        starting_on="2026-04-01T00:00:00Z",
        ending_before="2026-04-08T00:00:00Z",
        window_size="day",
    )

    assert summary["processed"] == 2
    cp = SyncCheckpoint.objects.get(entity="usage", metronome_environment="sandbox")
    assert cp.status == "ok"
    assert cp.cursor == ""
    assert "starting_on" in (cp.metadata or {})


@pytest.mark.django_db
def test_sync_rate_cards_cards_phase_then_rates():
    class FakeAdapter:
        def __init__(self):
            self.rate_calls: list[str | None] = []

        def list_rate_cards_page(self, *, limit, next_page):
            _ = limit
            if not next_page:
                return ([{"id": "rc1", "name": "Card"}], None)
            return ([], None)

        def list_rates_page(self, *, rate_card_id, at, limit, next_page):
            _ = at, limit
            self.rate_calls.append(next_page)
            if not next_page:
                return (
                    [
                        {
                            "product_id": "prod_a",
                            "product_name": "A",
                            "starting_at": "2026-01-01T00:00:00Z",
                            "ending_before": None,
                            "pricing_group_values": {},
                        }
                    ],
                    None,
                )
            return ([], None)

    from django_metronome.models import MetronomeRate

    adapter = FakeAdapter()
    summary = sync_rate_cards(adapter=adapter, environment="sandbox", limit=50)

    assert summary["processed"] >= 1
    assert MetronomeRate.objects.filter(
        product_id="prod_a", rate_card__metronome_id="rc1"
    ).exists()
    cp = SyncCheckpoint.objects.get(
        entity="rate_cards", metronome_environment="sandbox"
    )
    assert cp.status == "ok"
    assert cp.metadata == {}


@pytest.mark.django_db
def test_sync_usage_with_groups_fake_adapter():
    MetronomeCustomer.objects.create(
        metronome_id="cust_g",
        metronome_environment="sandbox",
        name="G",
    )

    class FakeAdapter:
        def list_usage_with_groups_page(self, **kwargs):
            _ = kwargs
            return (
                [
                    {
                        "starting_on": "2026-04-01T00:00:00Z",
                        "ending_before": "2026-04-02T00:00:00Z",
                        "value": 3.0,
                        "group": {"region": "us"},
                    }
                ],
                None,
            )

    adapter = FakeAdapter()
    summary = sync_usage_with_groups(
        adapter=adapter,
        environment="sandbox",
        billable_metric_id="metric-1",
        window_size="day",
        starting_on="2026-04-01T00:00:00Z",
        ending_before="2026-04-08T00:00:00Z",
    )

    assert summary["processed"] == 1
    row = MetronomeUsageAggregate.objects.get()
    assert row.event_type == "metric-1"
    assert row.groups == {"region": "us"}
