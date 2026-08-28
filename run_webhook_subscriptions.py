"""Register and renew OneDrive and Google Drive webhook subscriptions."""

import argparse
from pathlib import Path

from common.config import read_toml
from integrations.microsoft.azure.subscription_store import AzureSubscriptionStore
from integrations.microsoft.onedrive.client import find_folder_id
from integrations.microsoft.onedrive.subscriptions import delete_subscription
from integrations.google.google_drive.subscriptions import stop_channel
from repositories.webhook_subscriptions import (
    reconcile_google_drive_channel,
    reconcile_onedrive_subscription,
)


def _secret_text(path: Path, label: str) -> str:
    """Read a downloaded secret file without printing its contents."""
    if not path.is_file():
        raise FileNotFoundError(f"{label} file does not exist")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"{label} file is empty")
    return value


def _media_root() -> str:
    """Return the configured cloud-media root watched by the lifecycle."""
    try:
        value = read_toml("webhooks")["drive_changes"]["scope"]["media_root"]
    except (KeyError, TypeError) as error:
        raise ValueError(
            "config/webhooks.toml is missing drive_changes.scope.media_root"
        ) from error
    if not isinstance(value, str) or not value.strip():
        raise ValueError("drive_changes.scope.media_root must not be empty")
    return value.strip()


def _onedrive_subscription_folder_id() -> str | None:
    """Resolve the configured Graph subscription target without guessing."""
    try:
        target = read_toml("webhooks")["drive_changes"]["scope"][
            "onedrive_subscription_target"
        ]
    except (KeyError, TypeError) as error:
        raise ValueError(
            "config/webhooks.toml is missing "
            "drive_changes.scope.onedrive_subscription_target"
        ) from error
    match target:
        case "root":
            return None
        case "media_root":
            return find_folder_id(_media_root())
        case _:
            raise ValueError(
                "onedrive_subscription_target must be 'root' or 'media_root'"
            )


def reconcile(
    storage_account: str,
    onedrive_url: str,
    google_drive_url: str,
    onedrive_client_state_file: Path,
    google_channel_token_file: Path,
    *,
    apply: bool = False,
) -> None:
    """Reconcile both providers and persist only successful applied state."""
    store = AzureSubscriptionStore.from_account_name(storage_account)
    if apply:
        store.ensure_table()
    folder_id = _onedrive_subscription_folder_id()
    client_state = _secret_text(
        onedrive_client_state_file, "OneDrive client state"
    )
    channel_token = _secret_text(
        google_channel_token_file, "Google Drive channel token"
    )

    previous_onedrive = store.get("onedrive")
    onedrive_state, onedrive_action = reconcile_onedrive_subscription(
        previous_onedrive,
        onedrive_url,
        client_state,
        folder_id=folder_id,
        apply=apply,
    )
    if apply and onedrive_state:
        store.save(onedrive_state)
        if (
            previous_onedrive
            and previous_onedrive.external_id != onedrive_state.external_id
        ):
            try:
                delete_subscription(previous_onedrive.external_id)
            except Exception:
                print(
                    "Warning: the superseded OneDrive subscription could not "
                    "be removed; notification deduplication remains active."
                )
    print(
        f"OneDrive subscription: {onedrive_action.action}; "
        f"expiration={onedrive_action.expires_at or 'pending provider response'}"
    )

    previous_google = store.get("google_drive")
    google_state, google_action = reconcile_google_drive_channel(
        previous_google,
        google_drive_url,
        channel_token,
        apply=apply,
    )
    if apply and google_state:
        store.save(google_state)
        if (
            previous_google
            and previous_google.external_id != google_state.external_id
            and previous_google.resource_id
        ):
            try:
                stop_channel(
                    previous_google.external_id,
                    previous_google.resource_id,
                )
            except Exception:
                # Channel overlap is safer than deleting newly persisted state.
                print(
                    "Warning: the superseded Google Drive channel could not "
                    "be stopped; notification deduplication remains active."
                )
    print(
        f"Google Drive channel: {google_action.action}; "
        f"expiration={google_action.expires_at or 'pending provider response'}"
    )


def main() -> None:
    """Parse lifecycle arguments and default to a non-mutating preview."""
    parser = argparse.ArgumentParser(
        description="Register or renew cloud-drive webhook subscriptions.",
    )
    parser.add_argument("--storage-account", required=True)
    parser.add_argument("--onedrive-url", required=True)
    parser.add_argument("--google-drive-url", required=True)
    parser.add_argument(
        "--onedrive-client-state-file", type=Path, required=True,
    )
    parser.add_argument(
        "--google-channel-token-file", type=Path, required=True,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    reconcile(
        arguments.storage_account,
        arguments.onedrive_url,
        arguments.google_drive_url,
        arguments.onedrive_client_state_file,
        arguments.google_channel_token_file,
        apply=arguments.apply,
    )


if __name__ == "__main__":
    main()
