from __future__ import annotations

from datetime import datetime

from django.core.management.base import CommandError
from django.utils import timezone

from django_metronome.management.commands._sync_base import SyncCommandMixin
from django_metronome.services import sync_rate_cards


class Command(SyncCommandMixin):
    help = "Sync Metronome rate cards into the local mirror."

    def add_arguments(self, parser) -> None:
        self.add_base_arguments(parser)
        parser.add_argument(
            "--skip-rates",
            action="store_true",
            help="Stop after syncing rate card headers (skip per-card rate schedules).",
        )
        parser.add_argument(
            "--rates-at",
            default=None,
            help="ISO timestamp for getRates ``at=`` snapshot (default: current time).",
        )

    def handle(self, *args, **options):
        rates_at = None
        if options["rates_at"]:
            raw = options["rates_at"].strip().replace("Z", "+00:00")
            rates_at = datetime.fromisoformat(raw)
            if timezone.is_naive(rates_at):
                rates_at = timezone.make_aware(
                    rates_at, timezone.get_current_timezone()
                )
        try:
            summary = sync_rate_cards(
                adapter=self.build_adapter(),
                environment=options["environment"],
                limit=options["limit"],
                rates_at=rates_at,
                skip_rates=options["skip_rates"],
                reset_checkpoint=options["reset_checkpoint"],
            )
        except Exception as exc:  # pragma: no cover - CLI boundary
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Synced rate cards: {summary['processed']}")
        )
