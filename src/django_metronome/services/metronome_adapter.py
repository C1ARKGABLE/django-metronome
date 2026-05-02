from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from metronome import Metronome, omit

from django_metronome.client import build_metronome_client


def format_metronome_usage_timestamp(value: str | datetime) -> str:
    """
    Wire format for ``v1.usage.list`` body timestamps.

    Metronome rejects ISO strings with microsecond precision and ``+00:00``;
    accepted shapes are ``yyyy-MM-dd'T'HH:mm:ssZ`` or ``yyyy-MM-dd'T'HH:mm:ss.SSSZ``.
    """

    if isinstance(value, datetime):
        dt = value
    else:
        s = value.strip()
        if not s:
            raise ValueError("usage window timestamp must be non-empty")
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    ms = dt.microsecond // 1000
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if ms:
        return f"{base}.{ms:03d}Z"
    return f"{base}Z"


def normalize_metronome_usage_window_bound(value: str | datetime) -> str:
    """
    Normalize ``starting_on`` / ``ending_before`` for ``v1.usage.list``.

    Metronome returns 400 unless both bounds fall on UTC midnight
    (``yyyy-MM-dd'T'00:00:00Z``).
    """

    if isinstance(value, datetime):
        dt = value
    else:
        s = value.strip()
        if not s:
            raise ValueError("usage window timestamp must be non-empty")
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return format_metronome_usage_timestamp(dt)


def _optional_cursor(next_page: str | None) -> str | object:
    """Use ``omit`` for absent cursors (SDK contract), not ``None``."""
    return next_page if next_page else omit


class MetronomeApiVersion(StrEnum):
    V1 = "v1"
    V2 = "v2"


class MetronomeAdapter:
    """
    Anti-corruption boundary for all Metronome SDK access.

    Keep SDK-specific surface area in this class so the rest of the
    Django app can depend on stable plain-Python data structures.
    """

    def __init__(self, client: Metronome | None = None) -> None:
        self._client = client or build_metronome_client()

    @property
    def client(self) -> Metronome:
        return self._client

    def version_resource(self, version: MetronomeApiVersion) -> Any:
        if version == MetronomeApiVersion.V1:
            return self._client.v1
        if version == MetronomeApiVersion.V2:
            return self._client.v2
        raise ValueError(f"Unsupported Metronome API version: {version}")

    def collect_paginated(
        self,
        loader: Callable[..., Iterable[Any]],
        /,
        **kwargs: Any,
    ) -> list[Any]:
        """
        Normalize SDK pagination to a concrete list.

        The provided loader should return an iterable (sync iterator, page
        iterator, or plain list) from the Metronome SDK.
        """

        return list(loader(**kwargs))

    def retrieve_customer(self, customer_id: str) -> dict[str, Any]:
        """
        Retrieve and normalize a customer payload from Metronome.
        """

        response = self._client.v1.customers.retrieve(customer_id=customer_id)
        return dict(response.data.to_dict())

    @staticmethod
    def _to_dict(item: Any) -> dict[str, Any]:
        if hasattr(item, "to_dict"):
            return dict(item.to_dict())
        if isinstance(item, dict):
            return item
        return dict(item.__dict__)

    def list_customers_page(
        self, *, limit: int = 100, next_page: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        response = self._client.v1.customers.list(
            limit=limit,
            next_page=_optional_cursor(next_page),
        )
        items = [self._to_dict(item) for item in response]
        return items, getattr(response, "next_page", None)

    def list_billable_metrics_page(
        self,
        *,
        limit: int = 100,
        next_page: str | None = None,
        include_archived: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """One page of ``v1.billable_metrics.list`` as plain dicts."""

        response = self._client.v1.billable_metrics.list(
            limit=limit,
            next_page=_optional_cursor(next_page),
            include_archived=include_archived,
        )
        items = [self._to_dict(item) for item in response]
        return items, getattr(response, "next_page", None)

    def list_contracts_page(
        self,
        *,
        customer_id: str,
        limit: int = 100,  # kept for interface parity
        next_page: str | None = None,  # v2 endpoint currently does not expose cursoring
    ) -> tuple[list[dict[str, Any]], str | None]:
        _ = limit
        _ = next_page
        response = self._client.v2.contracts.list(customer_id=customer_id)
        data = getattr(response, "data", response)
        items = [self._to_dict(item) for item in data]
        return items, getattr(response, "next_page", None)

    def list_rate_cards_page(
        self, *, limit: int = 100, next_page: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        # MCP: rate-cards list expects a JSON body; omitting it breaks parsing.
        # Metronome may respond with "Unknown error parsing request body".
        response = self._client.v1.contracts.rate_cards.list(
            limit=limit,
            next_page=_optional_cursor(next_page),
            body={},
        )
        items = [self._to_dict(item) for item in response]
        return items, getattr(response, "next_page", None)

    def create_rate_card(self, **params: Any) -> str:
        """
        Create a rate card in Metronome (``v1.contracts.rate_cards.create``).

        Metronome assigns the canonical ``id`` in the response ``data``; callers
        should persist it via ``upsert_rate_card`` after ``retrieve``, or run sync.
        """

        response = self._client.v1.contracts.rate_cards.create(**params)
        data = getattr(response, "data", None)
        if data is None:
            raise ValueError("rate_cards.create returned empty data")
        rid = getattr(data, "id", None)
        if rid is not None:
            return str(rid)
        if isinstance(data, dict) and "id" in data:
            return str(data["id"])
        return str(data)

    def list_invoices_page(
        self,
        *,
        customer_id: str,
        limit: int = 100,
        next_page: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        response = self._client.v1.customers.invoices.list(
            customer_id=customer_id,
            limit=limit,
            next_page=_optional_cursor(next_page),
        )
        items = [self._to_dict(item) for item in response]
        return items, getattr(response, "next_page", None)

    def list_usage_page(
        self,
        *,
        starting_on: str | datetime,
        ending_before: str | datetime,
        window_size: str = "day",
        next_page: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        response = self._client.v1.usage.list(
            starting_on=normalize_metronome_usage_window_bound(starting_on),
            ending_before=normalize_metronome_usage_window_bound(ending_before),
            window_size=window_size.upper(),
            next_page=_optional_cursor(next_page),
        )
        items = [self._to_dict(item) for item in response]
        return items, getattr(response, "next_page", None)

    def list_usage_with_groups_page(
        self,
        *,
        billable_metric_id: str,
        customer_id: str,
        window_size: str,
        limit: int = 100,
        next_page: str | None = None,
        starting_on: str | datetime | None = None,
        ending_before: str | datetime | None = None,
        group_key: list[str] | None = None,
        group_filters: dict[str, list[str]] | None = None,
        current_period: bool | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        ws = window_size.strip().upper()
        if ws not in {"HOUR", "DAY", "NONE"}:
            ws = "DAY"

        kwargs: dict[str, Any] = {
            "billable_metric_id": billable_metric_id,
            "customer_id": customer_id,
            "window_size": ws,
            "limit": limit,
            "next_page": _optional_cursor(next_page),
        }
        if starting_on is not None:
            kwargs["starting_on"] = starting_on
        if ending_before is not None:
            kwargs["ending_before"] = ending_before
        if group_key:
            kwargs["group_key"] = group_key
        if group_filters:
            kwargs["group_filters"] = group_filters
        if current_period is not None:
            kwargs["current_period"] = current_period

        response = self._client.v1.usage.list_with_groups(**kwargs)
        items = [self._to_dict(item) for item in response]
        return items, getattr(response, "next_page", None)

    def list_rates_page(
        self,
        *,
        rate_card_id: str,
        at: str | datetime,
        limit: int = 100,
        next_page: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        response = self._client.v1.contracts.rate_cards.rates.list(
            rate_card_id=rate_card_id,
            at=at,
            limit=limit,
            next_page=_optional_cursor(next_page),
        )
        items = [self._to_dict(item) for item in response]
        return items, getattr(response, "next_page", None)

    def create_customer(self, **params: Any) -> dict[str, Any]:
        """``v1.customers.create``; returns normalized customer dict."""

        response = self._client.v1.customers.create(**params)
        return self._to_dict(response.data)

    def set_customer_ingest_aliases(
        self,
        *,
        customer_id: str,
        ingest_aliases: list[str],
    ) -> None:
        """Replace ingest aliases (``v1`` setIngestAliases)."""

        self._client.v1.customers.set_ingest_aliases(
            customer_id=customer_id,
            ingest_aliases=ingest_aliases,
        )

    def create_contract(self, **params: Any) -> str:
        """Create a contract via ``v1.contracts.create``; returns new contract id."""

        response = self._client.v1.contracts.create(**params)
        return str(response.data.id)

    def retrieve_contract(
        self,
        *,
        contract_id: str,
        customer_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """``v2.contracts.retrieve`` for mirror reconciliation."""

        response = self._client.v2.contracts.retrieve(
            contract_id=contract_id,
            customer_id=customer_id,
            **kwargs,
        )
        return self._to_dict(response.data)

    def retrieve_rate_card(self, *, rate_card_id: str) -> dict[str, Any]:
        """Rate card header via ``v1.contracts.rate_cards.retrieve`` (no lines)."""

        response = self._client.v1.contracts.rate_cards.retrieve(id=rate_card_id)
        data = getattr(response, "data", None)
        if data is None:
            raise ValueError("rate_cards.retrieve returned empty data")
        return self._to_dict(data)

    def add_rate(self, **params: Any) -> dict[str, Any]:
        """Add a single rate schedule row (``v1`` addRate)."""

        response = self._client.v1.contracts.rate_cards.rates.add(**params)
        return self._to_dict(response)

    def add_rates_many(self, **params: Any) -> dict[str, Any]:
        """Bulk-add rates (``v1`` addRates)."""

        response = self._client.v1.contracts.rate_cards.rates.add_many(**params)
        return self._to_dict(response)

    def archive_customer(self, *, customer_id: str) -> None:
        """Archive a customer (``v1.customers.archive``)."""

        self._client.v1.customers.archive(id=customer_id)

    def archive_contract(
        self,
        *,
        contract_id: str,
        customer_id: str,
        void_invoices: bool = False,
    ) -> None:
        """Archive a contract (``v1.contracts.archive``)."""

        self._client.v1.contracts.archive(
            contract_id=contract_id,
            customer_id=customer_id,
            void_invoices=void_invoices,
        )

    def archive_rate_card(self, *, rate_card_id: str) -> None:
        """Archive a rate card (``v1.contracts.rate_cards.archive``)."""

        self._client.v1.contracts.rate_cards.archive(id=rate_card_id)

    def create_usage_product(self, *, name: str, billable_metric_id: str) -> str:
        """Create a USAGE product; returns Metronome product id."""

        response = self._client.v1.contracts.products.create(
            name=name,
            type="USAGE",
            billable_metric_id=billable_metric_id,
        )
        return str(response.data.id)

    def retrieve_product(self, *, product_id: str) -> dict[str, Any]:
        """Normalize ``v1.contracts.products.retrieve``."""

        response = self._client.v1.contracts.products.retrieve(id=product_id)
        return self._to_dict(response.data)

    def archive_product(self, *, product_id: str) -> None:
        """Archive a product (``v1.contracts.products.archive``)."""

        self._client.v1.contracts.products.archive(product_id=product_id)
