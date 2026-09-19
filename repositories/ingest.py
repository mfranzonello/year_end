"""Ingest media and repository metadata from source providers."""

from datetime import datetime, timezone
from pathlib import Path

from pandas import DataFrame
from sqlalchemy import Engine

from common.video import VIDEO_EXTS
from database.db_project import (
    fetch_file_location_candidates, fetch_folder_transfer_locations,
    fetch_project_folders,
    update_folder_locations_and_shares,
)
from integrations.google.google_drive.client import (
    GoogleDriveRequestError,
    find_folder_id as find_google_drive_folder_id,
    get_share_link as get_google_drive_share_link,
    get_or_create_share_link as get_or_create_google_drive_share_link,
    list_child_folders as list_google_drive_child_folders,
    list_descendant_files as list_google_drive_descendant_files,
)
from integrations.microsoft.onedrive.client import (
    list_descendant_files as list_onedrive_descendant_files,
)


SOURCE_REPOSITORY = "Google Drive"
DESTINATION_REPOSITORY = "OneDrive"


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


def _location_key(file_name: str, relative_parent: str | None) -> tuple[str, str]:
    """Return a provider-neutral, case-insensitive relative file key."""
    parent = (relative_parent or "").replace("\\", "/").strip("/")
    return parent.casefold(), file_name.casefold()


def parse_created_timestamp(value: object, provider: str) -> datetime:
    """Parse a provider UTC timestamp for the database's naive UTC column."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{provider} returned no created timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{provider} returned an invalid created timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def match_discovered_file_locations(
    logical_files: DataFrame,
    discovered_files: DataFrame,
    repository_name: str,
    is_canonical: bool,
) -> DataFrame:
    """Match one discovery inventory to logical database files."""
    if logical_files.empty or discovered_files.empty:
        return DataFrame()
    discovered_by_key: dict[tuple[str, str, str], list[dict]] = {}
    for item in discovered_files.to_dict(orient="records"):
        folder_name = item.get("folder_name") or ""
        key = (
            folder_name.casefold(),
            *_location_key(item["file_name"], item.get("subfolder_name")),
        )
        discovered_by_key.setdefault(key, []).append(item)
    rows = []
    for logical_file in logical_files.to_dict(orient="records"):
        folder_name = logical_file.get("folder_name") or ""
        key = (
            folder_name.casefold(),
            *_location_key(
                logical_file["file_name"], logical_file.get("subfolder_name")
            ),
        )
        matches = discovered_by_key.get(key, [])
        if len(matches) != 1:
            continue
        match = matches[0]
        rows.append({
            "file_id": logical_file["file_id"],
            "repository_name": repository_name,
            "repository_item_id": match["repository_item_id"],
            "is_canonical": is_canonical,
            "created_timestamp": match["created_timestamp"],
        })
    return DataFrame(rows)


def discover_google_drive_migration(
    engine: Engine,
    media_type: str,
    project_year: int,
) -> DataFrame:
    """Build a read-only filename-based Google Drive migration plan."""
    locations = fetch_folder_transfer_locations(
        engine,
        project_year,
        media_type,
        SOURCE_REPOSITORY,
        DESTINATION_REPOSITORY,
    )
    logical_files = fetch_file_location_candidates(engine, project_year, media_type)
    logical_by_folder = {} if logical_files.empty else {
        folder_id: {
            _location_key(row["file_name"], row.get("subfolder_name")): row
            for row in rows.to_dict(orient="records")
        }
        for folder_id, rows in logical_files.groupby("folder_id", dropna=False)
    }
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
            rows.append({**base, "source_file_id": None,
                         "destination_folder_id": destination_folder_id,
                         "file_name": None, "file_size": None,
                         "status": "missing_source_location"})
            continue
        if not isinstance(destination_folder_id, str) or not destination_folder_id:
            rows.append({**base, "source_file_id": None,
                         "destination_folder_id": None,
                         "file_name": None, "file_size": None,
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
        destination_by_name: dict[tuple[str, str], list[dict]] = {}
        for item in destination_files:
            name = item.get("name")
            if isinstance(name, str) and name:
                key = _location_key(name, item.get("relative_parent"))
                destination_by_name.setdefault(key, []).append(item)

        source_name_counts: dict[str, int] = {}
        for item in source_files:
            folded_name = item["name"].casefold()
            source_name_counts[folded_name] = source_name_counts.get(folded_name, 0) + 1

        for source_file in source_files:
            file_name = source_file["name"]
            file_key = _location_key(file_name, source_file.get("relative_parent"))
            logical_file = logical_by_folder.get(folder["folder_id"], {}).get(file_key)
            try:
                size = _file_size(source_file, SOURCE_REPOSITORY)
            except ValueError:
                rows.append({**base, "source_file_id": source_file["id"],
                             "destination_folder_id": destination_folder_id,
                             "file_name": file_name, "file_size": None,
                             "status": "invalid_source_size"})
                continue
            file_row = {
                **base,
                "file_id": logical_file.get("file_id") if logical_file else None,
                "source_file_id": source_file["id"],
                "source_created_timestamp": parse_created_timestamp(
                    source_file.get("createdTime"), SOURCE_REPOSITORY,
                ),
                "destination_folder_id": destination_folder_id,
                "file_name": file_name,
                "file_size": size,
            }
            if source_file.get("capabilities", {}).get("canDownload") is False:
                rows.append({**file_row, "status": "download_not_allowed"})
                continue
            if source_name_counts[file_name.casefold()] > 1:
                rows.append({**file_row, "status": "duplicate_source_name"})
                continue

            destination_matches = destination_by_name.get(file_key, [])
            if destination_matches:
                destination = destination_matches[0]
                rows.append({
                    **file_row,
                    "destination_file_id": destination.get("id"),
                    "destination_created_timestamp": parse_created_timestamp(
                        destination.get("createdDateTime"), DESTINATION_REPOSITORY,
                    ),
                    "status": "already_present",
                })
                continue

            rows.append({**file_row, "status": "candidate"})

    results = DataFrame(rows)
    results.attrs["folder_count"] = len(locations)
    results.attrs["mapped_folder_count"] = sum(
        isinstance(row.get("source_item_id"), str) and bool(row["source_item_id"])
        and isinstance(row.get("destination_item_id"), str)
        and bool(row["destination_item_id"])
        for row in locations.to_dict(orient="records")
    )
    return results
