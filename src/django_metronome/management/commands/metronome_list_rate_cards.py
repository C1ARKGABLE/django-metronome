"""Print Metronome rate cards (``v1.contracts.rate_cards.list``)."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from django_metronome.client import MetronomeClientDisabledError, build_metronome_client
from django_metronome.services import MetronomeAdapter


class Command(BaseCommand):
    help = "List rate cards (requires METRONOME_API_KEY)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Page size per API request (default 100).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Print full JSON array instead of tab-separated id and name.",
        )

    def handle(self, *args, **options):
        try:
            build_metronome_client()
        except MetronomeClientDisabledError as exc:
            raise CommandError(str(exc)) from exc

        adapter = MetronomeAdapter()
        limit: int = options["limit"]
        as_json: bool = options["as_json"]

        all_rows: list[dict] = []
        cursor: str | None = None
        while True:
            page, next_c = adapter.list_rate_cards_page(
                limit=limit,
                next_page=cursor,
            )
            all_rows.extend(page)
            if not next_c:
                break
            cursor = next_c

        if as_json:
            self.stdout.write(json.dumps(all_rows, indent=2))
            return

        for row in all_rows:
            rid = row.get("id", "")
            name = row.get("name", "")
            self.stdout.write(f"{rid}\t{name}")
