"""Drain drive notifications, enforce debounce windows, and dispatch workflows."""

from collections.abc import Callable
from datetime import datetime, timezone

from integrations.microsoft.azure.webhook_store import AzureWebhookStore
from repositories.change_notifications import PendingBatch, extend_batch


DispatchFunction = Callable[[PendingBatch], None]


def process_webhook_batches(
    store: AzureWebhookStore,
    dispatch: DispatchFunction,
    *,
    now: datetime | None = None,
) -> tuple[int, int, int]:
    """Fold queued signals into batches and dispatch every due provider once."""
    current_time = now or datetime.now(timezone.utc)
    queued_signals, rejected = store.receive_signals()
    batches_by_provider = {batch.provider: batch for batch in store.list_batches()}
    for queued_signal in queued_signals:
        signal = queued_signal.signal
        batch = extend_batch(signal, batches_by_provider.get(signal.provider))
        batches_by_provider[signal.provider] = batch
        store.save_batch(batch)
        store.acknowledge(queued_signal)

    dispatched = 0
    for batch in batches_by_provider.values():
        if not batch.is_due(current_time):
            continue
        dispatch(batch)
        store.delete_batch(batch.provider)
        dispatched += 1
    return len(queued_signals), rejected, dispatched
