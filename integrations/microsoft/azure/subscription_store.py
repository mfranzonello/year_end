"""Persist provider-neutral webhook subscription state in Azure Tables."""

from collections.abc import Mapping
from datetime import datetime
import re

from repositories.webhook_subscriptions import ProviderSubscriptionState


SUBSCRIPTION_PARTITION = "provider-subscriptions"
DEFAULT_TABLE_NAME = "DriveWebhookState"


def state_to_entity(state: ProviderSubscriptionState) -> dict:
    """Serialize subscription state without provider tokens or credentials."""
    entity = {
        "PartitionKey": SUBSCRIPTION_PARTITION,
        "RowKey": state.provider,
        "Provider": state.provider,
        "ExternalId": state.external_id,
        "ExpiresAt": state.expires_at.isoformat(),
        "NotificationUrl": state.notification_url,
        "ResourceId": state.resource_id,
        "Cursor": state.cursor,
        "TargetResource": state.target_resource,
    }
    return {key: value for key, value in entity.items() if value is not None}


def state_from_entity(entity: Mapping) -> ProviderSubscriptionState:
    """Parse and validate one Azure Table subscription entity."""
    try:
        return ProviderSubscriptionState(
            provider=entity["Provider"],
            external_id=entity["ExternalId"],
            expires_at=datetime.fromisoformat(entity["ExpiresAt"]),
            notification_url=entity["NotificationUrl"],
            resource_id=entity.get("ResourceId") or None,
            cursor=entity.get("Cursor") or None,
            target_resource=entity.get("TargetResource") or None,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Azure Table contains malformed subscription state") from error


class AzureSubscriptionStore:
    """Read and replace the two small provider subscription records."""

    def __init__(self, table_client) -> None:
        self._table = table_client

    @classmethod
    def from_account_name(
        cls,
        account_name: str,
        *,
        table_name: str = DEFAULT_TABLE_NAME,
    ) -> "AzureSubscriptionStore":
        """Authenticate through the active Azure identity without account keys."""
        if not re.fullmatch(r"[a-z0-9]{3,24}", account_name):
            raise ValueError(
                "account_name must contain 3-24 lowercase letters or digits"
            )
        try:
            from azure.data.tables import TableServiceClient
            from azure.identity import DefaultAzureCredential
        except ImportError as error:
            raise RuntimeError(
                "Azure Identity and Tables SDKs are required for subscription state"
            ) from error
        service = TableServiceClient(
            f"https://{account_name}.table.core.windows.net",
            credential=DefaultAzureCredential(),
        )
        return cls(service.get_table_client(table_name))

    def ensure_table(self) -> None:
        """Idempotently create the state table before an applied reconciliation."""
        try:
            from azure.core.exceptions import ResourceExistsError
        except ImportError as error:
            raise RuntimeError("Azure Core is required for subscription state") from error
        try:
            self._table.create_table()
        except ResourceExistsError:
            pass

    def get(self, provider: str) -> ProviderSubscriptionState | None:
        """Return one provider's state when it exists."""
        try:
            from azure.core.exceptions import ResourceNotFoundError
        except ImportError as error:
            raise RuntimeError("Azure Core is required for subscription state") from error
        try:
            entity = self._table.get_entity(SUBSCRIPTION_PARTITION, provider)
        except ResourceNotFoundError:
            return None
        return state_from_entity(entity)

    def save(self, state: ProviderSubscriptionState) -> None:
        """Replace one provider's state only after provider success."""
        try:
            from azure.data.tables import UpdateMode
        except ImportError as error:
            raise RuntimeError("Azure Tables is required for subscription state") from error
        self._table.upsert_entity(state_to_entity(state), mode=UpdateMode.REPLACE)
