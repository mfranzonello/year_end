'''Main script to scan for new video files, copy them, summarize ratings, and update Premiere project.'''

import argparse

from pandas import DataFrame

from common.structure import ONE_DRIVE_FOLDER, GOOGLE_DRIVE_FOLDER, ADOBE_FOLDER, YIR_REVIEWS, QUARANTINE_FOLDER, QUARANTINE
from common.secret import secrets
from common.console import SplitConsole
from common.config import read_toml
from database.db import get_engine
from repositories.iterate import get_media_locations
from repositories.migrate import dedupe_one_drive, copy_from_gdrive
from repositories.ingest import copy_from_web, ingest_google_drive_folder_shares
from repositories.inspect import (
    inspect_onedrive_folder_shares, purge_stale_content, summarize_folders,
    update_database_images,
)

PGSECRETS = secrets['postgresql']['host']
PGHOST = secrets['postgresql']['host']
PGPORT = secrets['postgresql']['port']
PGDBNAME = secrets['postgresql']['database']
PGUSER = secrets['postgresql']['user']
PGPASSWORD = secrets['postgresql']['password']

CLOUDINARY_CLOUD = secrets['cloudinary']['cloud_name']
CLOUDINARY_API_KEY = secrets['cloudinary']['api_key']
CLOUDINARY_API_SECRET = secrets['cloudinary']['api_secret']

MIN_STARS = 3

ui = SplitConsole()
DRIVE_CONFIG = read_toml("drives")["local_storage"]

def set_up_engine():
    return get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

def scan_folders(media_locations:list[tuple], dry_run:bool=True):
    if GOOGLE_DRIVE_FOLDER is None:
        ui.add_update('Google Drive is not mounted; skipping Google Drive copy inspection.')
        return

    engine = set_up_engine()

    for media_type, supfolder_name in media_locations:
        if (GOOGLE_DRIVE_FOLDER / supfolder_name).exists():
            missing_targets = copy_from_gdrive(ONE_DRIVE_FOLDER / supfolder_name, GOOGLE_DRIVE_FOLDER / supfolder_name,
                                               QUARANTINE_FOLDER, QUARANTINE, ui, dry_run)

            if dry_run and missing_targets:
                ui.add_update("\n(Note) These OneDrive destination folders do not exist yet (will be created on --apply if needed):")
                for name in missing_targets:
                    ui.add_update(f"  - {name}")

    engine.dispose()

def dedupe_folders(media_locations:list[tuple], dry_run:bool=True):
    engine = set_up_engine()
    for media_type, supfolder_name in media_locations:
        dedupe_one_drive(engine, ONE_DRIVE_FOLDER / supfolder_name, media_type,
                         QUARANTINE_FOLDER / supfolder_name / QUARANTINE, dry_run)
    engine.dispose()

def harvest_albums(google:bool, icloud:bool, headless:bool=True):
    engine = set_up_engine()
    copy_from_web(engine, ONE_DRIVE_FOLDER, google=google, icloud=icloud, headless=headless)
    engine.dispose()

def purge_database(media_locations:list[tuple], dry_run:bool=True):
    engine = set_up_engine()
    for media_type, supfolder_name in media_locations:
        purge_stale_content(engine, ONE_DRIVE_FOLDER / supfolder_name, media_type, dry_run)
    engine.dispose()

def update_database(
    media_locations: list[tuple],
    dry_run: bool = True,
    project_year: int | None = None,
    folders_only: bool = False,
):
    """Inspect configured media locations and update their database records."""
    engine = set_up_engine()

    for media_type, supfolder_name in media_locations:
        summarize_folders(
            engine,
            ONE_DRIVE_FOLDER / supfolder_name,
            media_type,
            ADOBE_FOLDER,
            YIR_REVIEWS,
            ui,
            dry_run=dry_run,
            project_year=project_year,
            folders_only=folders_only,
        )
    engine.dispose()

def sync_cloud_folder_shares(
    media_locations: list[tuple],
    project_year: int,
    onedrive: bool,
    google_drive: bool,
    dry_run: bool = True,
):
    """Discover cloud folder IDs and optionally persist ensured share links."""
    engine = set_up_engine()
    try:
        for media_type, supfolder_name in media_locations:
            if onedrive:
                inspect_onedrive_folder_shares(
                    engine,
                    DRIVE_CONFIG["onedrive"]["videos"],
                    media_type,
                    supfolder_name,
                    project_year,
                    ui,
                    dry_run=dry_run,
                )
            if google_drive:
                results = ingest_google_drive_folder_shares(
                    engine,
                    DRIVE_CONFIG["google_drive"]["videos"],
                    media_type,
                    supfolder_name,
                    project_year,
                    dry_run=dry_run,
                )
                expected_count = results.attrs.get("expected_count", 0)
                if expected_count:
                    ui.add_update(
                        f"Google Drive {project_year} {media_type}: matched "
                        f"{len(results)} of {expected_count} database folders."
                    )
    finally:
        engine.dispose()

def update_images(dry_run:bool=True):
    engine = set_up_engine()
    update_database_images(engine, CLOUDINARY_CLOUD, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, dry_run=dry_run)
    engine.dispose()

def main():
    ap = argparse.ArgumentParser(description=f"Scan for new files and import into current year's Premiere review project.")
    
    # run Selenium w/ or w/o head
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--headless", dest="headless", action="store_true",
                       help="Run Selenium in background")
    group.add_argument("--no-headless", dest="headless", action="store_false",
                       help="Run Selenium with UI visible")
    ap.set_defaults(headless=True)

    ap.add_argument('--no-dbupdate', nargs='?', type=bool, const=True, default=False, help="Don't update the database.")

    ap.add_argument('--gphotos', nargs='?', type=bool, const=True, default=False, help='Copy new files from Google Photos to OneDrive.')
    ap.add_argument('--iphotos', nargs='?', type=bool, const=True, default=False, help='Copy new files from iCloud Photos to OneDrive.')
    ap.add_argument('--gdrive', nargs='?', type=bool, const=True, default=False, help='Copy new files from Google Drive to OneDrive.')
    ap.add_argument('--pictures', nargs='?', type=bool, const=True, default=False, help='Update Premiere project with bins and imports.')
    ap.add_argument('--inspect-only', action='store_true', help='Only discover top-level participant folders and update their database records.')
    ap.add_argument('--onedrive-shares', action='store_true', help='Discover OneDrive folder IDs and ensure share links with --apply.')
    ap.add_argument('--google-drive-shares', action='store_true', help='Discover Google Drive folder IDs and ensure share links with --apply.')
    ap.add_argument('--year', type=int, help='Limit folder inspection or cloud sharing to one project year.')

    ap.add_argument('--stars', type=int, default=MIN_STARS, help='Minimum star rating to use in project.')

    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Apply requested file, share-link, and database changes.")
    group.add_argument("--dry-run", action="store_true", help="Inspect without changing files, cloud permissions, or the database.")
    
    args = ap.parse_args()
    cloud_shares = args.onedrive_shares or args.google_drive_shares
    if args.year and not (args.inspect_only or cloud_shares):
        ap.error('--year requires --inspect-only or a cloud-share option.')
    if cloud_shares and args.year is None:
        ap.error('--onedrive-shares and --google-drive-shares require --year.')
    if cloud_shares and args.no_dbupdate:
        ap.error('Cloud-share reconciliation cannot be combined with --no-dbupdate.')
    if args.inspect_only and args.no_dbupdate:
        ap.error('--inspect-only cannot be combined with --no-dbupdate.')
    dry_run = not args.apply  # default to dry-run unless --apply

    ui.add_update(f'Running with args: {args}')

    engine = set_up_engine()
    media_locations = get_media_locations(engine)
    engine.dispose()

    if args.gphotos or args.iphotos:
        harvest_albums(args.gphotos, args.iphotos, args.headless)
   
    if args.gdrive:
        scan_folders(media_locations, dry_run=dry_run)

    if args.inspect_only:
        update_database(media_locations, dry_run=dry_run, project_year=args.year, folders_only=True)
    elif not args.no_dbupdate and not cloud_shares:
        purge_database(media_locations, dry_run=dry_run)
        update_database(media_locations, dry_run=dry_run)
        dedupe_folders(media_locations, dry_run=dry_run)
        purge_database(media_locations, dry_run=dry_run)

    if cloud_shares:
        sync_cloud_folder_shares(
            media_locations,
            args.year,
            args.onedrive_shares,
            args.google_drive_shares,
            dry_run=dry_run,
        )

    if args.pictures:
        update_images(dry_run=dry_run)

    ui.set_status("Done.")

if __name__ == "__main__":
    main()
