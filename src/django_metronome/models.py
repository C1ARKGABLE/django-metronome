from django.db import models
from django.utils import timezone


class AuditStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class MetronomeSyncBaseModel(AuditStampedModel):
    """Mirrored entity with a canonical ``metronome_id`` assigned by Metronome APIs."""

    metronome_id = models.CharField(max_length=255, db_index=True)
    metronome_environment = models.CharField(max_length=32, default="sandbox")
    metronome_livemode = models.BooleanField(default=False)
    raw_payload = models.JSONField(default=dict, blank=True)

    source_created_at = models.DateTimeField(null=True, blank=True)
    source_updated_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(default=timezone.now)

    # Audit metadata that future upsert services can consistently populate.
    sync_cursor = models.CharField(max_length=255, blank=True, default="")
    sync_origin = models.CharField(max_length=64, blank=True, default="")
    sync_event_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        abstract = True


class MetronomeCustomer(MetronomeSyncBaseModel):
    name = models.CharField(max_length=255, blank=True, default="")
    ingest_aliases = models.JSONField(default=list, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("metronome_id", "metronome_environment")
        indexes = [
            models.Index(fields=["metronome_environment", "name"]),
            models.Index(fields=["metronome_environment", "archived_at"]),
        ]

    def __str__(self) -> str:
        return self.name or self.metronome_id


class MetronomeContractQuerySet(models.QuerySet):
    def current_for_customer(
        self,
        customer: MetronomeCustomer,
        *,
        at: timezone.datetime | None = None,
    ):
        point_in_time = at or timezone.now()
        return (
            self.filter(customer=customer)
            .filter(
                models.Q(starting_at__lte=point_in_time)
                | models.Q(starting_at__isnull=True)
            )
            .filter(
                models.Q(ending_before__gt=point_in_time)
                | models.Q(ending_before__isnull=True)
            )
            .order_by("-starting_at")
            .first()
        )


class MetronomeContract(MetronomeSyncBaseModel):
    customer = models.ForeignKey(
        MetronomeCustomer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contracts",
    )
    status = models.CharField(max_length=64, blank=True, default="")
    starting_at = models.DateTimeField(null=True, blank=True)
    ending_before = models.DateTimeField(null=True, blank=True)
    rate_card_id = models.CharField(max_length=255, blank=True, default="")

    objects = MetronomeContractQuerySet.as_manager()

    class Meta:
        unique_together = ("metronome_id", "metronome_environment")
        indexes = [
            models.Index(fields=["metronome_environment", "status"]),
            models.Index(fields=["customer", "starting_at"]),
        ]

    def __str__(self) -> str:
        return self.metronome_id


class MetronomeRateCard(MetronomeSyncBaseModel):
    name = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")
    aliases = models.JSONField(default=list, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("metronome_id", "metronome_environment")
        indexes = [
            models.Index(fields=["metronome_environment", "name"]),
        ]

    def __str__(self) -> str:
        return self.name or self.metronome_id


class MetronomeRate(AuditStampedModel):
    """Rate schedule line from Metronome (product_id + dimensions from API/sync)."""

    rate_card = models.ForeignKey(
        MetronomeRateCard,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    product_id = models.CharField(max_length=255)
    product_name = models.CharField(max_length=255, blank=True, default="")
    starting_at = models.DateTimeField(null=True, blank=True)
    ending_before = models.DateTimeField(null=True, blank=True)
    pricing_group_values = models.JSONField(default=dict, blank=True)
    rate_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rate_card", "product_id", "starting_at"],
                name="uniq_rate_card_product_starting_at",
            )
        ]
        indexes = [
            models.Index(fields=["product_id", "starting_at"]),
        ]


class MetronomeInvoiceQuerySet(models.QuerySet):
    def timeline_for_customer(
        self,
        customer: MetronomeCustomer,
        *,
        statuses: list[str] | None = None,
    ):
        qs = self.filter(customer=customer).order_by("-start_timestamp")
        if statuses:
            qs = qs.filter(status__in=statuses)
        return qs


class MetronomeInvoice(MetronomeSyncBaseModel):
    customer = models.ForeignKey(
        MetronomeCustomer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    status = models.CharField(max_length=64, blank=True, default="")
    total = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    currency = models.CharField(max_length=16, blank=True, default="")
    start_timestamp = models.DateTimeField(null=True, blank=True)
    end_timestamp = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    objects = MetronomeInvoiceQuerySet.as_manager()

    class Meta:
        unique_together = ("metronome_id", "metronome_environment")
        indexes = [
            models.Index(fields=["metronome_environment", "status"]),
            models.Index(fields=["customer", "start_timestamp"]),
        ]


class MetronomeUsageAggregateQuerySet(models.QuerySet):
    def for_window(self, *, starting_on, ending_before, customer=None):
        qs = self.filter(window_start__gte=starting_on, window_end__lt=ending_before)
        if customer is not None:
            qs = qs.filter(customer=customer)
        return qs


class MetronomeUsageAggregate(AuditStampedModel):
    """Usage aggregate from Metronome; keyed by window + grouping dimensions."""

    customer = models.ForeignKey(
        MetronomeCustomer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_aggregates",
    )
    metronome_environment = models.CharField(max_length=32, default="sandbox")
    event_type = models.CharField(max_length=255, blank=True, default="")
    window_size = models.CharField(max_length=32, default="day")
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    value = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    groups = models.JSONField(default=dict, blank=True)
    grouping_key = models.CharField(max_length=255, blank=True, default="")
    raw_payload = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(default=timezone.now)

    objects = MetronomeUsageAggregateQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "metronome_environment",
                    "customer",
                    "event_type",
                    "window_size",
                    "window_start",
                    "window_end",
                    "grouping_key",
                ],
                name="uniq_usage_aggregate_dimensions",
            )
        ]
        indexes = [
            models.Index(
                fields=["metronome_environment", "event_type", "window_start"]
            ),
            models.Index(fields=["customer", "window_start"]),
        ]


class SyncCheckpoint(AuditStampedModel):
    """Sync progress owned by management commands; not a Metronome entity."""

    entity = models.CharField(max_length=64)
    metronome_environment = models.CharField(max_length=32, default="sandbox")
    cursor = models.CharField(max_length=255, blank=True, default="")
    window_start = models.DateTimeField(null=True, blank=True)
    window_end = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, default="idle")
    last_error = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    last_successful_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "metronome_environment"],
                name="uniq_checkpoint_entity_environment",
            )
        ]

    def __str__(self) -> str:
        return f"{self.entity}@{self.metronome_environment}"
