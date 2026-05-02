from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from django.core.management.base import CommandError
from django.utils import timezone

from django_metronome.management.commands._sync_base import SyncCommandMixin
from django_metronome.services import sync_usage, sync_usage_with_groups
from django_metronome.services.metronome_adapter import (
    normalize_metronome_usage_window_bound,
)


class Command(SyncCommandMixin):
    help = "Sync Metronome usage aggregates into the local mirror."

    def add_arguments(self, parser) -> None:
        self.add_base_arguments(parser)
        parser.add_argument("--starting-on", default=None, help="ISO start timestamp")
        parser.add_argument("--ending-before", default=None, help="ISO end timestamp")
        parser.add_argument(
            "--window-size", default="day", help="hour/day/none window size"
        )
        parser.add_argument(
            "--with-groups",
            action="store_true",
            help="Use v1.usage.list_with_groups (requires --billable-metric-id).",
        )
        parser.add_argument(
            "--billable-metric-id",
            default=None,
            help="Billable metric UUID for grouped usage sync.",
        )
        parser.add_argument(
            "--group-key",
            action="append",
            default=None,
            help="Grouping dimension; repeat for compound keys (e.g. region).",
        )
        parser.add_argument(
            "--current-period",
            action="store_true",
            help="With --with-groups: use current billing period (no fixed window).",
        )

    def handle(self, *args, **options):
        if options["with_groups"]:
            if not options["billable_metric_id"]:
                raise CommandError(
                    "--billable-metric-id is required when using --with-groups"
                )
            starting_on = ending_before = None
            if not options["current_period"]:
                utc_now = timezone.now().astimezone(UTC)
                end_date = utc_now.date()
                if options["ending_before"] is not None:
                    ending_before = normalize_metronome_usage_window_bound(
                        options["ending_before"]
                    )
                else:
                    ending_before = normalize_metronome_usage_window_bound(
                        datetime.combine(
                            end_date + timedelta(days=1),
                            time.min,
                            tzinfo=UTC,
                        )
                    )
                if options["starting_on"] is not None:
                    starting_on = normalize_metronome_usage_window_bound(
                        options["starting_on"]
                    )
                else:
                    starting_on = normalize_metronome_usage_window_bound(
                        datetime.combine(
                            end_date - timedelta(days=6),
                            time.min,
                            tzinfo=UTC,
                        )
                    )
            try:
                summary = sync_usage_with_groups(
                    adapter=self.build_adapter(),
                    environment=options["environment"],
                    billable_metric_id=options["billable_metric_id"],
                    window_size=options["window_size"],
                    starting_on=starting_on,
                    ending_before=ending_before,
                    group_key=options["group_key"],
                    group_filters=None,
                    current_period=True if options["current_period"] else None,
                    limit=options["limit"],
                    reset_checkpoint=options["reset_checkpoint"],
                )
            except Exception as exc:  # pragma: no cover - CLI boundary
                raise CommandError(str(exc)) from exc
            self.stdout.write(
                self.style.SUCCESS(f"Synced grouped usage rows: {summary['processed']}")
            )
            return

        if options["current_period"]:
            raise CommandError("--current-period is only valid with --with-groups")

        utc_now = timezone.now().astimezone(UTC)
        end_date = utc_now.date()
        if options["ending_before"] is not None:
            ending_before = normalize_metronome_usage_window_bound(
                options["ending_before"]
            )
        else:
            ending_before = normalize_metronome_usage_window_bound(
                datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
            )
        if options["starting_on"] is not None:
            starting_on = normalize_metronome_usage_window_bound(options["starting_on"])
        else:
            starting_on = normalize_metronome_usage_window_bound(
                datetime.combine(end_date - timedelta(days=6), time.min, tzinfo=UTC)
            )
        try:
            summary = sync_usage(
                adapter=self.build_adapter(),
                environment=options["environment"],
                starting_on=starting_on,
                ending_before=ending_before,
                window_size=options["window_size"],
                reset_checkpoint=options["reset_checkpoint"],
            )
        except Exception as exc:  # pragma: no cover - CLI boundary
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Synced usage rows: {summary['processed']}")
        )
