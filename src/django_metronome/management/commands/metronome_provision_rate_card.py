from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from django_metronome.schemas.provisioning import RateAddRequest, RateCardCreateRequest
from django_metronome.services import MetronomeAdapter, provision_rate_card_with_rates


class Command(BaseCommand):
    help = (
        "Create a rate card, add rates, and mirror rows via getRates (Phase 1.5). "
        "--rates-json is a JSON array of objects validated as RateAddRequest."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--environment", default="sandbox")
        parser.add_argument("--name", required=True)
        parser.add_argument("--description", default=None)
        parser.add_argument(
            "--alias",
            action="append",
            dest="aliases",
            default=[],
            help="Repeat for each rate-card alias name.",
        )
        parser.add_argument(
            "--rates-json",
            required=True,
            help=(
                "JSON array of rate rows "
                '(e.g. [{"product_id":"...","rate_type":"FLAT"}]).'
            ),
        )

    def handle(self, *args, **options):
        try:
            raw_rates = json.loads(options["rates_json"])
            if not isinstance(raw_rates, list):
                raise ValueError("--rates-json must be a JSON array")
            rates = [RateAddRequest.model_validate(item) for item in raw_rates]
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid --rates-json: {exc}") from exc
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        card = RateCardCreateRequest(
            name=options["name"],
            description=options["description"],
            aliases=options["aliases"] or [],
        )

        try:
            row, n_lines = provision_rate_card_with_rates(
                adapter=MetronomeAdapter(),
                environment=options["environment"],
                card=card,
                rates=rates,
            )
        except Exception as exc:  # pragma: no cover - CLI boundary
            raise CommandError(str(exc)) from exc

        msg = (
            f"Provisioned rate card metronome_id={row.metronome_id} "
            f"mirrored_rates={n_lines}"
        )
        self.stdout.write(self.style.SUCCESS(msg))
