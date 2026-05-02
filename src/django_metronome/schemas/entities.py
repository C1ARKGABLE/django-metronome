from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field

from .common import IsoTimestamp, MetronomeIdentifier, MetronomeSchema


class CustomerWriteSchema(MetronomeSchema):
    id: MetronomeIdentifier
    name: str | None = None
    ingest_aliases: list[str] = Field(default_factory=list)
    archived_at: IsoTimestamp | None = None
    livemode: bool = False


class ContractWriteSchema(MetronomeSchema):
    id: MetronomeIdentifier
    customer_id: MetronomeIdentifier | None = None
    status: str | None = None
    starting_at: IsoTimestamp | None = None
    ending_before: IsoTimestamp | None = None
    livemode: bool = False


class RateCardWriteSchema(MetronomeSchema):
    id: MetronomeIdentifier
    name: str | None = None
    description: str | None = None
    aliases: list[Any] = Field(default_factory=list)
    archived_at: IsoTimestamp | None = None


class InvoiceWriteSchema(MetronomeSchema):
    id: MetronomeIdentifier
    customer_id: MetronomeIdentifier | None = None
    status: str | None = None
    total: Decimal | float | int | str | dict[str, Any] | None = None
    currency: str | None = None
    start_timestamp: IsoTimestamp | None = None
    end_timestamp: IsoTimestamp | None = None
    issued_at: IsoTimestamp | None = None


class UsageAggregateWriteSchema(MetronomeSchema):
    """Slice for ``v1.usage.list`` / ``v1.usage.list_with_groups`` payloads."""

    customer_id: MetronomeIdentifier | None = None
    event_type: str | None = None
    billable_metric_id: str | None = None
    billable_metric_name: str | None = None
    window_size: str | None = None
    start_timestamp: IsoTimestamp | None = None
    end_timestamp: IsoTimestamp | None = None
    starting_on: IsoTimestamp | None = None
    ending_before: IsoTimestamp | None = None
    value: Decimal | float | int | str | None = None
    groups: dict[str, Any] | None = None


class RateLineWriteSchema(MetronomeSchema):
    """Single schedule row from ``v1/contract-pricing/rate-cards/getRates``."""

    product_id: MetronomeIdentifier
    product_name: str | None = None
    starting_at: IsoTimestamp
    ending_before: IsoTimestamp | None = None
    pricing_group_values: dict[str, str] | None = None
