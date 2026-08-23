"""Identify duplicate local media and quarantine reviewed redundant files."""

from itertools import combinations
from pathlib import Path
import shutil

from pandas import DataFrame
from sqlalchemy import Engine

from common.system import rebuild_path
from database.db_project import fetch_duplicates


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
