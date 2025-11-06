#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''Scan and copy new videos from Google Drive to OneDrive.'''

from pathlib import Path
import shutil

def get_person_folders(root: Path) -> list[Path]:
    """Immediate child directories (e.g., 'Michael 2025')."""
    if not root.exists():
        return []
    return [p for p in root.iterdir() if p.is_dir()]

def get_person_names(root: Path):
    '''Get person names from OneDrive YIR clips for a given year.'''
    year = root.name
    person_names = [p.name.replace(f' {year}', '') for p in root.iterdir() if p.is_dir() and p.name.endswith(year)]
    return person_names

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