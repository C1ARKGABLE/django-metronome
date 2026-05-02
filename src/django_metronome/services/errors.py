"""Stable integration errors for Metronome outbound calls (Phase 1.5 provisioning)."""

from __future__ import annotations

from typing import Any

from metronome import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    MetronomeError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)


class MetronomeProvisioningError(RuntimeError):
    """Raised when provisioning fails or the API response shape is unexpected."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


def translate_sdk_exception(exc: BaseException) -> MetronomeProvisioningError:
    """Map Metronome SDK errors to library-stable exceptions for integrators."""

    if isinstance(exc, ConflictError):
        return MetronomeProvisioningError(
            "Metronome conflict (duplicate uniqueness_key or ingest alias). "
            "No mirror changes after the failed API call.",
            cause=exc,
        )
    if isinstance(exc, NotFoundError):
        return MetronomeProvisioningError(
            "Metronome resource not found (404).",
            cause=exc,
        )
    if isinstance(exc, BadRequestError):
        return MetronomeProvisioningError(
            f"Metronome rejected the request (400): {_safe_body(exc)}",
            cause=exc,
        )
    if isinstance(exc, AuthenticationError):
        return MetronomeProvisioningError(
            "Metronome authentication failed (401).",
            cause=exc,
        )
    if isinstance(exc, PermissionDeniedError):
        return MetronomeProvisioningError(
            "Metronome permission denied (403).",
            cause=exc,
        )
    if isinstance(exc, RateLimitError):
        return MetronomeProvisioningError(
            "Metronome rate limit exceeded (429).",
            cause=exc,
        )
    if isinstance(exc, APIConnectionError):
        return MetronomeProvisioningError("Metronome API connection error.", cause=exc)
    if isinstance(exc, APIError):
        code = getattr(exc, "status_code", "?")
        return MetronomeProvisioningError(
            f"Metronome API error ({code}): {_safe_body(exc)}",
            cause=exc,
        )
    if isinstance(exc, MetronomeError):
        return MetronomeProvisioningError(str(exc), cause=exc)
    return MetronomeProvisioningError(str(exc), cause=exc)


def _safe_body(exc: APIError) -> str:
    body: Any = getattr(exc, "body", None)
    if body is None:
        return str(exc)
    if isinstance(body, str):
        return body[:500]
    try:
        return str(body)[:500]
    except Exception:
        return str(exc)
