'''Main script to scan for new video files, copy them, summarize ratings, and update Premiere project.'''

from pathlib import Path
import argparse
import sys
from datetime import datetime

from common.structure import ONE_DRIVE_FOLDER, GOOGLE_DRIVE_FOLDER, ADOBE_FOLDER, YIR_CLIPS, YIR_REVIEWS, YIR_PROJECT, PR_EXT, SHARED_ALBUMS
from common.secret import get_secret
from common.system import clear_screen, file_type, get_person_name, get_videos_in_folder, mount_g_drive
from common.console import SplitConsole
from family_tree.db import get_engine
from adobe.bridge import get_rated_videos
from migrate.scan_and_copy import get_person_folders, get_person_names, copy_if_needed
from migrate.summarize import summarize_folders, update_cloud_images
from adobe.premiere import open_project, find_videos_bin, create_person_bins, import_videos, set_family_color_labels
from scraping.photos import get_share_source, source_allowed, harvest_shared_album

PGHOST = get_secret('PGHOST')
PGPORT = get_secret('PGPORT', '5432')
PGDBNAME = get_secret('PGDATABASE')
PGUSER = get_secret('PGUSER')
PGPASSWORD = get_secret('PGPASSWORD')

CLOUDINARY_CLOUD = get_secret('CLOUDINARY_CLOUD')
CLOUDINARY_API_KEY = get_secret('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = get_secret('CLOUDINARY_API_SECRET')

MIN_STARS = 3

ui = SplitConsole()

def scan_folders(od, gd, yir_clips, year, dry_run=True):
    od_year = od / yir_clips / str(year)
    gd_year = gd / yir_clips / str(year)
    
    mount_g_drive()
    if not gd_year.exists():
        ui.add_update(f"WARNING: Google Drive year folder missing: {gd_year}", file=sys.stderr)
    if not od_year.exists():
        ui.add_update(f"WARNING: OneDrive year folder missing (will be created on demand): {od_year}", file=sys.stderr)

    # --- Copy new videos from GDrive to OneDrive, per person folder ---
    copy_report: list[tuple[str, int]] = []
    gd_people = get_person_folders(gd_year)

    ui.set_status('Checking for new videos to copy...')
    for gd_person in sorted(gd_people, key=lambda p: p.name.lower()):
        person_name = gd_person.name  # e.g., "Michael 2025"
        od_person = od_year / person_name

        # List candidate videos in the Google Drive person folder (non-recursive).
        candidates = [p for p in gd_person.iterdir() if file_type(p) == 'VIDEO']
        copied_count = 0
        for src in candidates:
            if copy_if_needed(src, od_person, dry_run=dry_run):
                copied_count += 1

        copy_report.append((person_name, copied_count))

    # Also include note for any GDrive person folders that do not exist in OneDrive yet (only relevant when dry-run)
    missing_targets = []
    for gd_person in gd_people:
        if not (od_year / gd_person.name).exists():
            missing_targets.append(gd_person.name)

    # --- Output ---
    ui.add_update("\n=== Copy Summary (Google Drive -> OneDrive) ===")
    if all(c == 0 for _, c in copy_report):
        ui.add_update("No new videos detected.")
    else:
        for name, count in copy_report:
            if count > 0:
                v_s = 's' if count != 1 else ''
                ui.add_update(f"{count} video{v_s} copied from {name}")
        # For zero-copy entries, we keep it quiet to reduce noise.

    if dry_run and missing_targets:
        ui.add_update("\n(Note) These OneDrive destination folders do not exist yet (will be created on --apply if needed):")
        for name in missing_targets:
            ui.add_update(f"  - {name}")

def harvest_albums(albums, year, google, icloud, headless=True):
    for album in albums:
        shared_album_url = album['url']
        person_name = album['person']
        year = album['year']
        profile_name = album['profile']
        share_source = get_share_source(shared_album_url)

        if year == year and source_allowed(share_source, google=google, icloud=icloud):
            harvest_shared_album(shared_album_url, person_name, profile_name, year=year, headless=headless)

def update_database(year, min_stars, dry_run=True):
    engine = get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)
    summarize_folders(engine, year, min_stars, dry_run=dry_run)

def update_project(year, min_stars, dry_run=True):
    ui.set_status('Opening Premiere project...')
    project_id = open_project(Path(ADOBE_FOLDER) / f'{YIR_REVIEWS} {year}' / f'{YIR_PROJECT} {year}{PR_EXT}')

    ui.set_status('Finding Videos bin')
    videos_bin = find_videos_bin(project_id)

    ui.set_status('Creating person bins...')
    od_videos = Path(ONE_DRIVE_FOLDER) / YIR_CLIPS / f'{year}'
    person_names = get_person_names(od_videos)
    create_person_bins(videos_bin, person_names)

    ui.set_status(f'Importing reviewed videos ({min_stars} star and above)...')
    for person_name in person_names:
        ui.set_status(f'\tLooking at {person_name}...')
        videos = get_videos_in_folder(Path(ONE_DRIVE_FOLDER) / YIR_CLIPS / f'{year}' / f'{person_name} {year}') ## FIX FOR TALENT SHOW
        rated_videos, _ = get_rated_videos(videos, min_stars)

        if rated_videos:
            num_videos = len(rated_videos)
            v_s = 's' if num_videos != 1 else ''
            ui.set_status(f'\t\tChecking {len(rated_videos)} video{v_s} for {person_name}...')
            import_videos(project_id, videos_bin, person_name, rated_videos)

    ui.set_status('Setting labels...')
    set_family_color_labels(videos_bin)

def main():
    ap = argparse.ArgumentParser(description=f"Scan for new files and import into current year's Premiere review project.")
    
    ap.add_argument("--od", type=Path, default=Path(ONE_DRIVE_FOLDER), help=f"OneDrive Videos root (default: {ONE_DRIVE_FOLDER})")
    ap.add_argument("--gd", type=Path, default=Path(GOOGLE_DRIVE_FOLDER), help=f"Google Drive Videos root (default: {ONE_DRIVE_FOLDER})")
    
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

    ap.add_argument('--google', nargs='?', type=bool, const=True, default=False, help='Copy new files from Google Photos to OneDrive.')
    ap.add_argument('--icloud', nargs='?', type=bool, const=True, default=False, help='Copy new files from iCloud Photos to OneDrive.')
    ap.add_argument('--gdrive', nargs='?', type=bool, const=True, default=False, help='Copy new files from Google Drive to OneDrive.')
    ap.add_argument('--premiere', nargs='?', type=bool, const=True, default=False, help='Update Premiere project with bins and imports.')

    ap.add_argument('--stars', type=int, default=MIN_STARS, help='Minimum star rating to use in project.')

    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Actually copy files.")
    group.add_argument("--dry-run", action="store_true", help="Do not copy or download; show what would happen.")
    
    args = ap.parse_args()
    dry_run = not args.apply  # default to dry-run unless --apply

    # clean the slate
    clear_screen()

    ui.add_update(f'Running with args: {args}')

    for year in args.year:
        if args.google or args.icloud:
            harvest_albums(SHARED_ALBUMS, year, args.google, args.icloud, args.headless)

        if args.gdrive:
            scan_folders(args.od, args.gd, YIR_CLIPS, year, dry_run)

        if not args.nodbupdate:
            update_database(year, args.stars, dry_run=dry_run)

        if args.premiere:
            update_project(year, args.stars, dry_run=dry_run)

    ui.set_status("Done.")

if __name__ == "__main__":
    main()