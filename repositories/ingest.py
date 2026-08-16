"""Ingest media and repository metadata from source providers."""

from pandas import DataFrame
from sqlalchemy import Engine

from database.db_project import fetch_shared_albums
from database.db_project import fetch_project_folders, update_folder_locations_and_shares
from integrations.google.google_drive.client import (
    GoogleDriveRequestError,
    find_folder_id as find_google_drive_folder_id,
    get_share_link as get_google_drive_share_link,
    get_or_create_share_link as get_or_create_google_drive_share_link,
    list_child_folders as list_google_drive_child_folders,
)
from scraping.photos import source_allowed, harvest_shared_album


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
