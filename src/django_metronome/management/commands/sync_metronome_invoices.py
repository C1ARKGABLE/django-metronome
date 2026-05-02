from __future__ import annotations

from django.core.management.base import CommandError

from django_metronome.management.commands._sync_base import SyncCommandMixin
from django_metronome.services import sync_invoices


class Command(SyncCommandMixin):
    help = "Sync Metronome invoices into the local mirror."

    def add_arguments(self, parser) -> None:
        self.add_base_arguments(parser)

    def handle(self, *args, **options):
        try:
            summary = sync_invoices(
                adapter=self.build_adapter(),
                environment=options["environment"],
                limit=options["limit"],
                reset_checkpoint=options["reset_checkpoint"],
            )
        except Exception as exc:  # pragma: no cover - CLI boundary
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Synced invoices: {summary['processed']}")
        )
