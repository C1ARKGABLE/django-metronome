"""Phase 1.5 provisioning request payloads (distinct from sync snapshots)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .common import MetronomeIdentifier, MetronomeSchema


class CustomerCreateRequest(MetronomeSchema):
    name: str
    ingest_aliases: list[str] = Field(default_factory=list)
    custom_fields: dict[str, str] | None = None


class ContractCreateRequest(MetronomeSchema):
    """v1 contract-create subset; ``model_extra`` allows extra SDK keys."""

    customer_id: MetronomeIdentifier
    starting_at: datetime | str
    name: str | None = None
    ending_before: datetime | str | None = None
    rate_card_id: MetronomeIdentifier | None = None
    rate_card_alias: str | None = None
    package_id: MetronomeIdentifier | None = None
    package_alias: str | None = None
    uniqueness_key: str | None = None
    custom_fields: dict[str, str] | None = None


class RateCardCreateRequest(MetronomeSchema):
    """Rate card header for ``v1.contracts.rate_cards.create``."""

    name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    fiat_credit_type_id: MetronomeIdentifier | None = None
    custom_fields: dict[str, str] | None = None


class RateAddRequest(MetronomeSchema):
    """One ``rates.add`` row; provisioning injects ``rate_card_id``."""

    entitled: bool = True
    product_id: MetronomeIdentifier
    rate_type: str
    starting_at: datetime | str
    ending_before: datetime | str | None = None
    price: float | None = None
    quantity: float | None = None
    billing_frequency: str | None = None
    credit_type_id: str | None = None
    pricing_group_values: dict[str, str] | None = None
    is_prorated: bool | None = None


def rate_card_create_sdk_kwargs(request: RateCardCreateRequest) -> dict[str, Any]:
    """Turn simple string aliases into SDK ``Alias`` dicts."""

    data = request.model_dump(exclude_none=True, exclude_unset=True, mode="json")
    aliases = data.pop("aliases", None) or []
    if aliases:
        if isinstance(aliases[0], str):
            data["aliases"] = [{"name": a} for a in aliases]
        else:
            data["aliases"] = aliases
    return data
