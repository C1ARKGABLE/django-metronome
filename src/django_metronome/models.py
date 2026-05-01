from django.db import models
from django.utils import timezone


class AuditStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class MetronomeSyncBaseModel(AuditStampedModel):
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
