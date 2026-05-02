from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from django_metronome.schemas.provisioning import CustomerCreateRequest
from django_metronome.services import MetronomeAdapter, provision_customer


class Command(BaseCommand):
    help = "Create a Metronome customer and mirror row (Phase 1.5 provisioning)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--environment", default="sandbox")
        parser.add_argument("--name", required=True)
        parser.add_argument(
            "--ingest-alias",
            action="append",
            dest="ingest_aliases",
            default=[],
            help="Repeat for multiple ingest aliases.",
        )

    def handle(self, *args, **options):
        req = CustomerCreateRequest(
            name=options["name"],
            ingest_aliases=options["ingest_aliases"] or [],
        )
        try:
            row = provision_customer(
                adapter=MetronomeAdapter(),
                environment=options["environment"],
                request=req,
            )
        except Exception as exc:  # pragma: no cover - CLI boundary
            raise CommandError(str(exc)) from exc

        msg = f"Provisioned customer metronome_id={row.metronome_id} name={row.name!r}"
        self.stdout.write(self.style.SUCCESS(msg))
