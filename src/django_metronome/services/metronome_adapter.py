from __future__ import annotations

from collections.abc import Callable, Iterable
from enum import StrEnum
from typing import Any

from metronome import Metronome

from django_metronome.client import build_metronome_client


class MetronomeApiVersion(StrEnum):
    V1 = "v1"
    V2 = "v2"


class MetronomeAdapter:
    """
    Anti-corruption boundary for all Metronome SDK access.

    Keep SDK-specific surface area in this class so the rest of the
    Django app can depend on stable plain-Python data structures.
    """

    def __init__(self, client: Metronome | None = None) -> None:
        self._client = client or build_metronome_client()

    @property
    def client(self) -> Metronome:
        return self._client

    def version_resource(self, version: MetronomeApiVersion) -> Any:
        if version == MetronomeApiVersion.V1:
            return self._client.v1
        if version == MetronomeApiVersion.V2:
            return self._client.v2
        raise ValueError(f"Unsupported Metronome API version: {version}")

    def collect_paginated(
        self,
        loader: Callable[..., Iterable[Any]],
        /,
        **kwargs: Any,
    ) -> list[Any]:
        """
        Normalize SDK pagination to a concrete list.

        The provided loader should return an iterable (sync iterator, page
        iterator, or plain list) from the Metronome SDK.
        """

        return list(loader(**kwargs))

    def retrieve_customer(self, customer_id: str) -> dict[str, Any]:
        """
        Retrieve and normalize a customer payload from Metronome.
        """

        response = self._client.v1.customers.retrieve({"customer_id": customer_id})
        return dict(response.data.to_dict())
