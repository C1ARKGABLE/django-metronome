from __future__ import annotations

import httpx
import pytest
from django.utils import timezone
from metronome import ConflictError

from django_metronome.models import MetronomeCustomer
from django_metronome.schemas.provisioning import (
    ContractCreateRequest,
    CustomerCreateRequest,
    RateAddRequest,
    RateCardCreateRequest,
)
from django_metronome.services.errors import (
    MetronomeProvisioningError,
    translate_sdk_exception,
)
from django_metronome.services.provisioning import (
    provision_contract,
    provision_customer,
    provision_rate_card_with_rates,
    update_customer_ingest_aliases,
)


def test_translate_conflict_maps_to_provisioning_error():
    req = httpx.Request("POST", "https://api.metronome.com/v1/foo")
    resp = httpx.Response(409, request=req)
    inner = ConflictError("duplicate", response=resp, body={"detail": "exists"})
    outer = translate_sdk_exception(inner)
    assert isinstance(outer, MetronomeProvisioningError)
    assert "conflict" in str(outer).lower()


@pytest.mark.django_db
def test_provision_customer_reconciles_from_retrieve():
    class FakeAdapter:
        def create_customer(self, **kwargs):
            _ = kwargs
            return {
                "id": "cust-new",
                "name": "Acme",
                "ingest_aliases": ["a"],
                "livemode": False,
            }

        def retrieve_customer(self, customer_id):
            assert customer_id == "cust-new"
            return {
                "id": "cust-new",
                "name": "Acme",
                "ingest_aliases": ["a"],
                "livemode": False,
                "archived_at": None,
            }

    req = CustomerCreateRequest(name="Acme", ingest_aliases=["a"])
    row = provision_customer(adapter=FakeAdapter(), environment="sandbox", request=req)
    assert isinstance(row, MetronomeCustomer)
    assert row.metronome_id == "cust-new"
    assert row.name == "Acme"


@pytest.mark.django_db
def test_update_customer_ingest_aliases_requires_existing_mirror_customer():
    MetronomeCustomer.objects.create(
        metronome_id="c1",
        metronome_environment="sandbox",
        name="Old",
    )

    class FakeAdapter:
        def set_customer_ingest_aliases(self, *, customer_id, ingest_aliases):
            assert customer_id == "c1"
            assert ingest_aliases == ["alias1"]

        def retrieve_customer(self, customer_id):
            return {
                "id": customer_id,
                "name": "Old",
                "ingest_aliases": ["alias1"],
                "livemode": False,
                "archived_at": None,
            }

    row = update_customer_ingest_aliases(
        adapter=FakeAdapter(),
        environment="sandbox",
        customer_id="c1",
        ingest_aliases=["alias1"],
    )
    assert row.ingest_aliases == ["alias1"]


@pytest.mark.django_db
def test_provision_contract_calls_v2_retrieve_for_mirror():
    MetronomeCustomer.objects.create(
        metronome_id="cust-1",
        metronome_environment="sandbox",
        name="Buyer",
    )

    class FakeAdapter:
        def create_contract(self, **kwargs):
            assert kwargs["customer_id"] == "cust-1"
            return "ctr_99"

        def retrieve_contract(self, *, contract_id, customer_id):
            assert contract_id == "ctr_99"
            assert customer_id == "cust-1"
            return {
                "id": "ctr_99",
                "customer_id": "cust-1",
                "status": "active",
                "starting_at": "2026-01-01T00:00:00Z",
                "ending_before": None,
                "livemode": False,
            }

    req = ContractCreateRequest(
        customer_id="cust-1",
        starting_at="2026-01-01T00:00:00Z",
    )
    row = provision_contract(adapter=FakeAdapter(), environment="sandbox", request=req)
    assert row.metronome_id == "ctr_99"
    assert row.customer.metronome_id == "cust-1"


@pytest.mark.django_db
def test_provision_rate_card_with_rates_lists_schedule():
    now = timezone.now()

    class FakeAdapter:
        def __init__(self):
            self.add_calls = []

        def create_rate_card(self, **kwargs):
            assert kwargs["name"] == "Standard"
            return "rc_1"

        def retrieve_rate_card(self, *, rate_card_id):
            assert rate_card_id == "rc_1"
            return {"id": "rc_1", "name": "Standard", "description": "", "aliases": []}

        def add_rate(self, **kwargs):
            self.add_calls.append(kwargs)
            assert kwargs["rate_card_id"] == "rc_1"

        def list_rates_page(self, *, rate_card_id, at, limit=100, next_page=None):
            _ = at, limit
            assert rate_card_id == "rc_1"
            if not next_page:
                return (
                    [
                        {
                            "product_id": "prod_x",
                            "product_name": "X",
                            "starting_at": now.isoformat(),
                            "ending_before": None,
                            "pricing_group_values": {},
                            "rate": {},
                        }
                    ],
                    None,
                )
            return ([], None)

    adapter = FakeAdapter()
    card = RateCardCreateRequest(name="Standard")
    rates = [
        RateAddRequest(
            product_id="prod_x",
            rate_type="FLAT",
            starting_at=now,
            price=1.0,
            entitled=True,
        )
    ]
    rc, n = provision_rate_card_with_rates(
        adapter=adapter,
        environment="sandbox",
        card=card,
        rates=rates,
        rates_at=now,
    )
    assert rc.metronome_id == "rc_1"
    assert n == 1
    assert len(adapter.add_calls) == 1
