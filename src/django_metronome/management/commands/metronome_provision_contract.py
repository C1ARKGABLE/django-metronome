from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from django_metronome.schemas.provisioning import ContractCreateRequest
from django_metronome.services import MetronomeAdapter, provision_contract


class Command(BaseCommand):
    help = (
        "Create a Metronome contract (v1) and mirror via v2 retrieve (Phase 1.5). "
        "Optional SDK fields: --kwargs-json."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--environment", default="sandbox")
        parser.add_argument("--customer-id", required=True)
        parser.add_argument(
            "--starting-at",
            required=True,
            help="ISO-8601 contract start",
        )
        parser.add_argument(
            "--kwargs-json",
            default="{}",
            help=(
                "Extra JSON merged into create payload "
                '(e.g. {"rate_card_alias":"paygo"}).'
            ),
        )

    def handle(self, *args, **options):
        try:
            extra = json.loads(options["kwargs_json"])
            if not isinstance(extra, dict):
                raise ValueError("--kwargs-json must be a JSON object")
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid --kwargs-json: {exc}") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        payload = {
            "customer_id": options["customer_id"],
            "starting_at": options["starting_at"],
            **extra,
        }
        try:
            request = ContractCreateRequest.model_validate(payload)
        except Exception as exc:
            raise CommandError(f"Invalid contract payload: {exc}") from exc

        try:
            row = provision_contract(
                adapter=MetronomeAdapter(),
                environment=options["environment"],
                request=request,
            )
        except Exception as exc:  # pragma: no cover - CLI boundary
            raise CommandError(str(exc)) from exc

        cust_mid = row.customer.metronome_id if row.customer else ""
        msg = (
            f"Provisioned contract metronome_id={row.metronome_id} "
            f"customer_metronome_id={cust_mid}"
        )
        self.stdout.write(self.style.SUCCESS(msg))
