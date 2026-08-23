"""Ingest media and repository metadata from source providers."""

from pathlib import Path
from time import sleep
from typing import Protocol

from pandas import DataFrame
from sqlalchemy import Engine

from common.video import VIDEO_EXTS
from database.db_project import fetch_shared_albums
from database.db_project import (
    fetch_folder_transfer_locations, fetch_project_folders,
    update_folder_locations_and_shares,
)
from integrations.google.google_drive.client import (
    GoogleDriveRequestError,
    download_file_range as download_google_drive_file_range,
    find_folder_id as find_google_drive_folder_id,
    get_share_link as get_google_drive_share_link,
    get_or_create_share_link as get_or_create_google_drive_share_link,
    list_child_folders as list_google_drive_child_folders,
    list_descendant_files as list_google_drive_descendant_files,
)
from integrations.microsoft.onedrive.client import (
    GraphRequestError,
    UPLOAD_FRAGMENT_GRANULARITY,
    cancel_upload_session as cancel_onedrive_upload_session,
    create_upload_session as create_onedrive_upload_session,
    get_upload_session_status as get_onedrive_upload_session_status,
    list_descendant_files as list_onedrive_descendant_files,
    upload_chunk as upload_onedrive_chunk,
)
from scraping.photos import source_allowed, harvest_shared_album


TRANSFER_CHUNK_SIZE = 32 * UPLOAD_FRAGMENT_GRANULARITY
SOURCE_REPOSITORY = "Google Drive"
DESTINATION_REPOSITORY = "OneDrive"


class UpdateConsole(Protocol):
    """Minimal status surface required by cloud ingestion."""

    def add_update(self, message: str) -> None:
        """Emit a durable status message."""


def ingest_google_drive_folder_shares(
    engine: Engine,
    project_root: str,
    media_type: str,
    supfolder_name: str,
    project_year: int,
    dry_run: bool = True,
    create_missing_shares: bool = True,
) -> DataFrame:
    """Match source Google Drive folders to project records and ensure shares."""
    project_folders = fetch_project_folders(engine, project_year, media_type)
    if project_folders.empty:
        return DataFrame()

    year_path = "/".join((project_root.strip("/\\"), supfolder_name, str(project_year)))
    try:
        year_folder_id = find_google_drive_folder_id(year_path)
    except GoogleDriveRequestError as error:
        if "was not found" not in str(error):
            raise
        results = DataFrame()
        results.attrs["expected_count"] = len(project_folders)
        return results
    cloud_folders = list_google_drive_child_folders(year_folder_id)
    cloud_by_name = {folder.get("name"): folder for folder in cloud_folders}
    if len(cloud_by_name) != len(cloud_folders):
        raise ValueError("The Google Drive year folder contains duplicate top-level folder names")

    matched = []
    for row in project_folders.to_dict(orient="records"):
        cloud_folder = cloud_by_name.get(row["folder_name"])
        if cloud_folder is None:
            continue
        item_id = cloud_folder.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        share_function = (
            get_or_create_google_drive_share_link
            if create_missing_shares
            else get_google_drive_share_link
        )
        matched.append({
            **row,
            "repository_item_id": item_id,
            "share_url": None if dry_run else share_function(item_id),
        })

    results = DataFrame(matched)
    results.attrs["expected_count"] = len(project_folders)
    if not dry_run:
        update_folder_locations_and_shares(engine, results, "Google Drive", is_canonical=False)
    return results


def _video_items(items: list[dict]) -> list[dict]:
    """Return configured video files from provider traversal results."""
    return [
        item for item in items
        if isinstance(item.get("name"), str)
        and Path(item["name"]).suffix.lower() in VIDEO_EXTS
    ]


def _file_size(item: dict, provider: str) -> int:
    """Return a non-negative provider byte size or raise an actionable error."""
    try:
        size = int(item.get("size"))
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{provider} returned no usable size for {item.get('name')!r}"
        ) from error
    if size <= 0:
        raise ValueError(
            f"{provider} returned a non-positive size for {item.get('name')!r}"
        )
    return size


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
    source_file: dict,
    destination_folder_id: str,
) -> dict:
    """Stream one Google Drive blob into a OneDrive folder without local storage."""
    source_id = source_file.get("id")
    file_name = source_file.get("name")
    if not isinstance(source_id, str) or not source_id:
        raise GoogleDriveRequestError("Google Drive returned a file without an ID")
    if not isinstance(file_name, str) or not file_name:
        raise GoogleDriveRequestError("Google Drive returned a file without a name")
    if source_file.get("capabilities", {}).get("canDownload") is False:
        raise GoogleDriveRequestError(
            f"Google Drive does not permit downloading {file_name!r}"
        )

    total = _file_size(source_file, SOURCE_REPOSITORY)
    session = create_onedrive_upload_session(
        destination_folder_id,
        file_name,
        conflict_behavior="fail",
    )
    upload_url = session["uploadUrl"]
    offset = 0
    final_item = None
    try:
        while offset < total:
            end = min(offset + TRANSFER_CHUNK_SIZE, total) - 1
            content = _download_google_chunk(source_id, offset, end)
            for attempt in range(3):
                try:
                    response = upload_onedrive_chunk(
                        upload_url, content, offset, total,
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
            if expected_offset < total:
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


def ingest_google_drive_cloud(
    engine: Engine,
    media_type: str,
    project_year: int,
    ui: UpdateConsole,
    *,
    dry_run: bool = True,
) -> DataFrame:
    """Compare mapped provider folders and optionally stream missing videos."""
    locations = fetch_folder_transfer_locations(
        engine,
        project_year,
        media_type,
        SOURCE_REPOSITORY,
        DESTINATION_REPOSITORY,
    )
    if locations["folder_id"].duplicated().any():
        raise ValueError(
            "A project folder has multiple locations in a transfer repository"
        )

    rows = []
    for folder in locations.to_dict(orient="records"):
        source_folder_id = folder.get("source_item_id")
        destination_folder_id = folder.get("destination_item_id")
        base = {
            "folder_id": folder["folder_id"],
            "folder_name": folder["folder_name"],
            "project_year": project_year,
            "media_type": media_type,
        }
        if not isinstance(source_folder_id, str) or not source_folder_id:
            rows.append({**base, "file_name": None, "file_size": None,
                         "status": "missing_source_location"})
            continue
        if not isinstance(destination_folder_id, str) or not destination_folder_id:
            rows.append({**base, "file_name": None, "file_size": None,
                         "status": "missing_destination_location"})
            continue

        source_files_by_id = {
            item["id"]: item
            for item in _video_items(
                list_google_drive_descendant_files(source_folder_id)
            )
            if isinstance(item.get("id"), str) and item["id"]
        }
        source_files = sorted(
            source_files_by_id.values(),
            key=lambda item: (item["name"].casefold(), item["id"]),
        )
        destination_files = list_onedrive_descendant_files(destination_folder_id)
        destination_by_name: dict[str, list[dict]] = {}
        for item in destination_files:
            name = item.get("name")
            if isinstance(name, str) and name:
                destination_by_name.setdefault(name.casefold(), []).append(item)

        source_name_counts: dict[str, int] = {}
        for item in source_files:
            folded_name = item["name"].casefold()
            source_name_counts[folded_name] = source_name_counts.get(folded_name, 0) + 1

        for source_file in source_files:
            file_name = source_file["name"]
            try:
                size = _file_size(source_file, SOURCE_REPOSITORY)
            except ValueError:
                rows.append({**base, "file_name": file_name, "file_size": None,
                             "status": "invalid_source_size"})
                continue
            file_row = {**base, "file_name": file_name, "file_size": size}
            if source_file.get("capabilities", {}).get("canDownload") is False:
                rows.append({**file_row, "status": "download_not_allowed"})
                continue
            if source_name_counts[file_name.casefold()] > 1:
                rows.append({**file_row, "status": "duplicate_source_name"})
                continue

            destination_matches = destination_by_name.get(file_name.casefold(), [])
            if destination_matches:
                destination_sizes = {
                    int(item["size"])
                    for item in destination_matches
                    if str(item.get("size", "")).isdigit()
                }
                status = (
                    "already_present"
                    if len(destination_matches) == 1 and destination_sizes == {size}
                    else "destination_name_conflict"
                )
                rows.append({**file_row, "status": status})
                continue

            if dry_run:
                rows.append({**file_row, "status": "would_copy"})
                continue

            uploaded = transfer_google_file_to_onedrive(
                source_file, destination_folder_id,
            )
            rows.append({
                **file_row,
                "status": "copied",
                "destination_item_id": uploaded["id"],
            })

    results = DataFrame(rows)
    counts = results["status"].value_counts().to_dict() if not results.empty else {}
    mapped_pairs = sum(
        isinstance(row.get("source_item_id"), str) and bool(row["source_item_id"])
        and isinstance(row.get("destination_item_id"), str)
        and bool(row["destination_item_id"])
        for row in locations.to_dict(orient="records")
    )
    action_summary = (
        ", ".join(
            f"{count} {status.replace('_', ' ')}"
            for status, count in sorted(counts.items())
        )
        if counts else "0 video candidates"
    )
    ui.add_update(
        f"Google Drive cloud ingest for {media_type} {project_year}: "
        f"{mapped_pairs} of {len(locations)} folder pairs mapped; {action_summary}."
    )
    return results


def copy_from_web(engine, one_drive_folder, google=True, icloud=True, headless=False):
    albums = fetch_shared_albums(engine)
    for _, (_, url, folder_name, project_year, supfolder_name,
            scrape_name, browser_name, profile_name, notes) in albums.iterrows():
        
        if notes:
            print(f'Skipping album: {notes}')

        else:
            share_source = scrape_name.lower()
            browser_profile = f'{profile_name} {scrape_name}'
            download_directory = one_drive_folder / supfolder_name / str(project_year) / folder_name

            if source_allowed(share_source, google=google, icloud=icloud):
                harvest_shared_album(url, download_directory, scrape_name, browser_name, browser_profile,
                                     headless=headless)
