from __future__ import annotations

from django.core.management.base import CommandError

from django_metronome.management.commands._sync_base import SyncCommandMixin
from django_metronome.services import sync_customers


class Command(SyncCommandMixin):
    help = "Sync Metronome customers into the local mirror."

    def add_arguments(self, parser) -> None:
        self.add_base_arguments(parser)
        parser.add_argument("--cursor", default=None, help="Cursor to resume from.")

    def handle(self, *args, **options):
        try:
            summary = sync_customers(
                adapter=self.build_adapter(),
                environment=options["environment"],
                limit=options["limit"],
                cursor=options["cursor"],
            )
        except Exception as exc:  # pragma: no cover - CLI boundary
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Synced customers: {summary['processed']} (cursor={summary['cursor']})"
            )
        )
