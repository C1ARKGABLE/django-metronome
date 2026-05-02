"""
Phase 1.5 provisioning: validate requests, adapter writes, mirror reconcile.

Use Metronome idempotency keys (e.g. ``uniqueness_key``) where supported;
otherwise ``409`` conflicts raise ``MetronomeProvisioningError`` without mirror
writes. After success, mirror rows come only from retrieve / schedule reads,
not optimistic payloads alone.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from django.utils import timezone
from metronome import MetronomeError

from django_metronome.models import (
    MetronomeContract,
    MetronomeCustomer,
    MetronomeRateCard,
)
from django_metronome.schemas.provisioning import (
    ContractCreateRequest,
    CustomerCreateRequest,
    RateAddRequest,
    RateCardCreateRequest,
    rate_card_create_sdk_kwargs,
)
from django_metronome.services.errors import (
    MetronomeProvisioningError,
    translate_sdk_exception,
)
from django_metronome.services.metronome_adapter import MetronomeAdapter
from django_metronome.services.sync import (
    upsert_contract,
    upsert_customer,
    upsert_rate_card,
    upsert_rate_line,
)

logger = logging.getLogger(__name__)


def provision_customer(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    request: CustomerCreateRequest,
) -> MetronomeCustomer:
    """Create a customer in Metronome and upsert the mirror from ``retrieve``."""

    payload = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")
    try:
        logger.info(
            "metronome.provision.customer.create",
            extra={"environment": environment},
        )
        created = adapter.create_customer(**payload)
        cid = created.get("id")
        if not cid:
            raise MetronomeProvisioningError("Customer create response missing id")
        fresh = adapter.retrieve_customer(str(cid))
        return upsert_customer(fresh, environment=environment)
    except MetronomeError as exc:
        raise translate_sdk_exception(exc) from exc


def update_customer_ingest_aliases(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    customer_id: str,
    ingest_aliases: list[str],
) -> MetronomeCustomer:
    """Replace ingest aliases then refresh the mirror from ``retrieve``."""

    try:
        logger.info(
            "metronome.provision.customer.set_ingest_aliases",
            extra={"environment": environment, "customer_id": customer_id},
        )
        adapter.set_customer_ingest_aliases(
            customer_id=customer_id,
            ingest_aliases=ingest_aliases,
        )
        fresh = adapter.retrieve_customer(customer_id)
        return upsert_customer(fresh, environment=environment)
    except MetronomeError as exc:
        raise translate_sdk_exception(exc) from exc


def provision_contract(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    request: ContractCreateRequest,
) -> MetronomeContract:
    """``v1.contracts.create`` then mirror reconcile via ``v2.contracts.retrieve``."""

    payload = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")
    customer_id = request.customer_id
    try:
        logger.info(
            "metronome.provision.contract.create",
            extra={"environment": environment, "customer_id": customer_id},
        )
        contract_id = adapter.create_contract(**payload)
        mirror_payload = adapter.retrieve_contract(
            contract_id=contract_id,
            customer_id=customer_id,
        )
        return upsert_contract(mirror_payload, environment=environment)
    except MetronomeError as exc:
        raise translate_sdk_exception(exc) from exc


def provision_rate_card_with_rates(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    card: RateCardCreateRequest,
    rates: Sequence[RateAddRequest],
    rates_at: datetime | None = None,
) -> tuple[MetronomeRateCard, int]:
    """Create card + ``rates.add``, then mirror lines via ``getRates`` pagination."""

    snapshot_at = rates_at or timezone.now()
    card_kw = rate_card_create_sdk_kwargs(card)
    try:
        logger.info(
            "metronome.provision.rate_card.create",
            extra={"environment": environment},
        )
        rate_card_id = adapter.create_rate_card(**card_kw)
        header = adapter.retrieve_rate_card(rate_card_id=rate_card_id)
        card_obj = upsert_rate_card(header, environment=environment)

        for rate in rates:
            r_kw = rate.model_dump(exclude_none=True, exclude_unset=True, mode="json")
            r_kw["rate_card_id"] = rate_card_id
            adapter.add_rate(**r_kw)

        lines = 0
        cursor: str | None = None
        while True:
            items, next_c = adapter.list_rates_page(
                rate_card_id=rate_card_id,
                at=snapshot_at,
                next_page=cursor,
            )
            for item in items:
                upsert_rate_line(card_obj, item)
                lines += 1
            if not next_c:
                break
            cursor = next_c

        logger.info(
            "metronome.provision.rate_card.done",
            extra={
                "environment": environment,
                "rate_card_id": rate_card_id,
                "rate_lines": lines,
            },
        )
        return card_obj, lines
    except MetronomeError as exc:
        raise translate_sdk_exception(exc) from exc
