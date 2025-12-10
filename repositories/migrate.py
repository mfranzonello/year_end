'''Scan and copy new videos from Google Drive to OneDrive.'''

import sys
from pathlib import Path
import shutil
from itertools import combinations

from pandas import DataFrame
from sqlalchemy import Engine

from common.system import (get_shortcuts_in_folder, resolve_shortcut_target, mount_g_drive, sort_paths,
                            get_videos_in_folder, get_year_folders, get_person_folders, rebuild_path)
from database.db_project import fetch_duplicates

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

def are_dupes(file_1:Path, file_2:Path, byte_threshold=50000) -> Path|None:
    # check that extensions are the same
    if file_1.suffix.lower() == file_2.suffix.lower():

        # check that one stem is contained in the other
        stem_1 = file_1.stem
        stem_2 = file_2.stem

        contains_1 = stem_1 in stem_2
        contains_2 = stem_2 in stem_1
        if contains_1 or contains_2:

            # check that they are roughly the same size
            stat_1 = file_1.stat()
            stat_2 = file_2.stat()
            if abs(stat_1.st_size - stat_2.st_size) <= byte_threshold:

                # check which has the longer name
                len_1 = len(file_1.name)
                len_2 = len(file_2.name)

                if len_1 > len_2:
                    return file_1
                elif len_2 > len_1:
                    return file_2

                else:
                    # check which is in a deeper subfolder
                    depth_1 = len(file_1.parts)
                    depth_2 = len(file_2.parts)
                    if depth_1 > depth_2:
                        return file_1
                    elif depth_2 > depth_1:
                        return file_2

                    else:
                        # check which ws modified later
                        return file_1 if stat_1.st_mtime > stat_2.st_mtime else file_2

def quarantine_file(file:Path, quarantine_root:Path) -> Path:
    # recreate the folder structure under quarantine
    rel_path = file.relative_to(file.parents[2])   # adjust depending on structure

    target = quarantine_root / rel_path
    
    # ensure target directory exists
    target.parent.mkdir(parents=True, exist_ok=True)

    # check that source exists and target does not:
    if not file.exists():
        if target.exists():
            print(f'File {file} already in quarantine.')
        else:
            print(f'File {file} is missing.')
    else:
        if target.exists():
            print(f'Cannot move file {file} as it is already in quarantine.')
        else:
            # atomic move (fast, keeps metadata)
            file.rename(target)

    return target

def quarantine_file_2(file:Path, incoming_path:Path, quarantine_root:Path) -> Path:
    # recreate the folder structure under quarantine
    rel_path = file.relative_to(incoming_path)   # adjust depending on structure

    target = quarantine_root / rel_path
    
    # ensure target directory exists
    target.parent.mkdir(parents=True, exist_ok=True)

    # check that source exists and target does not:
    if not file.exists():
        if target.exists():
            print(f'File {file} already in quarantine.')
        else:
            print(f'File {file} is missing.')
    else:
        if target.exists():
            print(f'Cannot move file {file} as it is already in quarantine.')
        else:
            # atomic move (fast, keeps metadata)
            shutil.move(file, target)
            #file.rename(target)

    return target

def dedupe_folder_from_incoming(files_in_folder:list[Path], quarantine_root:Path, dry_run:bool) -> list[Path]|None:
    # identify candidates for removal in GDrive

    file_pairings = combinations(files_in_folder, 2)
    potential_dupes = []
    for f1, f2 in file_pairings:
        dupe = are_dupes(f1, f2)
        if dupe:
            potential_dupes.append(dupe)

    if not dry_run:
        # move dupes to a quarantine folder
        for dupe in potential_dupes:
            quarantine_file(dupe, quarantine_root)
            return potential_dupes

def dedupe_folder_from_db(duplicates_df:DataFrame, one_drive_folder:Path, quarantine_folder:Path,
                          dry_run:bool) -> tuple[list[Path], list[list[Path]]]:
    # identify candidates from removal in OneDrive
    keep_paths = []
    move_paths = []
    for _, row in duplicates_df.iterrows():
        potential_duplicates = row['duplicates_sorted']
        project_year = str(row['project_year'])
        parent_folder = one_drive_folder / project_year
        folder_name = row['folder_name']

        file_paths = [rebuild_path(parent_folder, folder_name, d['subfolder_name'], d['file_name']) for d in potential_duplicates]
        keep_paths.append(file_paths[0])
        dupe_paths = file_paths[1:]
        move_paths.append(dupe_paths)
        
        if not dry_run:
            for d in dupe_paths:
                quarantine_file_2(d, one_drive_folder, quarantine_folder)

    return keep_paths, move_paths

def dedupe_one_drive(engine:Engine, one_drive_folder:Path, media_type:str,
                     quarantine_folder:Path, dry_run:bool):
    # dedupe from before
    print('Deduping previous imports...')
    dupes_df = fetch_duplicates(engine, media_type)
    keep_paths, move_paths = dedupe_folder_from_db(dupes_df, one_drive_folder, quarantine_folder, dry_run=dry_run)
    for k, m in zip(keep_paths, move_paths):
        print(f'Kept {k}, moved {m}.')

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