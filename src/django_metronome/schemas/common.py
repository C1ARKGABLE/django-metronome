from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

MetronomeIdentifier = Annotated[str, Field(min_length=1)]
IsoTimestamp = datetime


class MetronomeSchema(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    @property
    def unknown_fields(self) -> dict[str, Any]:
        return dict(self.model_extra or {})
