"""Execute provider-to-provider media migration without mounted cloud drives."""

from time import sleep
from typing import Protocol

from pandas import DataFrame
from sqlalchemy import Engine

from integrations.google.google_drive.client import (
    GoogleDriveRequestError,
    download_file_range as download_google_drive_file_range,
)
from integrations.microsoft.onedrive.client import (
    GraphRequestError,
    UPLOAD_FRAGMENT_GRANULARITY,
    cancel_upload_session as cancel_onedrive_upload_session,
    create_upload_session as create_onedrive_upload_session,
    get_upload_session_status as get_onedrive_upload_session_status,
    upload_chunk as upload_onedrive_chunk,
)
from repositories.ingest import discover_google_drive_migration


TRANSFER_CHUNK_SIZE = 32 * UPLOAD_FRAGMENT_GRANULARITY


class UpdateConsole(Protocol):
    """Minimal status surface required by cloud migration."""

    def add_update(self, message: str) -> None:
        """Emit a durable status message."""


def _next_upload_offset(status: dict) -> int:
    """Return the next sequential byte offset from an upload-session response."""
    ranges = status.get("nextExpectedRanges")
    if not isinstance(ranges, list) or not ranges or not isinstance(ranges[0], str):
        raise GraphRequestError(
            "OneDrive upload session did not report its next expected byte range"
        )
    start = ranges[0].split("-", 1)[0]
    if not start.isdigit():
        raise GraphRequestError(
            "OneDrive upload session returned a malformed expected byte range"
        )
    return int(start)


def _download_google_chunk(file_id: str, start: int, end: int) -> bytes:
    """Download a Google Drive range with bounded transient retries."""
    for attempt in range(3):
        try:
            return download_google_drive_file_range(file_id, start, end)
        except GoogleDriveRequestError:
            if attempt == 2:
                raise
            sleep(2 ** attempt)
    raise AssertionError("Google Drive download retry loop ended unexpectedly")


def transfer_google_file_to_onedrive(
    source_file_id: str,
    file_name: str,
    file_size: int,
    destination_folder_id: str,
) -> dict:
    """Stream one Google Drive blob into OneDrive without local file storage."""
    if not source_file_id:
        raise ValueError("source_file_id must not be empty")
    if not file_name:
        raise ValueError("file_name must not be empty")
    if file_size <= 0:
        raise ValueError("file_size must be positive")
    if not destination_folder_id:
        raise ValueError("destination_folder_id must not be empty")

    session = create_onedrive_upload_session(
        destination_folder_id,
        file_name,
        conflict_behavior="fail",
    )
    upload_url = session["uploadUrl"]
    offset = 0
    final_item = None
    try:
        while offset < file_size:
            end = min(offset + TRANSFER_CHUNK_SIZE, file_size) - 1
            content = _download_google_chunk(source_file_id, offset, end)
            for attempt in range(3):
                try:
                    response = upload_onedrive_chunk(
                        upload_url, content, offset, file_size,
                    )
                    break
                except GraphRequestError:
                    status = get_onedrive_upload_session_status(upload_url)
                    next_offset = _next_upload_offset(status)
                    if next_offset > offset:
                        response = status
                        break
                    if next_offset != offset or attempt == 2:
                        raise
                    sleep(2 ** attempt)

            expected_offset = end + 1
            if expected_offset < file_size:
                next_offset = _next_upload_offset(response)
                if next_offset != expected_offset:
                    raise GraphRequestError(
                        f"OneDrive expected byte {next_offset}, not {expected_offset}"
                    )
            else:
                final_item = response
            offset = expected_offset
    except Exception:
        try:
            cancel_onedrive_upload_session(upload_url)
        except GraphRequestError:
            pass
        raise

    if not isinstance(final_item, dict) or not isinstance(final_item.get("id"), str):
        raise GraphRequestError(
            f"OneDrive completed {file_name!r} without returning a file ID"
        )
    return final_item


def migrate_google_drive_cloud(
    engine: Engine,
    media_type: str,
    project_year: int,
    ui: UpdateConsole,
    *,
    dry_run: bool = True,
) -> DataFrame:
    """Plan and optionally execute missing Google Drive video copies."""
    plan = discover_google_drive_migration(engine, media_type, project_year)
    folder_count = plan.attrs.get("folder_count", 0)
    mapped_folder_count = plan.attrs.get("mapped_folder_count", 0)
    results = plan.copy()
    results.attrs.update(plan.attrs)
    if not results.empty:
        candidate_indexes = results.index[results["status"] == "candidate"]
        if dry_run:
            results.loc[candidate_indexes, "status"] = "would_copy"
        else:
            for index in candidate_indexes:
                row = results.loc[index]
                uploaded = transfer_google_file_to_onedrive(
                    row["source_file_id"],
                    row["file_name"],
                    int(row["file_size"]),
                    row["destination_folder_id"],
                )
                results.loc[index, "status"] = "copied"
                results.loc[index, "destination_item_id"] = uploaded["id"]

    counts = results["status"].value_counts().to_dict() if not results.empty else {}
    action_summary = (
        ", ".join(
            f"{count} {status.replace('_', ' ')}"
            for status, count in sorted(counts.items())
        )
        if counts else "0 video candidates"
    )
    ui.add_update(
        f"Google Drive cloud migration for {media_type} {project_year}: "
        f"{mapped_folder_count} of {folder_count} folder pairs mapped; "
        f"{action_summary}."
    )
    return results
