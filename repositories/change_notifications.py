"""Coalesce cloud repository notifications into bounded workflow batches."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal


ProviderName = Literal["google_drive", "onedrive"]
QUIET_WINDOW = timedelta(minutes=10)
MAXIMUM_BATCH_WAIT = timedelta(minutes=30)
WORKFLOW_EVENTS: dict[ProviderName, str] = {
    "google_drive": "google_drive_changed",
    "onedrive": "onedrive_changed",
}


def _aware_utc(value: datetime) -> datetime:
    """Return an aware UTC timestamp or reject ambiguous queue state."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("notification timestamps must include a timezone")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ChangeSignal:
    """Small, non-sensitive provider notification stored in the durable queue."""

    provider: ProviderName
    identity: str
    received_at: datetime

    def __post_init__(self) -> None:
        if self.provider not in WORKFLOW_EVENTS:
            raise ValueError(f"Unsupported change provider: {self.provider!r}")
        if not self.identity:
            raise ValueError("notification identity must not be empty")
        object.__setattr__(self, "received_at", _aware_utc(self.received_at))


@dataclass(frozen=True)
class PendingBatch:
    """Trailing-edge debounce state with a hard maximum wait."""

    provider: ProviderName
    first_received_at: datetime
    last_received_at: datetime
    due_at: datetime
    notification_count: int

    def __post_init__(self) -> None:
        if self.provider not in WORKFLOW_EVENTS:
            raise ValueError(f"Unsupported batch provider: {self.provider!r}")
        for field_name in ("first_received_at", "last_received_at", "due_at"):
            object.__setattr__(self, field_name, _aware_utc(getattr(self, field_name)))
        if self.first_received_at > self.last_received_at:
            raise ValueError("batch first timestamp cannot follow its last timestamp")
        if self.notification_count < 1:
            raise ValueError("notification_count must be positive")

    @property
    def workflow_event(self) -> str:
        """Return the GitHub repository-dispatch event for this provider."""
        return WORKFLOW_EVENTS[self.provider]

    def is_due(self, now: datetime) -> bool:
        """Return whether the batch can be dispatched at ``now``."""
        return _aware_utc(now) >= self.due_at


def extend_batch(
    signal: ChangeSignal,
    existing: PendingBatch | None = None,
    *,
    quiet_window: timedelta = QUIET_WINDOW,
    maximum_wait: timedelta = MAXIMUM_BATCH_WAIT,
) -> PendingBatch:
    """Start or extend a batch without allowing indefinite postponement."""
    if quiet_window <= timedelta(0) or maximum_wait <= timedelta(0):
        raise ValueError("debounce windows must be positive")
    if quiet_window > maximum_wait:
        raise ValueError("quiet_window cannot exceed maximum_wait")
    if existing and existing.provider != signal.provider:
        raise ValueError("cannot combine notifications from different providers")

    first_received = min(
        existing.first_received_at if existing else signal.received_at,
        signal.received_at,
    )
    last_received = max(
        existing.last_received_at if existing else signal.received_at,
        signal.received_at,
    )
    due_at = min(last_received + quiet_window, first_received + maximum_wait)
    return PendingBatch(
        provider=signal.provider,
        first_received_at=first_received,
        last_received_at=last_received,
        due_at=due_at,
        notification_count=(existing.notification_count if existing else 0) + 1,
    )
