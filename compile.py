'''Main script to scan for new video files, copy them, summarize ratings, and update Premiere project.'''

from pathlib import Path
import argparse
import sys
from datetime import datetime

from common.structure import ONE_DRIVE_FOLDER, ADOBE_FOLDER
from common.structure import YIR_REVIEWS, PR_EXT, COMMON_FOLDER, LABEL_PRESET ## needed for pymiere control
from common.secret import secrets
from common.console import SplitConsole
from database.db import get_engine
from repositories.assemble import ensure_premiere, import_and_label, setup_label_presets, get_actors_and_chapters

PGSECRETS = secrets['postgresql']['host']
PGHOST = secrets['postgresql']['host']
PGPORT = secrets['postgresql']['port']
PGDBNAME = secrets['postgresql']['database']
PGUSER = secrets['postgresql']['user']
PGPASSWORD = secrets['postgresql']['password']

MIN_STARS = 3

ui = SplitConsole()

def set_up_engine():
    return get_engine(PGHOST, PGPORT, PGDBNAME, PGUSER, PGPASSWORD)

def update_project(year:int, pull:bool, label:bool, appear:bool, min_stars:int, dry_run=True):
    engine = set_up_engine()
    
    project_id = ensure_premiere(engine, year, ADOBE_FOLDER, YIR_REVIEWS, PR_EXT, ui)
    if project_id >= 0:
        if pull:
            import_and_label(engine, project_id, year, min_stars, ONE_DRIVE_FOLDER, ui, dry_run=dry_run)
        if label:
            setup_label_presets(engine, COMMON_FOLDER, LABEL_PRESET)
        if appear:
            get_actors_and_chapters(engine, project_id, year)

    engine.dispose()

def main():
    ap = argparse.ArgumentParser(description=f"Scan for new files and import into current year's Premiere review project.")
    
    YEAR = datetime.now().year
    ap.add_argument("--year", type=int, default=YEAR, help=f"Project year to process (default: {YEAR})")

    # run Selenium w/ or w/o head
    group = ap.add_mutually_exclusive_group()

    ap.add_argument('--pull', nargs='?', type=bool, const=True, default=False, help='Import rated videos.')
    ap.add_argument('--stars', type=int, default=MIN_STARS, help='Minimum star rating to use in project.')
    ap.add_argument('--appear', nargs='?', type=bool, const=True, default=False, help='Update the appearances table.')
    ap.add_argument('--label', nargs='?', type=bool, const=True, default=False, help='Update the appearances table.')

    group = ap.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Actually copy files.")
    group.add_argument("--dry-run", action="store_true", help="Do not copy or download; show what would happen.")
    
    args = ap.parse_args()
    dry_run = not args.apply  # default to dry-run unless --apply

    ui.add_update(f'Running with args: {args}')

    if sys.version_info >= (3, 12):
        print('WARNING! Pymiere was built for older versions of Python and may not work properly.')
    update_project(args.year, args.pull, args.label, args.appear, args.stars, dry_run=dry_run)

    ui.set_status("Done.")

if __name__ == "__main__":
    main()