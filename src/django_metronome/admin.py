"""
Django admin is read-only for Metronome-backed data: canonical identifiers and
rows come from Metronome APIs and ``sync_metronome_*`` commands, not from manual
admin creates/edits.
"""

from django.contrib import admin

from django_metronome.models import (
    MetronomeContract,
    MetronomeCustomer,
    MetronomeInvoice,
    MetronomeRate,
    MetronomeRateCard,
    MetronomeUsageAggregate,
    SyncCheckpoint,
)


class MetronomeMirrorModelAdmin(admin.ModelAdmin):
    """Mirror-only: no adding or changing rows in admin (sync populates the mirror)."""

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(MetronomeCustomer)
class MetronomeCustomerAdmin(MetronomeMirrorModelAdmin):
    list_display = ("metronome_id", "name", "metronome_environment", "archived_at")
    search_fields = ("metronome_id", "name")
    list_filter = ("metronome_environment", "archived_at")


@admin.register(MetronomeContract)
class MetronomeContractAdmin(MetronomeMirrorModelAdmin):
    list_display = (
        "metronome_id",
        "customer",
        "status",
        "starting_at",
        "ending_before",
    )
    search_fields = ("metronome_id", "customer__metronome_id")
    list_filter = ("metronome_environment", "status")


@admin.register(MetronomeRateCard)
class MetronomeRateCardAdmin(MetronomeMirrorModelAdmin):
    list_display = ("metronome_id", "name", "metronome_environment", "archived_at")
    search_fields = ("metronome_id", "name")
    list_filter = ("metronome_environment",)


@admin.register(MetronomeRate)
class MetronomeRateAdmin(MetronomeMirrorModelAdmin):
    list_display = ("rate_card", "product_id", "starting_at", "ending_before")
    search_fields = ("product_id", "product_name", "rate_card__metronome_id")


@admin.register(MetronomeInvoice)
class MetronomeInvoiceAdmin(MetronomeMirrorModelAdmin):
    list_display = ("metronome_id", "customer", "status", "total", "start_timestamp")
    search_fields = ("metronome_id", "customer__metronome_id")
    list_filter = ("metronome_environment", "status")


@admin.register(MetronomeUsageAggregate)
class MetronomeUsageAggregateAdmin(MetronomeMirrorModelAdmin):
    list_display = ("customer", "event_type", "window_start", "window_end", "value")
    search_fields = ("customer__metronome_id", "event_type", "grouping_key")
    list_filter = ("metronome_environment", "window_size", "event_type")


@admin.register(SyncCheckpoint)
class SyncCheckpointAdmin(MetronomeMirrorModelAdmin):
    list_display = (
        "entity",
        "metronome_environment",
        "status",
        "cursor",
        "last_successful_at",
    )
    search_fields = ("entity", "cursor")
    list_filter = ("metronome_environment", "status")
