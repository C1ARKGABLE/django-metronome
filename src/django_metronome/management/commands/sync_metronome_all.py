from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run all Metronome sync commands in dependency order."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--environment", default="sandbox")
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--window-size", default="day")
        parser.add_argument("--starting-on", default=None)
        parser.add_argument("--ending-before", default=None)
        parser.add_argument(
            "--reset-checkpoint",
            action="store_true",
            help="Forward --reset-checkpoint to each sync command.",
        )
        parser.add_argument(
            "--skip-rates",
            action="store_true",
            help="Forward to sync_metronome_rate_cards (headers only).",
        )
        parser.add_argument(
            "--rates-at",
            default=None,
            help="ISO timestamp forwarded to rate_cards getRates ``at``.",
        )

    def handle(self, *args, **options):
        command_kwargs = {
            "environment": options["environment"],
            "limit": options["limit"],
            "reset_checkpoint": options["reset_checkpoint"],
        }
        call_command("sync_metronome_customers", **command_kwargs)
        call_command("sync_metronome_contracts", **command_kwargs)
        call_command(
            "sync_metronome_rate_cards",
            **command_kwargs,
            skip_rates=options["skip_rates"],
            rates_at=options["rates_at"],
        )
        call_command("sync_metronome_invoices", **command_kwargs)
        call_command(
            "sync_metronome_usage",
            **command_kwargs,
            window_size=options["window_size"],
            starting_on=options["starting_on"],
            ending_before=options["ending_before"],
        )
