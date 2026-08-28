"""Persist webhook signals and debounce batches in Azure Storage."""

from dataclasses import dataclass
from collections.abc import Mapping
from datetime import datetime
from itertools import islice
from typing import Any
import json

from repositories.change_notifications import (
    ChangeSignal, PendingBatch, ProviderName,
)


DEFAULT_QUEUE_NAME = "drive-change-signals"
DEFAULT_TABLE_NAME = "DriveWebhookState"
BATCH_PARTITION = "pending-batches"


@dataclass(frozen=True)
class QueuedSignal:
    """Validated signal paired with its private Azure acknowledgement receipt."""

    signal: ChangeSignal
    receipt: Any


def signal_to_json(signal: ChangeSignal) -> str:
    """Serialize a queue-safe signal without provider payload or private data."""
    return json.dumps({
        "provider": signal.provider,
        "identity": signal.identity,
        "received_at": signal.received_at.isoformat(),
    }, separators=(",", ":"))


def signal_from_json(value: str) -> ChangeSignal:
    """Parse and validate one durable notification signal."""
    try:
        payload = json.loads(value)
        return ChangeSignal(
            provider=payload["provider"],
            identity=payload["identity"],
            received_at=datetime.fromisoformat(payload["received_at"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Azure queue contains a malformed drive-change signal") from error


def batch_to_entity(batch: PendingBatch) -> dict[str, Any]:
    """Serialize a pending batch as one replaceable Azure Table entity."""
    return {
        "PartitionKey": BATCH_PARTITION,
        "RowKey": batch.provider,
        "Provider": batch.provider,
        "FirstReceivedAt": batch.first_received_at.isoformat(),
        "LastReceivedAt": batch.last_received_at.isoformat(),
        "DueAt": batch.due_at.isoformat(),
        "NotificationCount": batch.notification_count,
    }


def batch_from_entity(entity: dict[str, Any]) -> PendingBatch:
    """Parse and validate one Azure Table debounce entity."""
    try:
        return PendingBatch(
            provider=entity["Provider"],
            first_received_at=datetime.fromisoformat(entity["FirstReceivedAt"]),
            last_received_at=datetime.fromisoformat(entity["LastReceivedAt"]),
            due_at=datetime.fromisoformat(entity["DueAt"]),
            notification_count=int(entity["NotificationCount"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Azure Table contains malformed webhook batch state") from error


class AzureWebhookStore:
    """Queue notifications and maintain timer-owned debounce state."""

    def __init__(
        self,
        connection_string: str,
        *,
        queue_name: str = DEFAULT_QUEUE_NAME,
        table_name: str = DEFAULT_TABLE_NAME,
    ) -> None:
        if not connection_string.strip():
            raise ValueError("Azure storage connection string must not be empty")
        try:
            from azure.data.tables import TableServiceClient
            from azure.storage.queue import QueueClient
        except ImportError as error:
            raise RuntimeError(
                "Azure Table and Queue SDKs are required by the webhook host"
            ) from error

        self._queue = QueueClient.from_connection_string(
            connection_string, queue_name,
        )
        table_service = TableServiceClient.from_connection_string(connection_string)
        self._table = table_service.get_table_client(table_name)

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        queue_name: str = DEFAULT_QUEUE_NAME,
        table_name: str = DEFAULT_TABLE_NAME,
    ) -> "AzureWebhookStore":
        """Use a local connection string or the Function's managed identity."""
        connection_string = environment.get("AzureWebJobsStorage", "").strip()
        if connection_string:
            return cls(
                connection_string, queue_name=queue_name, table_name=table_name,
            )

        account_name = environment.get("AzureWebJobsStorage__accountName", "").strip()
        if not account_name:
            raise ValueError(
                "AzureWebJobsStorage or AzureWebJobsStorage__accountName is required"
            )
        try:
            from azure.data.tables import TableServiceClient
            from azure.identity import DefaultAzureCredential
            from azure.storage.queue import QueueClient
        except ImportError as error:
            raise RuntimeError(
                "Azure Identity, Table, and Queue SDKs are required by the webhook host"
            ) from error

        instance = cls.__new__(cls)
        managed_identity_client_id = environment.get(
            "AzureWebJobsStorage__clientId", ""
        ).strip()
        credential = DefaultAzureCredential(
            managed_identity_client_id=managed_identity_client_id or None,
        )
        instance._queue = QueueClient(
            f"https://{account_name}.queue.core.windows.net",
            queue_name,
            credential=credential,
        )
        table_service = TableServiceClient(
            f"https://{account_name}.table.core.windows.net",
            credential=credential,
        )
        instance._table = table_service.get_table_client(table_name)
        return instance

    def ensure_resources(self) -> None:
        """Idempotently create the small queue and table used by the host."""
        try:
            from azure.core.exceptions import ResourceExistsError
        except ImportError as error:
            raise RuntimeError("Azure Core is required by the webhook host") from error
        try:
            self._queue.create_queue()
        except ResourceExistsError:
            pass
        try:
            self._table.create_table()
        except ResourceExistsError:
            pass

    def enqueue(self, signal: ChangeSignal) -> None:
        """Durably append a validated provider signal."""
        self._queue.send_message(signal_to_json(signal))

    def receive_signals(self, *, max_messages: int = 512) -> tuple[list[QueuedSignal], int]:
        """Receive valid signals without deleting them before state is durable."""
        if max_messages < 1:
            raise ValueError("max_messages must be positive")
        signals = []
        rejected = 0
        messages = self._queue.receive_messages(
            messages_per_page=min(max_messages, 32),
            visibility_timeout=120,
        )
        for message in islice(messages, max_messages):
            try:
                signals.append(QueuedSignal(signal_from_json(message.content), message))
            except ValueError:
                rejected += 1
                self._queue.delete_message(message)
        return signals, rejected

    def acknowledge(self, queued_signal: QueuedSignal) -> None:
        """Delete a queue message only after its batch state has been saved."""
        self._queue.delete_message(queued_signal.receipt)

    def get_batch(self, provider: ProviderName) -> PendingBatch | None:
        """Return current debounce state for one provider, when present."""
        try:
            from azure.core.exceptions import ResourceNotFoundError
        except ImportError as error:
            raise RuntimeError("Azure Core is required by the webhook host") from error
        try:
            entity = self._table.get_entity(BATCH_PARTITION, provider)
        except ResourceNotFoundError:
            return None
        return batch_from_entity(entity)

    def save_batch(self, batch: PendingBatch) -> None:
        """Replace one provider's timer-owned debounce state."""
        try:
            from azure.data.tables import UpdateMode
        except ImportError as error:
            raise RuntimeError("Azure Tables is required by the webhook host") from error
        self._table.upsert_entity(batch_to_entity(batch), mode=UpdateMode.REPLACE)

    def list_batches(self) -> list[PendingBatch]:
        """Return the small set of currently pending provider batches."""
        entities = self._table.query_entities(
            query_filter=f"PartitionKey eq '{BATCH_PARTITION}'"
        )
        return [batch_from_entity(entity) for entity in entities]

    def delete_batch(self, provider: ProviderName) -> None:
        """Remove a successfully dispatched provider batch."""
        try:
            from azure.core.exceptions import ResourceNotFoundError
        except ImportError as error:
            raise RuntimeError("Azure Core is required by the webhook host") from error
        try:
            self._table.delete_entity(BATCH_PARTITION, provider)
        except ResourceNotFoundError:
            pass
