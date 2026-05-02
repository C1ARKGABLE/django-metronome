from __future__ import annotations

from django.core.management.base import BaseCommand

from django_metronome.conf import get_metronome_settings
from django_metronome.services import MetronomeAdapter


class SyncCommandMixin(BaseCommand):
    def add_base_arguments(self, parser) -> None:
        parser.add_argument(
            "--environment",
            default=get_metronome_settings().environment,
            help="Target Metronome environment label for local mirror rows.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Page size for list operations.",
        )
        parser.add_argument(
            "--reset-checkpoint",
            action="store_true",
            help="Discard saved sync cursor/metadata for this entity and start over.",
        )

    def build_adapter(self) -> MetronomeAdapter:
        return MetronomeAdapter()
