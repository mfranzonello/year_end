#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''Scan and copy new videos from Google Drive to OneDrive.'''

from pathlib import Path
import shutil
import re
from itertools import combinations

from common.system import get_person_names, is_year_folder

def get_year_folders(root:Path) -> list[Path]:
    ''' All folder names that are a year (e.g., '2020') '''
    if not root.exists():
        return []
    else:
        return [p for p in root.iterdir() if p.is_dir() and is_year_folder(p)]

def get_person_folders(root:Path) -> list[Path]:
    """Immediate child directories (e.g., 'Michael 2025')."""
    if not root.exists():
        return []
    else:
        return [p for p in root.iterdir() if p.is_dir()]

def gather_names_casefold(folder: Path) -> set[str]:
    """Set of existing filenames (casefolded) in a folder (non-recursive)."""
    names = set()
    if folder.exists():
        for p in folder.iterdir():
            if p.is_file():
                names.add(p.name.casefold())
    return names

def copy_if_needed(src_file: Path, dst_folder: Path, dry_run: bool) -> bool:
    """
    Copy file if a case-insensitive filename does not already exist in dst_folder.
    Returns True if a copy will/does happen, False otherwise.
    """
    existing = gather_names_casefold(dst_folder)
    if src_file.name.casefold() in existing:
        return False
    if dry_run:
        return True
    dst_folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_file, dst_folder / src_file.name)
    return True

def are_dupes(file_1:Path, file_2:Path, byte_threshold=5000):
    # common ways a file can be renamed
    renamings = ['_', '()'] # use re
    size_1 = file_1.stat().st_size
    is_match = []
    if is_match and abs(file_1.stat().st_size - file_2.stat().st_size()) < byte_threshold:
        return is_match[1]
    

def dedupe_folder(folder_path:Path, dry_run:bool):
    # identify candidates for removal
    files_in_folder = []
    file_pairings = combinations(files_in_folder)
    potential_dupes = []
    for file in files_in_folder:
        for file_1, file_2 in file_pairings:
            dupe = are_dupes(file_1, file_2)
            if dupe:
                potential_dupes.append(dupe)

    if not dry_run:
        # delete the potential dupes
        for file in set(potential_dupes):
            os.rm(file)
