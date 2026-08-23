"""Coalesce cloud repository notifications into bounded workflow batches."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

from common.config import read_toml


ProviderName = Literal["google_drive", "onedrive"]
WORKFLOW_EVENTS: dict[ProviderName, str] = {
    "google_drive": "google_drive_changed",
    "onedrive": "onedrive_changed",
}


@dataclass(frozen=True)
class DebouncePolicy:
    """Validated provider-neutral timing policy for change batches."""

    quiet_window: timedelta
    maximum_wait: timedelta

    def __post_init__(self) -> None:
        if self.quiet_window <= timedelta(0) or self.maximum_wait <= timedelta(0):
            raise ValueError("debounce windows must be positive")
        if self.quiet_window > self.maximum_wait:
            raise ValueError("quiet_window cannot exceed maximum_wait")


def _configured_minutes(value: object, field_name: str) -> timedelta:
    """Convert one positive numeric TOML minute value to a duration."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(
            f"webhooks.drive_changes.debounce.{field_name} must be positive"
        )
    return timedelta(minutes=value)


@lru_cache(maxsize=1)
def get_debounce_policy() -> DebouncePolicy:
    """Load and validate the checked-in drive-change debounce policy."""
    try:
        config = read_toml("webhooks")["drive_changes"]["debounce"]
        quiet_window = _configured_minutes(
            config["quiet_minutes"], "quiet_minutes",
        )
        maximum_wait = _configured_minutes(
            config["maximum_wait_minutes"], "maximum_wait_minutes",
        )
    except (KeyError, TypeError) as error:
        raise ValueError(
            "config/webhooks.toml is missing the drive_changes debounce policy"
        ) from error
    return DebouncePolicy(quiet_window, maximum_wait)


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
    quiet_window: timedelta | None = None,
    maximum_wait: timedelta | None = None,
) -> PendingBatch:
    """Start or extend a batch without allowing indefinite postponement."""
    if quiet_window is None or maximum_wait is None:
        configured_policy = get_debounce_policy()
        quiet_window = (
            quiet_window
            if quiet_window is not None
            else configured_policy.quiet_window
        )
        maximum_wait = (
            maximum_wait
            if maximum_wait is not None
            else configured_policy.maximum_wait
        )
    policy = DebouncePolicy(quiet_window, maximum_wait)
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
    due_at = min(
        last_received + policy.quiet_window,
        first_received + policy.maximum_wait,
    )
    return PendingBatch(
        provider=signal.provider,
        first_received_at=first_received,
        last_received_at=last_received,
        due_at=due_at,
        notification_count=(existing.notification_count if existing else 0) + 1,
    )
