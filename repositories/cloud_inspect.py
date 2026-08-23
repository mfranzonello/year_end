"""Reconcile OneDrive folder and video metadata without local media dependencies."""

from pathlib import Path
from typing import Protocol

from pandas import DataFrame, concat
from sqlalchemy import Engine

from common.video import VIDEO_EXTS, get_resolution
from database.db_project import (
    fetch_known_files, fetch_project_folders, purge_files, update_files,
    update_folder_locations_and_shares, update_folders,
)
from integrations.microsoft.onedrive.client import (
    GraphRequestError,
    find_folder_id as find_onedrive_folder_id,
    get_or_create_share_link as get_or_create_onedrive_share_link,
    get_share_link as get_onedrive_share_link,
    list_child_folders as list_onedrive_child_folders,
    list_children as list_onedrive_children,
    list_descendant_files as list_onedrive_descendant_files,
)


class UpdateConsole(Protocol):
    """Minimal status surface required by cloud inspection."""

    def add_update(self, message: str) -> None:
        """Emit a durable status message."""


def inspect_onedrive_folder_shares(
    engine: Engine,
    project_root: str,
    media_type: str,
    supfolder_name: str,
    project_year: int,
    ui: UpdateConsole,
    dry_run: bool = True,
    create_missing_shares: bool = True,
) -> DataFrame:
    """Match canonical OneDrive folders to project records and ensure shares."""
    project_folders = fetch_project_folders(engine, project_year, media_type)
    if project_folders.empty:
        return DataFrame()

    year_path = "/".join((project_root.strip("/\\"), supfolder_name, str(project_year)))
    try:
        year_folder_id = find_onedrive_folder_id(year_path)
    except GraphRequestError as error:
        if "HTTP 404" not in str(error):
            raise
        ui.add_update(
            f"OneDrive {project_year} {media_type}: configured year folder does not exist."
        )
        return DataFrame()
    cloud_folders = list_onedrive_child_folders(year_folder_id)
    cloud_by_name = {folder.get("name"): folder for folder in cloud_folders}
    if len(cloud_by_name) != len(cloud_folders):
        raise ValueError("The OneDrive year folder contains duplicate top-level folder names")

    matched = []
    for row in project_folders.to_dict(orient="records"):
        cloud_folder = cloud_by_name.get(row["folder_name"])
        if cloud_folder is None:
            continue
        item_id = cloud_folder.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        share_function = (
            get_or_create_onedrive_share_link
            if create_missing_shares
            else get_onedrive_share_link
        )
        matched.append({
            **row,
            "repository_item_id": item_id,
            "share_url": None if dry_run else share_function(item_id),
        })

    results = DataFrame(matched)
    ui.add_update(
        f"OneDrive {project_year} {media_type}: matched {len(results)} of "
        f"{len(project_folders)} database folders."
    )
    if not dry_run:
        update_folder_locations_and_shares(
            engine, results, "OneDrive", is_canonical=True,
        )
    return results


def _is_video_item(item: dict) -> bool:
    """Return whether a Graph file item has a configured video extension."""
    name = item.get("name")
    return (
        "file" in item
        and isinstance(name, str)
        and Path(name).suffix.lower() in VIDEO_EXTS
    )


def _cloud_file_row(
    item: dict,
    folder_name: str | None,
    project_year: int,
    subfolder_name: str | None,
) -> dict:
    """Convert Graph metadata to the portable project.files input contract."""
    size = item.get("size")
    if not isinstance(size, int) or size < 0:
        raise GraphRequestError(
            f"Microsoft Graph returned an invalid size for {item.get('name')!r}"
        )
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    duration_ms = video.get("duration")
    duration = (
        round(duration_ms / 1000)
        if isinstance(duration_ms, (int, float)) and duration_ms >= 0
        else None
    )
    width = video.get("width")
    height = video.get("height")
    resolution = (
        get_resolution(width, height)
        if isinstance(width, int) and width > 0
        and isinstance(height, int) and height > 0
        else None
    )
    return {
        "folder_name": folder_name,
        "project_year": project_year,
        "file_name": item["name"],
        "subfolder_name": subfolder_name,
        "file_size": round(size / (1024 ** 2), 1),
        "video_duration": duration,
        "video_resolution": resolution,
        "stored": "cloud",
    }


def _get_to_purge(
    known: DataFrame,
    found: DataFrame,
    comparison_columns: list[str],
) -> DataFrame:
    merged = known.merge(found, on=comparison_columns, how="left", indicator=True)
    return merged[merged["_merge"] == "left_only"]


def _find_stale_cloud_files(
    engine: Engine,
    files: DataFrame,
    project_years: list[int],
    media_type: str,
) -> DataFrame:
    """Return database files absent from a successful OneDrive inventory."""
    comparison_columns = [
        "folder_name", "project_year", "media_type", "file_name", "subfolder_name",
    ]
    found_files = files.copy()
    if found_files.empty:
        found_files = DataFrame(columns=comparison_columns)
    else:
        found_files["media_type"] = media_type

    stale_files = []
    for selected_year in project_years:
        known_files = fetch_known_files(engine, selected_year, media_type)
        found_for_year = found_files[
            found_files["project_year"] == selected_year
        ][comparison_columns]
        stale = _get_to_purge(known_files, found_for_year, comparison_columns)
        if not stale.empty:
            stale_files.append(stale)

    return concat(stale_files, ignore_index=True) if stale_files else DataFrame()


def inspect_onedrive_cloud_contents(
    engine: Engine,
    project_root: str,
    media_type: str,
    supfolder_name: str,
    ui: UpdateConsole,
    dry_run: bool = True,
    project_year: int | None = None,
    folders_only: bool = False,
) -> tuple[DataFrame, DataFrame]:
    """Inventory OneDrive folders and file metadata without downloading media."""
    media_path = "/".join((project_root.strip("/\\"), supfolder_name))
    requested_path = f"{media_path}/{project_year}" if project_year is not None else media_path
    try:
        if project_year is not None:
            year_folders = [{
                "id": find_onedrive_folder_id(f"{media_path}/{project_year}"),
                "name": str(project_year),
                "folder": {},
            }]
        else:
            media_folder_id = find_onedrive_folder_id(media_path)
            year_folders = [
                item for item in list_onedrive_child_folders(media_folder_id)
                if isinstance(item.get("name"), str)
                and item["name"].isdigit()
                and len(item["name"]) == 4
            ]
    except GraphRequestError as error:
        if "HTTP 404" not in str(error):
            raise
        ui.add_update(f"OneDrive cloud path does not exist: {requested_path}")
        return DataFrame(), DataFrame()

    folder_rows = []
    file_rows = []
    for year_folder in sorted(year_folders, key=lambda item: item["name"]):
        if not isinstance(year_folder.get("id"), str) or not year_folder["id"]:
            raise GraphRequestError("Microsoft Graph returned a year folder without an ID")
        selected_year = int(year_folder["name"])
        ui.add_update(f"Checking OneDrive cloud metadata for {media_type} {selected_year}")
        children = list_onedrive_children(year_folder["id"])
        participant_folders = [item for item in children if "folder" in item]
        participant_names = [item.get("name") for item in participant_folders]
        if not all(isinstance(name, str) and name for name in participant_names):
            raise GraphRequestError(
                f"Microsoft Graph returned an unnamed folder beneath {selected_year}"
            )
        if not all(
            isinstance(item.get("id"), str) and item["id"]
            for item in participant_folders
        ):
            raise GraphRequestError(
                f"Microsoft Graph returned a folder without an ID beneath {selected_year}"
            )
        if len(set(participant_names)) != len(participant_names):
            raise ValueError(
                f"OneDrive {selected_year} contains duplicate top-level folder names"
            )

        root_files = [item for item in children if _is_video_item(item)]
        if root_files:
            folder_rows.append({
                "folder_name": None,
                "project_year": selected_year,
                "media_type": media_type,
            })
            if not folders_only:
                file_rows.extend(
                    _cloud_file_row(item, None, selected_year, None)
                    for item in root_files
                )

        for participant in sorted(participant_folders, key=lambda item: item["name"]):
            folder_name = participant["name"]
            folder_rows.append({
                "folder_name": folder_name,
                "project_year": selected_year,
                "media_type": media_type,
            })
            if folders_only:
                continue
            file_rows.extend(
                _cloud_file_row(
                    item,
                    folder_name,
                    selected_year,
                    item.get("relative_parent"),
                )
                for item in list_onedrive_descendant_files(participant["id"])
                if _is_video_item(item)
            )

    folders = DataFrame(
        folder_rows,
        columns=["folder_name", "project_year", "media_type"],
    )
    files = DataFrame(
        file_rows,
        columns=[
            "folder_name", "project_year", "file_name", "subfolder_name",
            "file_size", "video_duration", "video_resolution", "stored",
        ],
    )
    ui.add_update(
        f"OneDrive cloud inventory found {len(folders)} project folders and "
        f"{len(files)} video files for {media_type}."
    )
    inventoried_years = [int(item["name"]) for item in year_folders]
    stale_files = (
        DataFrame()
        if folders_only
        else _find_stale_cloud_files(engine, files, inventoried_years, media_type)
    )
    if not folders_only:
        action = "would remove" if dry_run else "removed"
        ui.add_update(
            f"OneDrive cloud reconciliation {action} {len(stale_files)} stale "
            f"database file records for {media_type}."
        )
    if not dry_run:
        if not folders.empty:
            update_folders(engine, folders)
        if not files.empty:
            files["media_type"] = media_type
            update_files(engine, files)
        if not stale_files.empty:
            purge_files(engine, stale_files)
    return folders, files
