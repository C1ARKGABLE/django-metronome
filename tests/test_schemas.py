from django_metronome.schemas.entities import (
    ContractWriteSchema,
    CustomerWriteSchema,
    InvoiceWriteSchema,
    RateCardWriteSchema,
)
from django_metronome.schemas.webhooks import WebhookEnvelopeSchema


def test_webhook_schema_tolerates_unknown_fields():
    payload = {
        "id": "evt_123",
        "event_type": "customer.updated",
        "livemode": False,
        "data": {"id": "customer_123"},
        "future_field": {"new_shape": True},
    }

    parsed = WebhookEnvelopeSchema.model_validate(payload)

    assert parsed.id == "evt_123"
    assert parsed.data["id"] == "customer_123"
    assert parsed.unknown_fields["future_field"] == {"new_shape": True}


def test_entity_write_schemas_capture_unknown_fields():
    customer = CustomerWriteSchema.model_validate(
        {
            "id": "customer_1",
            "name": "Acme",
            "ingest_aliases": ["acme"],
            "new_customer_field": "arr-v2",
        }
    )
    contract = ContractWriteSchema.model_validate(
        {
            "id": "contract_1",
            "customer_id": "customer_1",
            "status": "active",
            "new_contract_field": {"source": "backfill"},
        }
    )

    assert customer.unknown_fields["new_customer_field"] == "arr-v2"
    assert contract.unknown_fields["new_contract_field"] == {"source": "backfill"}


def test_contract_write_schema_allows_missing_customer_id():
    parsed = ContractWriteSchema.model_validate({"id": "contract_x", "status": "draft"})
    assert parsed.customer_id is None


def test_invoice_and_rate_card_schemas_roundtrip_unknown_fields():
    inv = InvoiceWriteSchema.model_validate(
        {
            "id": "inv_1",
            "customer_id": "cust_1",
            "total": "10.50",
            "currency": "USD",
            "invoice_extra": True,
        }
    )
    assert inv.id == "inv_1"
    assert inv.unknown_fields["invoice_extra"] is True

    rc = RateCardWriteSchema.model_validate(
        {"id": "rc_1", "name": "Standard", "aliases": ["std"], "rc_extra": [1, 2]}
    )
    assert rc.name == "Standard"
    assert rc.unknown_fields["rc_extra"] == [1, 2]
