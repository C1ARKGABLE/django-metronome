from django_metronome.schemas.entities import ContractWriteSchema, CustomerWriteSchema
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
