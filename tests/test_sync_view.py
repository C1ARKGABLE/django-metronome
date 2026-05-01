import pytest
from django.test import Client


@pytest.mark.django_db
def test_sync_customer_returns_503_when_integration_disabled(settings):
    settings.METRONOME_API_KEY = None

    client = Client()
    response = client.post("/sync/customers/customer_123/")

    assert response.status_code == 503
    assert response.json()["detail"].startswith("Metronome integration disabled")


@pytest.mark.django_db
def test_sync_customer_returns_payload_when_enabled(settings, monkeypatch):
    settings.METRONOME_API_KEY = "mtr_test_key"
    settings.METRONOME_ENV = "sandbox"

    class FakeAdapter:
        def retrieve_customer(self, customer_id: str):
            assert customer_id == "customer_123"
            return {"id": "customer_123", "name": "Acme"}

    monkeypatch.setattr("django_metronome.views.MetronomeAdapter", FakeAdapter)

    client = Client()
    response = client.post("/sync/customers/customer_123/")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "customer_id": "customer_123",
        "environment": "sandbox",
        "payload": {"id": "customer_123", "name": "Acme"},
    }
