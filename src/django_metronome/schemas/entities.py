from __future__ import annotations

from pydantic import Field

from .common import IsoTimestamp, MetronomeIdentifier, MetronomeSchema


class CustomerWriteSchema(MetronomeSchema):
    id: MetronomeIdentifier
    name: str | None = None
    ingest_aliases: list[str] = Field(default_factory=list)
    archived_at: IsoTimestamp | None = None
    livemode: bool = False


class ContractWriteSchema(MetronomeSchema):
    id: MetronomeIdentifier
    customer_id: MetronomeIdentifier
    status: str | None = None
    starting_at: IsoTimestamp | None = None
    ending_before: IsoTimestamp | None = None
    livemode: bool = False
