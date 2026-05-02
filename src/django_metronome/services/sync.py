from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha1
from typing import Any

from django.db import transaction
from django.utils import timezone

from django_metronome.models import (
    MetronomeContract,
    MetronomeCustomer,
    MetronomeInvoice,
    MetronomeRate,
    MetronomeRateCard,
    MetronomeUsageAggregate,
    SyncCheckpoint,
)
from django_metronome.schemas.entities import (
    ContractWriteSchema,
    CustomerWriteSchema,
    InvoiceWriteSchema,
    RateCardWriteSchema,
    RateLineWriteSchema,
    UsageAggregateWriteSchema,
)
from django_metronome.services.metronome_adapter import (
    MetronomeAdapter,
    normalize_metronome_usage_window_bound,
)


def _decimal_safe(value: Any) -> Decimal:
    """Coerce Metronome numeric fields (often nullable) into ``Decimal``."""

    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return Decimal("0")
        try:
            return Decimal(s)
        except InvalidOperation:
            return Decimal("0")
    if isinstance(value, dict):
        for key in ("amount", "value", "total", "quantity"):
            if key in value:
                return _decimal_safe(value[key])
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    return value


def _payload_changed(instance, payload: dict[str, Any]) -> bool:
    return instance.raw_payload != payload


def _get_checkpoint(entity: str, environment: str) -> SyncCheckpoint:
    checkpoint, _ = SyncCheckpoint.objects.get_or_create(
        entity=entity,
        metronome_environment=environment,
        defaults={"status": "idle"},
    )
    return checkpoint


def _reset_sync_checkpoint(entity: str, environment: str) -> SyncCheckpoint:
    SyncCheckpoint.objects.filter(
        entity=entity, metronome_environment=environment
    ).delete()
    return _get_checkpoint(entity, environment)


def _mark_checkpoint_started(checkpoint: SyncCheckpoint, *, cursor: str | None) -> None:
    checkpoint.status = "running"
    checkpoint.cursor = cursor or checkpoint.cursor
    checkpoint.last_attempted_at = timezone.now()
    checkpoint.last_error = ""
    checkpoint.save(
        update_fields=[
            "status",
            "cursor",
            "last_attempted_at",
            "last_error",
            "updated_at",
        ]
    )


def _mark_checkpoint_finished_cleared(checkpoint: SyncCheckpoint) -> None:
    checkpoint.status = "ok"
    checkpoint.cursor = ""
    checkpoint.metadata = {}
    checkpoint.last_error = ""
    checkpoint.last_successful_at = timezone.now()
    checkpoint.save(
        update_fields=[
            "status",
            "cursor",
            "metadata",
            "last_error",
            "last_successful_at",
            "updated_at",
        ]
    )


def _mark_checkpoint_failure(checkpoint: SyncCheckpoint, error: Exception) -> None:
    checkpoint.status = "failed"
    checkpoint.last_error = str(error)
    checkpoint.save(update_fields=["status", "last_error", "updated_at"])


def _persist_contracts_progress(
    checkpoint: SyncCheckpoint, *, customer_metronome_id: str, page_cursor: str
) -> None:
    checkpoint.metadata = {"customer_metronome_id": customer_metronome_id}
    checkpoint.cursor = page_cursor
    checkpoint.save(update_fields=["metadata", "cursor", "updated_at"])


def _usage_window_matches(
    checkpoint: SyncCheckpoint,
    starting_on: str | datetime,
    ending_before: str | datetime,
    window_size: str,
) -> bool:
    try:
        ns = normalize_metronome_usage_window_bound(starting_on)
        ne = normalize_metronome_usage_window_bound(ending_before)
    except ValueError:
        return False
    m = checkpoint.metadata or {}
    return (
        m.get("starting_on") == ns
        and m.get("ending_before") == ne
        and str(m.get("window_size", "")).upper() == window_size.strip().upper()
    )


def _usage_groups_params_match(
    checkpoint: SyncCheckpoint,
    *,
    billable_metric_id: str,
    starting_on: str | datetime | None,
    ending_before: str | datetime | None,
    window_size: str,
    group_key: list[str] | None,
    current_period: bool | None,
) -> bool:
    m = checkpoint.metadata or {}
    if m.get("billable_metric_id") != billable_metric_id:
        return False
    if str(m.get("window_size", "")).upper() != window_size.strip().upper():
        return False
    if (m.get("group_key") or []) != (group_key or []):
        return False
    if bool(m.get("current_period")) != bool(current_period):
        return False
    if bool(current_period):
        return True
    try:
        if starting_on is None or ending_before is None:
            return False
        ns = normalize_metronome_usage_window_bound(starting_on)
        ne = normalize_metronome_usage_window_bound(ending_before)
    except ValueError:
        return False
    return m.get("starting_on") == ns and m.get("ending_before") == ne


@transaction.atomic
def upsert_customer(payload: dict[str, Any], *, environment: str) -> MetronomeCustomer:
    payload_json = _json_safe(payload)
    parsed = CustomerWriteSchema.model_validate(payload)
    defaults = {
        "name": parsed.name or "",
        "ingest_aliases": parsed.ingest_aliases,
        "archived_at": parsed.archived_at,
        "metronome_livemode": parsed.livemode,
        "raw_payload": payload_json,
        "last_synced_at": timezone.now(),
    }
    obj, _ = MetronomeCustomer.objects.get_or_create(
        metronome_id=parsed.id,
        metronome_environment=environment,
        defaults=defaults,
    )
    if _payload_changed(obj, payload_json):
        for key, value in defaults.items():
            setattr(obj, key, value)
        obj.save(update_fields=[*defaults.keys(), "updated_at"])
    return obj


@transaction.atomic
def upsert_contract(payload: dict[str, Any], *, environment: str) -> MetronomeContract:
    payload_json = _json_safe(payload)
    parsed = ContractWriteSchema.model_validate(payload)
    customer = None
    if parsed.customer_id:
        customer = MetronomeCustomer.objects.filter(
            metronome_id=parsed.customer_id,
            metronome_environment=environment,
        ).first()

    defaults = {
        "customer": customer,
        "status": parsed.status or "",
        "starting_at": parsed.starting_at,
        "ending_before": parsed.ending_before,
        "metronome_livemode": parsed.livemode,
        "raw_payload": payload_json,
        "rate_card_id": str(payload.get("rate_card_id", "")),
        "last_synced_at": timezone.now(),
    }
    obj, _ = MetronomeContract.objects.get_or_create(
        metronome_id=parsed.id,
        metronome_environment=environment,
        defaults=defaults,
    )
    if _payload_changed(obj, payload_json):
        for key, value in defaults.items():
            setattr(obj, key, value)
        obj.save(update_fields=[*defaults.keys(), "updated_at"])
    return obj


@transaction.atomic
def upsert_rate_card(payload: dict[str, Any], *, environment: str) -> MetronomeRateCard:
    payload_json = _json_safe(payload)
    parsed = RateCardWriteSchema.model_validate(payload)
    defaults = {
        "name": parsed.name or "",
        "description": parsed.description or "",
        "aliases": _json_safe(parsed.aliases or []),
        "archived_at": parsed.archived_at,
        "raw_payload": payload_json,
        "last_synced_at": timezone.now(),
    }
    obj, _ = MetronomeRateCard.objects.get_or_create(
        metronome_id=parsed.id,
        metronome_environment=environment,
        defaults=defaults,
    )
    if _payload_changed(obj, payload_json):
        for key, value in defaults.items():
            setattr(obj, key, value)
        obj.save(update_fields=[*defaults.keys(), "updated_at"])
    return obj


@transaction.atomic
def upsert_rate_line(
    rate_card: MetronomeRateCard, payload: dict[str, Any]
) -> MetronomeRate:
    payload_json = _json_safe(payload)
    parsed = RateLineWriteSchema.model_validate(payload)
    defaults = {
        "product_name": parsed.product_name or "",
        "starting_at": parsed.starting_at,
        "ending_before": parsed.ending_before,
        "pricing_group_values": _json_safe(parsed.pricing_group_values or {}),
        "rate_payload": payload_json,
    }
    obj, _ = MetronomeRate.objects.get_or_create(
        rate_card=rate_card,
        product_id=parsed.product_id,
        starting_at=parsed.starting_at,
        defaults=defaults,
    )
    if obj.rate_payload != payload_json:
        for key, value in defaults.items():
            setattr(obj, key, value)
        obj.save(update_fields=[*defaults.keys(), "updated_at"])
    return obj


@transaction.atomic
def upsert_invoice(payload: dict[str, Any], *, environment: str) -> MetronomeInvoice:
    payload_json = _json_safe(payload)
    parsed = InvoiceWriteSchema.model_validate(payload)
    customer = None
    if parsed.customer_id:
        customer = MetronomeCustomer.objects.filter(
            metronome_id=parsed.customer_id,
            metronome_environment=environment,
        ).first()
    defaults = {
        "customer": customer,
        "status": parsed.status or "",
        "total": _decimal_safe(parsed.total),
        "currency": parsed.currency or "",
        "start_timestamp": parsed.start_timestamp,
        "end_timestamp": parsed.end_timestamp,
        "issued_at": parsed.issued_at,
        "raw_payload": payload_json,
        "last_synced_at": timezone.now(),
    }
    obj, _ = MetronomeInvoice.objects.get_or_create(
        metronome_id=parsed.id,
        metronome_environment=environment,
        defaults=defaults,
    )
    if _payload_changed(obj, payload_json):
        for key, value in defaults.items():
            setattr(obj, key, value)
        obj.save(update_fields=[*defaults.keys(), "updated_at"])
    return obj


@transaction.atomic
def upsert_usage_aggregate(
    payload: dict[str, Any], *, environment: str
) -> MetronomeUsageAggregate:
    payload_json = _json_safe(payload)
    parsed = UsageAggregateWriteSchema.model_validate(payload)

    groups_raw = parsed.groups if parsed.groups is not None else payload.get("groups")
    if groups_raw is None and payload.get("group") is not None:
        groups_raw = payload.get("group")
    groups = _json_safe(groups_raw or {})

    group_key = sha1(str(sorted(groups.items())).encode("utf-8")).hexdigest()[:20]
    customer_id = (
        parsed.customer_id
        or payload.get("customer_id")
        or groups.get("customer_id")
        or groups.get("customer")
        or ""
    )
    customer = MetronomeCustomer.objects.filter(
        metronome_id=str(customer_id),
        metronome_environment=environment,
    ).first()

    event_type = (
        parsed.event_type
        or parsed.billable_metric_name
        or parsed.billable_metric_id
        or payload.get("event_type")
        or payload.get("billable_metric_name")
        or payload.get("billable_metric_id")
        or ""
    )

    defaults = {
        "value": _decimal_safe(
            parsed.value if parsed.value is not None else payload.get("value", 0)
        ),
        "groups": groups,
        "raw_payload": payload_json,
        "last_synced_at": timezone.now(),
    }
    window_start = (
        parsed.start_timestamp
        or parsed.starting_on
        or _parse_dt(payload.get("start_timestamp"))
        or _parse_dt(payload.get("starting_on"))
        or timezone.now()
    )
    window_end = (
        parsed.end_timestamp
        or parsed.ending_before
        or _parse_dt(payload.get("end_timestamp"))
        or _parse_dt(payload.get("ending_before"))
        or timezone.now()
    )
    window_size_val = (
        parsed.window_size or payload.get("window_size") or "day"
    ).strip().lower() or "day"

    obj, _ = MetronomeUsageAggregate.objects.get_or_create(
        metronome_environment=environment,
        customer=customer,
        event_type=str(event_type),
        window_size=window_size_val,
        window_start=window_start,
        window_end=window_end,
        grouping_key=group_key,
        defaults=defaults,
    )
    if obj.raw_payload != payload_json or obj.value != defaults["value"]:
        for key, value in defaults.items():
            setattr(obj, key, value)
        obj.save(update_fields=[*defaults.keys(), "updated_at"])
    return obj


def sync_customers(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    limit: int = 100,
    cursor: str | None = None,
) -> dict[str, int | str]:
    checkpoint = _get_checkpoint("customers", environment)
    effective_cursor = cursor or checkpoint.cursor or None
    _mark_checkpoint_started(checkpoint, cursor=effective_cursor)

    processed = 0
    try:
        while True:
            items, next_cursor = adapter.list_customers_page(
                limit=limit,
                next_page=effective_cursor,
            )
            for item in items:
                upsert_customer(item, environment=environment)
                processed += 1
            if not next_cursor:
                break
            effective_cursor = next_cursor
        _mark_checkpoint_finished_cleared(checkpoint)
    except Exception as exc:
        _mark_checkpoint_failure(checkpoint, exc)
        raise

    return {"processed": processed, "cursor": ""}


def sync_contracts(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    limit: int = 100,
    reset_checkpoint: bool = False,
) -> dict[str, int]:
    if reset_checkpoint:
        checkpoint = _reset_sync_checkpoint("contracts", environment)
    else:
        checkpoint = _get_checkpoint("contracts", environment)

    customers = list(
        MetronomeCustomer.objects.filter(metronome_environment=environment).order_by(
            "metronome_id"
        )
    )
    meta = dict(checkpoint.metadata or {})
    resume = not reset_checkpoint and checkpoint.status in ("running", "failed")
    start_customer_id = meta.get("customer_metronome_id") if resume else None
    resume_cursor = checkpoint.cursor or None if resume else None

    skip_until = bool(start_customer_id)
    processed = 0
    _mark_checkpoint_started(checkpoint, cursor=resume_cursor or "")

    try:
        for customer in customers:
            if skip_until:
                if customer.metronome_id != start_customer_id:
                    continue
                skip_until = False
                cursor: str | None = resume_cursor
            else:
                cursor = None

            while True:
                items, next_cursor = adapter.list_contracts_page(
                    customer_id=customer.metronome_id,
                    limit=limit,
                    next_page=cursor,
                )
                for item in items:
                    upsert_contract(item, environment=environment)
                    processed += 1
                _persist_contracts_progress(
                    checkpoint,
                    customer_metronome_id=customer.metronome_id,
                    page_cursor=next_cursor or "",
                )
                if not next_cursor:
                    break
                cursor = next_cursor

        _mark_checkpoint_finished_cleared(checkpoint)
    except Exception as exc:
        _mark_checkpoint_failure(checkpoint, exc)
        raise

    return {"processed": processed}


def sync_rate_cards(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    limit: int = 100,
    rates_at: datetime | None = None,
    skip_rates: bool = False,
    reset_checkpoint: bool = False,
) -> dict[str, int]:
    if reset_checkpoint:
        checkpoint = _reset_sync_checkpoint("rate_cards", environment)
    else:
        checkpoint = _get_checkpoint("rate_cards", environment)

    meta = dict(checkpoint.metadata or {})
    step = str(meta.get("step", "cards"))
    if reset_checkpoint:
        step = "cards"

    rates_timestamp = rates_at or timezone.now()
    processed = 0
    resume_sync = not reset_checkpoint and checkpoint.status in ("running", "failed")
    card_cursor: str | None = None
    if resume_sync and step == "cards":
        card_cursor = checkpoint.cursor or None

    start_cursor = ""
    if resume_sync:
        start_cursor = checkpoint.cursor or ""
    _mark_checkpoint_started(checkpoint, cursor=start_cursor)

    try:
        if step == "cards":
            cursor = card_cursor
            while True:
                items, next_cursor = adapter.list_rate_cards_page(
                    limit=limit, next_page=cursor
                )
                for item in items:
                    upsert_rate_card(item, environment=environment)
                    processed += 1
                checkpoint.cursor = next_cursor or ""
                checkpoint.metadata = {"step": "cards"}
                checkpoint.save(update_fields=["cursor", "metadata", "updated_at"])
                if not next_cursor:
                    break
                cursor = next_cursor

            if skip_rates:
                _mark_checkpoint_finished_cleared(checkpoint)
                return {"processed": processed}

            checkpoint.metadata = {"step": "rates", "rates_card_metronome_id": ""}
            checkpoint.cursor = ""
            checkpoint.save(update_fields=["cursor", "metadata", "updated_at"])
            step = "rates"

        if step == "rates" and not skip_rates:
            meta = dict(checkpoint.metadata or {})
            resume_card_id = meta.get("rates_card_metronome_id") or None
            resume_rates_cursor = checkpoint.cursor or None if resume_card_id else None

            cards = list(
                MetronomeRateCard.objects.filter(metronome_environment=environment)
                .exclude(metronome_id="")
                .order_by("metronome_id")
            )
            skip_cards = bool(resume_card_id)
            for card in cards:
                if skip_cards:
                    if card.metronome_id != resume_card_id:
                        continue
                    skip_cards = False
                    r_cursor: str | None = resume_rates_cursor
                else:
                    r_cursor = None

                while True:
                    items, next_r = adapter.list_rates_page(
                        rate_card_id=card.metronome_id,
                        at=rates_timestamp,
                        limit=limit,
                        next_page=r_cursor,
                    )
                    for item in items:
                        upsert_rate_line(card, item)
                        processed += 1
                    checkpoint.metadata = {
                        "step": "rates",
                        "rates_card_metronome_id": card.metronome_id,
                    }
                    checkpoint.cursor = next_r or ""
                    checkpoint.save(update_fields=["cursor", "metadata", "updated_at"])
                    if not next_r:
                        break
                    r_cursor = next_r

        _mark_checkpoint_finished_cleared(checkpoint)
    except Exception as exc:
        _mark_checkpoint_failure(checkpoint, exc)
        raise

    return {"processed": processed}


def sync_invoices(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    limit: int = 100,
    reset_checkpoint: bool = False,
) -> dict[str, int]:
    if reset_checkpoint:
        checkpoint = _reset_sync_checkpoint("invoices", environment)
    else:
        checkpoint = _get_checkpoint("invoices", environment)

    customers = list(
        MetronomeCustomer.objects.filter(metronome_environment=environment).order_by(
            "metronome_id"
        )
    )
    meta = dict(checkpoint.metadata or {})
    resume = not reset_checkpoint and checkpoint.status in ("running", "failed")
    start_customer_id = meta.get("customer_metronome_id") if resume else None
    resume_cursor = checkpoint.cursor or None if resume else None

    skip_until = bool(start_customer_id)
    processed = 0
    _mark_checkpoint_started(checkpoint, cursor=resume_cursor or "")

    try:
        for customer in customers:
            if skip_until:
                if customer.metronome_id != start_customer_id:
                    continue
                skip_until = False
                cursor: str | None = resume_cursor
            else:
                cursor = None

            while True:
                items, next_cursor = adapter.list_invoices_page(
                    customer_id=customer.metronome_id,
                    limit=limit,
                    next_page=cursor,
                )
                for item in items:
                    upsert_invoice(item, environment=environment)
                    processed += 1
                _persist_contracts_progress(
                    checkpoint,
                    customer_metronome_id=customer.metronome_id,
                    page_cursor=next_cursor or "",
                )
                if not next_cursor:
                    break
                cursor = next_cursor

        _mark_checkpoint_finished_cleared(checkpoint)
    except Exception as exc:
        _mark_checkpoint_failure(checkpoint, exc)
        raise

    return {"processed": processed}


def sync_usage(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    starting_on: str | datetime,
    ending_before: str | datetime,
    window_size: str = "day",
    reset_checkpoint: bool = False,
) -> dict[str, int]:
    checkpoint = _get_checkpoint("usage", environment)
    norm_start = normalize_metronome_usage_window_bound(starting_on)
    norm_end = normalize_metronome_usage_window_bound(ending_before)
    ws = window_size.strip().upper()

    if reset_checkpoint:
        checkpoint.cursor = ""
        checkpoint.metadata = {}
        checkpoint.last_error = ""
        checkpoint.status = "idle"
        checkpoint.save(
            update_fields=["cursor", "metadata", "last_error", "status", "updated_at"]
        )

    resume = (
        not reset_checkpoint
        and checkpoint.status in ("running", "failed")
        and _usage_window_matches(checkpoint, starting_on, ending_before, window_size)
    )

    if not resume:
        checkpoint.metadata = {
            "starting_on": norm_start,
            "ending_before": norm_end,
            "window_size": ws,
        }
        checkpoint.window_start = _parse_dt(norm_start)
        checkpoint.window_end = _parse_dt(norm_end)
        checkpoint.cursor = ""
        checkpoint.save(
            update_fields=[
                "metadata",
                "window_start",
                "window_end",
                "cursor",
                "updated_at",
            ]
        )

    cursor = checkpoint.cursor or None if resume else None
    _mark_checkpoint_started(checkpoint, cursor=cursor or "")

    processed = 0
    try:
        effective = cursor
        while True:
            items, next_cursor = adapter.list_usage_page(
                starting_on=starting_on,
                ending_before=ending_before,
                window_size=window_size,
                next_page=effective,
            )
            for item in items:
                upsert_usage_aggregate(item, environment=environment)
                processed += 1
            checkpoint.cursor = next_cursor or ""
            checkpoint.save(update_fields=["cursor", "updated_at"])
            if not next_cursor:
                break
            effective = next_cursor

        checkpoint.status = "ok"
        checkpoint.cursor = ""
        checkpoint.last_successful_at = timezone.now()
        checkpoint.save(
            update_fields=["status", "cursor", "last_successful_at", "updated_at"]
        )
    except Exception as exc:
        _mark_checkpoint_failure(checkpoint, exc)
        raise

    return {"processed": processed}


def sync_usage_with_groups(
    *,
    adapter: MetronomeAdapter,
    environment: str,
    billable_metric_id: str,
    window_size: str = "day",
    starting_on: str | datetime | None = None,
    ending_before: str | datetime | None = None,
    group_key: list[str] | None = None,
    group_filters: dict[str, list[str]] | None = None,
    current_period: bool | None = None,
    limit: int = 100,
    reset_checkpoint: bool = False,
) -> dict[str, int]:
    if reset_checkpoint:
        checkpoint = _reset_sync_checkpoint("usage_groups", environment)
    else:
        checkpoint = _get_checkpoint("usage_groups", environment)

    ws = window_size.strip().upper()
    customers = list(
        MetronomeCustomer.objects.filter(metronome_environment=environment).order_by(
            "metronome_id"
        )
    )

    meta_base: dict[str, Any] = {
        "billable_metric_id": billable_metric_id,
        "window_size": ws,
        "group_key": group_key or [],
    }
    if current_period:
        meta_base["current_period"] = True
    else:
        meta_base["current_period"] = False
        if starting_on is None or ending_before is None:
            raise ValueError("Usage groups sync needs a window or current_period=true")
        meta_base["starting_on"] = normalize_metronome_usage_window_bound(starting_on)
        meta_base["ending_before"] = normalize_metronome_usage_window_bound(
            ending_before
        )

    if reset_checkpoint:
        checkpoint.cursor = ""
        checkpoint.metadata = {}
        checkpoint.last_error = ""
        checkpoint.status = "idle"
        checkpoint.save(
            update_fields=["cursor", "metadata", "last_error", "status", "updated_at"]
        )

    resume = (
        not reset_checkpoint
        and checkpoint.status in ("running", "failed")
        and _usage_groups_params_match(
            checkpoint,
            billable_metric_id=billable_metric_id,
            starting_on=starting_on,
            ending_before=ending_before,
            window_size=window_size,
            group_key=group_key,
            current_period=current_period,
        )
    )

    if not resume:
        checkpoint.metadata = dict(meta_base)
        checkpoint.cursor = ""
        checkpoint.save(update_fields=["metadata", "cursor", "updated_at"])

    start_customer_id = (
        (checkpoint.metadata or {}).get("customer_metronome_id") if resume else None
    )
    resume_cursor = checkpoint.cursor or None if resume else None

    skip_until = bool(start_customer_id)
    processed = 0
    _mark_checkpoint_started(checkpoint, cursor=resume_cursor or "")

    try:
        for customer in customers:
            if skip_until:
                if customer.metronome_id != start_customer_id:
                    continue
                skip_until = False
                g_cursor: str | None = resume_cursor
            else:
                g_cursor = None

            while True:
                items, next_cursor = adapter.list_usage_with_groups_page(
                    billable_metric_id=billable_metric_id,
                    customer_id=customer.metronome_id,
                    window_size=ws,
                    limit=limit,
                    next_page=g_cursor,
                    starting_on=starting_on,
                    ending_before=ending_before,
                    group_key=group_key,
                    group_filters=group_filters,
                    current_period=current_period,
                )
                for row in items:
                    payload = {
                        "customer_id": customer.metronome_id,
                        "billable_metric_id": billable_metric_id,
                        "window_size": window_size,
                        "starting_on": row.get("starting_on"),
                        "ending_before": row.get("ending_before"),
                        "value": row.get("value"),
                        "groups": row.get("group") or {},
                    }
                    upsert_usage_aggregate(payload, environment=environment)
                    processed += 1

                m = dict(meta_base)
                m["customer_metronome_id"] = customer.metronome_id
                checkpoint.metadata = m
                checkpoint.cursor = next_cursor or ""
                checkpoint.save(update_fields=["metadata", "cursor", "updated_at"])

                if not next_cursor:
                    break
                g_cursor = next_cursor

        _mark_checkpoint_finished_cleared(checkpoint)
    except Exception as exc:
        _mark_checkpoint_failure(checkpoint, exc)
        raise

    return {"processed": processed}
