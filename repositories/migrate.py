"""Copy media from mounted or browser-based sources into OneDrive."""

import sys
from pathlib import Path
import shutil

from sqlalchemy import Engine

from common.system import (get_shortcuts_in_folder, resolve_shortcut_target, mount_g_drive, sort_paths,
                            get_videos_in_folder, get_year_folders, get_person_folders)
from database.db_project import fetch_shared_albums
from repositories.cleanup import dedupe_folder_from_incoming
from scraping.photos import harvest_shared_album, source_allowed

def gather_names_casefold(folder: Path) -> set[str]:
    """Set of existing filenames (casefolded) in a folder (non-recursive)."""
    names = set()
    if folder.exists():
        for p in folder.iterdir():
            if p.is_file():
                names.add(p.name.casefold())
    return names

def copy_if_needed(source_file: Path, destination_folder:Path, existing_videos: list[Path], dry_run: bool) -> bool:
    """
    Copy file if a case-insensitive filename does not already exist in dst_folder.
    Returns True if a copy will/does happen, False otherwise.
    """
    if source_file.name.casefold() in existing_videos:
        return False
    if dry_run:
        return True

    destination_folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, destination_folder / source_file.name)
    return True

def download_shared_albums(
    engine: Engine,
    one_drive_folder: Path,
    google: bool = True,
    icloud: bool = True,
    headless: bool = False,
    dry_run: bool = True,
) -> None:
    """Download configured browser-based shared albums into OneDrive."""
    albums = fetch_shared_albums(engine)
    for _, (_, url, folder_name, project_year, supfolder_name,
            scrape_name, browser_name, profile_name, notes) in albums.iterrows():
        if notes:
            print(f'Skipping album: {notes}')
            continue

        share_source = scrape_name.lower()
        browser_profile = f'{profile_name} {scrape_name}'
        download_directory = (
            one_drive_folder / supfolder_name / str(project_year) / folder_name
        )
        if source_allowed(share_source, google=google, icloud=icloud):
            harvest_shared_album(
                url,
                download_directory,
                scrape_name,
                browser_name,
                browser_profile,
                headless=headless,
                dry_run=dry_run,
            )

def copy_from_gdrive(one_drive_folder:Path, google_drive_folder:Path,
                     quarantine_folder:Path, quarantine:str, ui, dry_run:bool):
    ''' look at Google Drive folders and copy in new items '''
    mount_g_drive()

    google_drive_years = get_year_folders(google_drive_folder)

    for g_year in google_drive_years:
        o_year = one_drive_folder / g_year.name
        q_year = quarantine_folder / g_year.name
        if not o_year.exists():
            ui.add_update(f"WARNING: OneDrive year folder missing (will be created on demand): {g_year.name}", file=sys.stderr)

        # --- Copy new videos from GDrive to OneDrive, per person folder ---
        copy_report: list[tuple[str, int]] = []
        g_people = get_person_folders(g_year)

        ui.set_status('Checking for new videos to copy...')
        for g_person in sort_paths(g_people):
            person_name = g_person.name  # e.g., "Michael 2025"
            o_person = o_year / person_name
            q_person = q_year / person_name

            # check if there are shortcuts in the top level
            shortcut_folders = get_shortcuts_in_folder(g_person) # recursive=True if more than top level
            checkable_folders = [g_person] + [resolve_shortcut_target(s) for s in shortcut_folders if s]

            for folder in checkable_folders:
                # see what's in the folder before quarantine
                video_files = get_videos_in_folder(folder, recursive=True)
        
                # dedupe the source folder
                dupes = dedupe_folder_from_incoming(video_files, google_drive_folder / quarantine, dry_run)

                # List candidate videos in the Google Drive person folder (non-recursive).
                candidate_files = [v for v in video_files if v not in dupes] if dupes else video_files
            
                destination_files = get_videos_in_folder(o_person, recursive=True)
                quarantined_files = get_videos_in_folder(q_person, recursive=True) if q_person.exists() else []
                existing_videos = [f.name.casefold() for f in set(destination_files + quarantined_files)]
            
                copied_count = 0
                for video_file in candidate_files:
                    if copy_if_needed(video_file, o_person, existing_videos, dry_run=dry_run):
                        copied_count += 1

                copy_report.append((person_name, copied_count))

        # Also include note for any GDrive person folders that do not exist in OneDrive yet (only relevant when dry-run)
        missing_targets = []
        for g_person in g_people:
            if not (o_year / g_person.name).exists():
                missing_targets.append(g_person.name)

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
