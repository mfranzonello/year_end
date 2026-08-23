"""Azure Functions entry point for debounced cloud-drive notifications."""

import logging
import os
from functools import lru_cache

import azure.functions as func

from integrations.github.actions.client import dispatch_repository_event
from integrations.microsoft.azure.webhook_handlers import (
    handle_google_drive_webhook, handle_onedrive_webhook,
)
from integrations.microsoft.azure.webhook_service import process_webhook_batches
from integrations.microsoft.azure.webhook_store import AzureWebhookStore
from integrations.google.google_drive.webhook import GoogleDriveWebhookError
from integrations.microsoft.onedrive.webhook import WebhookNotificationError


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def _required_setting(name: str) -> str:
    """Return a required Function setting without exposing its value."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required Function setting: {name}")
    return value


def _optional_setting(name: str) -> str | None:
    """Return a stripped optional Function setting."""
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


@lru_cache(maxsize=1)
def _store() -> AzureWebhookStore:
    """Return the configured Azure Storage adapter."""
    store = AzureWebhookStore.from_environment(os.environ)
    store.ensure_resources()
    return store


def _http_response(result) -> func.HttpResponse:
    """Enqueue every trusted signal before acknowledging its notification."""
    store = _store() if result.signals else None
    for signal in result.signals:
        store.enqueue(signal)
    return func.HttpResponse(
        result.body,
        status_code=result.status_code,
        mimetype=result.content_type,
    )


@app.route(route="webhooks/onedrive", methods=["GET", "POST"])
def onedrive_webhook(request: func.HttpRequest) -> func.HttpResponse:
    """Validate and durably acknowledge OneDrive change notifications."""
    try:
        result = handle_onedrive_webhook(
            request.get_body(),
            validation_token=request.params.get("validationToken"),
            expected_client_state=_required_setting("ONEDRIVE_WEBHOOK_CLIENT_STATE"),
            expected_subscription_id=_optional_setting("ONEDRIVE_SUBSCRIPTION_ID"),
        )
    except WebhookNotificationError:
        logging.warning("Rejected an invalid OneDrive webhook request")
        return func.HttpResponse("Invalid notification", status_code=400)
    return _http_response(result)


@app.route(route="webhooks/google-drive", methods=["POST"])
def google_drive_webhook(request: func.HttpRequest) -> func.HttpResponse:
    """Validate and durably acknowledge Google Drive push notifications."""
    try:
        result = handle_google_drive_webhook(
            request.headers,
            expected_channel_token=_required_setting("GOOGLE_DRIVE_CHANNEL_TOKEN"),
            expected_channel_id=_optional_setting("GOOGLE_DRIVE_CHANNEL_ID"),
            expected_resource_id=_optional_setting("GOOGLE_DRIVE_RESOURCE_ID"),
        )
    except GoogleDriveWebhookError:
        logging.warning("Rejected an invalid Google Drive webhook request")
        return func.HttpResponse("Invalid notification", status_code=400)
    return _http_response(result)


def _dispatch(batch) -> None:
    """Send a due provider batch to its selected GitHub Actions workflow."""
    dispatch_repository_event(
        _required_setting("YEAR_END_GITHUB_REPOSITORY"),
        batch.workflow_event,
        app_id=_required_setting("YEAR_END_GITHUB_APP_ID"),
        installation_id=_required_setting("YEAR_END_GITHUB_APP_INSTALLATION_ID"),
        private_key=_required_setting("YEAR_END_GITHUB_APP_PRIVATE_KEY"),
        client_payload={"notification_count": batch.notification_count},
    )


@app.timer_trigger(
    schedule="0 * * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def dispatch_due_batches(_timer: func.TimerRequest) -> None:
    """Once per minute, extend debounce state and dispatch due work."""
    accepted, rejected, dispatched = process_webhook_batches(_store(), _dispatch)
    logging.info(
        "Processed %s drive signals, rejected %s, dispatched %s batches",
        accepted,
        rejected,
        dispatched,
    )
