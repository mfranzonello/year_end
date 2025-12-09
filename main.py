'''Main script to scan for new video files, copy them, summarize ratings, and update Premiere project.'''

import argparse

from common.structure import ONE_DRIVE_FOLDER, GOOGLE_DRIVE_FOLDER, ADOBE_FOLDER, YIR_REVIEWS, QUARANTINE
from common.secret import secrets
from common.console import SplitConsole
from database.db import get_engine
from repositories.migrate import dedupe_one_drive, copy_from_gdrive
from repositories.ingest import copy_from_web
from repositories.inspect import get_media_locations, summarize_folders, update_database_images, purge_stale_content

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

def set_up_engine():
    return get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

def set_up_media_locations():
    engine = set_up_engine()
    media_locations = get_media_locations(engine)[['media_type', 'supfolder_name']].values
    engine.dispose()
    return media_locations

def scan_folders(media_locations:list[list[str]], dry_run=True):
    engine = set_up_engine()

    for media_type, supfolder_name in media_locations:
        if (GOOGLE_DRIVE_FOLDER / supfolder_name).exists():
            missing_targets = copy_from_gdrive(ONE_DRIVE_FOLDER / supfolder_name, GOOGLE_DRIVE_FOLDER / supfolder_name, QUARANTINE, ui, dry_run)

            if dry_run and missing_targets:
                ui.add_update("\n(Note) These OneDrive destination folders do not exist yet (will be created on --apply if needed):")
                for name in missing_targets:
                    ui.add_update(f"  - {name}")

    engine.dispose()

def dedupe_folders(dry_run=True):
    engine = set_up_engine()
    if not dry_run:
        dedupe_one_drive(engine, ONE_DRIVE_FOLDER, QUARANTINE, dry_run)
    engine.dispose()

def harvest_albums(google, icloud, headless=True):
    engine = set_up_engine()
    copy_from_web(engine, ONE_DRIVE_FOLDER, google=google, icloud=icloud, headless=headless)
    engine.dispose()

def purge_database(media_locations:list[list[str]], dry_run=True):
    if not dry_run:
        engine = set_up_engine()
        for media_type, supfolder_name in media_locations:
            purge_stale_content(engine, ONE_DRIVE_FOLDER / supfolder_name, media_type, dry_run)
        engine.dispose()

def update_database(media_locations, dry_run=True):
    engine = set_up_engine()

    for media_type, supfolder_name in media_locations:
        summarize_folders(engine, ONE_DRIVE_FOLDER / supfolder_name, media_type, ADOBE_FOLDER, YIR_REVIEWS, ui, dry_run=dry_run)
    engine.dispose()

def update_images(dry_run=True):
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

    ap.add_argument('--stars', type=int, default=MIN_STARS, help='Minimum star rating to use in project.')

    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Actually copy files.")
    group.add_argument("--dry-run", action="store_true", help="Do not copy or download; show what would happen.")
    
    args = ap.parse_args()
    dry_run = not args.apply  # default to dry-run unless --apply

    ui.add_update(f'Running with args: {args}')

    media_locations = set_up_media_locations()

    if args.gphotos or args.iphotos:
        harvest_albums(args.gphotos, args.iphotos, args.headless)
   
    if args.gdrive:
        scan_folders(media_locations, dry_run=dry_run)

    if not args.no_dbupdate:
        purge_database(media_locations, dry_run=dry_run)
        update_database(media_locations, dry_run=dry_run)
        ##dedupe_folders(dry_run=dry_run)
        purge_database(media_locations, dry_run=dry_run)

    if args.pictures:
        update_images(dry_run=dry_run)

    ui.set_status("Done.")

if __name__ == "__main__":
    main()