"""
Live check: provisioning + adapter vs Metronome (create, verify, archive).

Needs ``METRONOME_API_KEY``. Creates real resources then archives them.

Example::

    export METRONOME_API_KEY=...
    poetry run python example/manage.py metronome_validate_provisioning \\
        --billable-metric-id <uuid>
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from django_metronome.client import MetronomeClientDisabledError, build_metronome_client
from django_metronome.models import MetronomeCustomer, MetronomeRate, MetronomeRateCard
from django_metronome.schemas.provisioning import (
    ContractCreateRequest,
    CustomerCreateRequest,
    RateAddRequest,
    RateCardCreateRequest,
)
from django_metronome.services import (
    MetronomeAdapter,
    provision_contract,
    provision_customer,
    provision_rate_card_with_rates,
)


class Command(BaseCommand):
    help = (
        "Provision test customer/rates/contract, assert API + DB mirror, then archive."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--environment", default="sandbox")
        parser.add_argument(
            "--billable-metric-id",
            required=True,
            help="Billable metric UUID for a temporary USAGE product and rate row.",
        )
        parser.add_argument(
            "--starting-at",
            default="2026-01-01T00:00:00Z",
            help="RFC3339 time for contract + rates (must match rate snapshot time).",
        )

    def handle(self, *args, **options):
        env: str = options["environment"]
        metric_id: str = options["billable_metric_id"]
        starting_at: str = options["starting_at"]

        try:
            build_metronome_client()
        except MetronomeClientDisabledError as exc:
            raise CommandError(str(exc)) from exc

        adapter = MetronomeAdapter()
        suffix = uuid.uuid4().hex[:12]
        rates_at = datetime.fromisoformat(starting_at.replace("Z", "+00:00"))

        self.stdout.write(f"Validation suffix={suffix}")

        def ok(cond: bool, msg: str) -> None:
            if not cond:
                raise CommandError(msg)

        cust_name = f"validate-cust-{suffix}"
        ingest_alias = f"validate-{suffix}@test.invalid"
        cust_req = CustomerCreateRequest(
            name=cust_name,
            ingest_aliases=[ingest_alias],
        )
        cust_row = provision_customer(
            adapter=adapter, environment=env, request=cust_req
        )
        api_cust = adapter.retrieve_customer(cust_row.metronome_id)
        ok(api_cust["name"] == cust_name, "customer name mismatch after retrieve")
        ok(
            ingest_alias in api_cust.get("ingest_aliases", []),
            "ingest alias missing after retrieve",
        )
        ok(
            MetronomeCustomer.objects.filter(
                metronome_id=cust_row.metronome_id,
                metronome_environment=env,
            ).exists(),
            "customer mirror row missing",
        )
        adapter.archive_customer(customer_id=cust_row.metronome_id)
        archived = adapter.retrieve_customer(cust_row.metronome_id)
        ok(bool(archived.get("archived_at")), "customer not archived")

        prod_name = f"validate-usage-{suffix}"
        prod_id = adapter.create_usage_product(
            name=prod_name,
            billable_metric_id=metric_id,
        )
        prod = adapter.retrieve_product(product_id=prod_id)
        cur = prod.get("current") or {}
        ok(cur.get("name") == prod_name, "usage product name mismatch")
        ok(prod.get("type") == "USAGE", "usage product type mismatch")

        rc_label = f"validate-rc-{suffix}"
        card_req = RateCardCreateRequest(
            name=rc_label,
            description=f"desc-{suffix}",
            aliases=[f"v-rc-{suffix}"],
        )
        rate_req = RateAddRequest(
            product_id=prod_id,
            rate_type="FLAT",
            starting_at=starting_at,
            entitled=True,
            price=100,
        )
        rc_row, n_lines = provision_rate_card_with_rates(
            adapter=adapter,
            environment=env,
            card=card_req,
            rates=[rate_req],
            rates_at=rates_at,
        )
        ok(n_lines >= 1, "expected at least one rate schedule line mirrored")
        ok(
            MetronomeRate.objects.filter(rate_card=rc_row).count() == n_lines,
            "mirror MetronomeRate count != schedule lines",
        )
        header = adapter.retrieve_rate_card(rate_card_id=rc_row.metronome_id)
        ok(header.get("name") == rc_label, "rate card header name mismatch")
        aliases = header.get("aliases") or []
        alias_names = (
            [a["name"] for a in aliases]
            if aliases and isinstance(aliases[0], dict)
            else []
        )
        ok(f"v-rc-{suffix}" in alias_names, "rate card alias missing")
        rows, _ = adapter.list_rates_page(
            rate_card_id=rc_row.metronome_id,
            at=starting_at,
            limit=50,
        )
        match = next((r for r in rows if r.get("product_id") == prod_id), None)
        ok(match is not None, "rates.list missing FLAT row for product")
        ok(match.get("rate", {}).get("rate_type") == "FLAT", "rate_type not FLAT")
        ok(match.get("rate", {}).get("price") == 100, "rate price not 100")
        adapter.archive_rate_card(rate_card_id=rc_row.metronome_id)
        adapter.archive_product(product_id=prod_id)

        ctr_cust_name = f"validate-ctr-cust-{suffix}"
        ctr_cust = provision_customer(
            adapter=adapter,
            environment=env,
            request=CustomerCreateRequest(
                name=ctr_cust_name,
                ingest_aliases=[f"ctr-{suffix}@test.invalid"],
            ),
        )
        ctr_rc_id = adapter.create_rate_card(
            name=f"validate-ctr-rc-{suffix}",
        )
        uniq = f"validate-uniq-{suffix}"
        ctr_name = f"validate-contract-{suffix}"
        ctr_row = provision_contract(
            adapter=adapter,
            environment=env,
            request=ContractCreateRequest(
                customer_id=ctr_cust.metronome_id,
                starting_at=starting_at,
                rate_card_id=ctr_rc_id,
                name=ctr_name,
                uniqueness_key=uniq,
            ),
        )
        v2 = adapter.retrieve_contract(
            contract_id=ctr_row.metronome_id,
            customer_id=ctr_cust.metronome_id,
        )
        ok(v2.get("customer_id") == ctr_cust.metronome_id, "v2 contract customer_id")
        ok(v2.get("name") == ctr_name, "v2 contract name")
        ok(v2.get("uniqueness_key") == uniq, "v2 contract uniqueness_key")
        ok(v2.get("rate_card_id") == ctr_rc_id, "v2 contract rate_card_id")
        ok(
            MetronomeCustomer.objects.filter(
                metronome_id=ctr_cust.metronome_id,
                metronome_environment=env,
            ).exists(),
            "contract customer mirror missing",
        )
        ok(
            MetronomeRateCard.objects.filter(
                metronome_id=ctr_rc_id,
                metronome_environment=env,
            ).exists(),
            "contract rate card mirror missing",
        )

        adapter.archive_contract(
            contract_id=ctr_row.metronome_id,
            customer_id=ctr_cust.metronome_id,
            void_invoices=False,
        )
        adapter.archive_rate_card(rate_card_id=ctr_rc_id)
        adapter.archive_customer(customer_id=ctr_cust.metronome_id)

        self.stdout.write(
            self.style.SUCCESS(
                "Provisioning validation passed (customer, rate card+rates, contract)."
            )
        )
