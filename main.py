'''Main script to scan for new video files, copy them, summarize ratings, and update Premiere project.'''

from pathlib import Path
import argparse
import sys
from datetime import datetime

from common.structure import ONE_DRIVE_FOLDER, GOOGLE_DRIVE_FOLDER, ADOBE_FOLDER, QUARANTINE
from common.structure import YIR_REVIEWS, YIR_PROJECT, PR_EXT ## needed for pymiere control
from common.secret import secrets
from common.console import SplitConsole
from common.system import get_person_names
from database.db import get_engine
from repositories.migrate import copy_from_gdrive
from repositories.ingest import copy_from_web
from repositories.inspect import get_usable_videos, summarize_folders, update_database_images
from adobe.premiere import open_project, find_videos_bin, create_person_bins, import_videos, set_family_color_labels

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

def scan_folders(one_drive_folder, google_drive_folder, dry_run=True):
    missing_targets = copy_from_gdrive(one_drive_folder, google_drive_folder, QUARANTINE, ui, dry_run)

    if dry_run and missing_targets:
        ui.add_update("\n(Note) These OneDrive destination folders do not exist yet (will be created on --apply if needed):")
        for name in missing_targets:
            ui.add_update(f"  - {name}")

def harvest_albums(year, google, icloud, headless=True):
    engine = set_up_engine()
    copy_from_web(engine, ONE_DRIVE_FOLDER, year, google=google, icloud=icloud, headless=headless)

def update_database(dry_run=True):
    engine = set_up_engine()
    summarize_folders(engine, ONE_DRIVE_FOLDER, QUARANTINE, ADOBE_FOLDER,
                      ui, dry_run=dry_run)
    engine.dispose()

def update_images(dry_run=True):
    engine = set_up_engine()
    update_database_images(engine, dry_run, CLOUDINARY_CLOUD, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)
    engine.dispose()

def update_project(year:int, min_stars:int, dry_run=True):
    engine = set_up_engine()

    ui.set_status('Opening Premiere project...')
    project_id = open_project(Path(ADOBE_FOLDER) / f'{YIR_REVIEWS} {year}' / f'{YIR_PROJECT} {year}{PR_EXT}')

    ui.set_status('Finding Videos bin')
    videos_bin = find_videos_bin(project_id)

    ui.set_status('Creating person bins...')
    od_videos = Path(ONE_DRIVE_FOLDER) / f'{year}'
    person_names = get_person_names(od_videos)
    create_person_bins(videos_bin, person_names)

    ui.set_status(f'Importing reviewed videos ({min_stars} star and above)...')
    for person_name in person_names:
        ui.set_status(f'\tLooking at {person_name}...')

        # pull from DB
        usable_videos = get_usable_videos(engine, year, min_stars)

        if not usable_videos.empty:
            num_videos = len(usable_videos)
            v_s = 's' if num_videos != 1 else ''
            ui.set_status(f'\t\tChecking {len(usable_videos)} video{v_s} for {person_name}...')
            import_videos(project_id, videos_bin, person_name, usable_videos) ## need to convert to paths

    ui.set_status('Setting labels...')
    set_family_color_labels(videos_bin)

    engine.dispose()

def main():
    ap = argparse.ArgumentParser(description=f"Scan for new files and import into current year's Premiere review project.")
    
    ap.add_argument("--od", type=Path, default=Path(ONE_DRIVE_FOLDER), help=f"OneDrive Videos root (default: {ONE_DRIVE_FOLDER})")
    ap.add_argument("--gd", type=Path, default=Path(GOOGLE_DRIVE_FOLDER), help=f"Google Drive Videos root (default: {GOOGLE_DRIVE_FOLDER})")
    
    YEAR = datetime.now().year
    ap.add_argument("--year", type=int, nargs='+', default=[YEAR], help=f"Year(s) subfolder to process (default: {YEAR})")

    # run Selenium w/ or w/o head
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--headless", dest="headless", action="store_true",
                       help="Run Selenium in background")
    group.add_argument("--no-headless", dest="headless", action="store_false",
                       help="Run Selenium with UI visible")
    ap.set_defaults(headless=True)

    ap.add_argument('--nodbupdate', nargs='?', type=bool, const=True, default=False, help="Don't update the database.")

    ap.add_argument('--gphotos', nargs='?', type=bool, const=True, default=False, help='Copy new files from Google Photos to OneDrive.')
    ap.add_argument('--iphotos', nargs='?', type=bool, const=True, default=False, help='Copy new files from iCloud Photos to OneDrive.')
    ap.add_argument('--gdrive', nargs='?', type=bool, const=True, default=False, help='Copy new files from Google Drive to OneDrive.')
    ap.add_argument('--premiere', nargs='?', type=bool, const=True, default=False, help='Update Premiere project with bins and imports.')
    ap.add_argument('--pictures', nargs='?', type=bool, const=True, default=False, help='Update Premiere project with bins and imports.')

    ap.add_argument('--stars', type=int, default=MIN_STARS, help='Minimum star rating to use in project.')

    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Actually copy files.")
    group.add_argument("--dry-run", action="store_true", help="Do not copy or download; show what would happen.")
    
    args = ap.parse_args()
    dry_run = not args.apply  # default to dry-run unless --apply

    ui.add_update(f'Running with args: {args}')

    for year in args.year:
        if args.gphotos or args.iphotos:
            harvest_albums(year, args.gphotos, args.iphotos, args.headless)

        if args.gdrive:
            scan_folders(args.od, args.gd, dry_run)

    ## can look at whole group at once
    if not args.nodbupdate:
        update_database(dry_run=dry_run)

        if args.pictures:
            update_images(dry_run=dry_run)

    for year in args.year:
        if args.premiere:
            if sys.version_info >= (3, 12):
                print('WARNING! Pymiere was built for older versions of Python and may not work properly.')
            update_project(year, args.stars, dry_run=dry_run)

    ui.set_status("Done.")

if __name__ == "__main__":
    main()