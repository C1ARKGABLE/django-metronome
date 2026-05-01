from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import IsoTimestamp, MetronomeIdentifier, MetronomeSchema


class WebhookEnvelopeSchema(MetronomeSchema):
    id: MetronomeIdentifier
    event_type: str
    created_at: IsoTimestamp | None = None
    livemode: bool = False
    data: dict[str, Any] = Field(default_factory=dict)
