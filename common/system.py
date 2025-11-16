'''System-level functions for managing Google Drive and Premiere Pro.'''

import os
import re
from pathlib import Path
from time import time, sleep
import subprocess
import ctypes
from ctypes import wintypes

from common.structure import VIDEO_EXTS, PR_EXT, AE_EXT, GOOGLE_DRIVE_FOLDER, \
    GOOGLE_DRIVE_EXE, PREMIERE_EXE, EDGE_EXE

REQUIRED_PATH = Path(GOOGLE_DRIVE_FOLDER)
WAIT_UP = 120 # seconds to wait for drive to reappear
POLL = 3 # seconds between checks

# Define constants for file attributes
FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
FILE_ATTRIBUTE_OFFLINE = 0x1000
FILE_ATTRIBUTE_PINNED = 0x80000       # Always keep on this device
FILE_ATTRIBUTE_UNPINNED = 0x100000      # Not kept locally
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA = 0x00400000
    
GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
GetFileAttributesW.restype  = wintypes.DWORD

def clear_screen():
    '''Clears the console screen based on the operating system.'''
    if os.name == 'nt':  # For Windows
        os.system('cls')
    else:  # For Unix-like systems (Linux, macOS)
        os.system('clear')

def file_type(file_path: Path) -> str:
    if file_path.is_file():
        suffix = file_path.suffix.lower()

        if suffix in VIDEO_EXTS:
            return 'VIDEO'
        elif suffix == PR_EXT:
            return 'PREMIERE_PROJECT'
        elif suffix == AE_EXT:
            return 'AFTER_EFFECTS_PROJECT'

    return 'UNKNOWN'

def get_file_sizes(videos:list[Path]) -> list[int]:
    file_sizes = [int(v.stat().st_size // 1e6) for v in videos]
    return file_sizes

def get_videos_in_folder(folder: Path) -> list[Path]:
    '''Get list of video files in a folder (non-recursive).'''
    videos = []
    if folder.exists():
        videos = [p for p in folder.iterdir() if file_type(p) == 'VIDEO']
    return videos

def get_actual_year(folder_path: Path) -> int:
    match = re.search(r"\s(\d{4})$", folder_path.name)
    return int(match.group(1)) if match else None

def get_person_name(folder_path: Path) -> str:
    year = get_actual_year(folder_path)
    return folder_path.name.replace(f' {year}', '').strip()

def get_person_names(root: Path):
    '''Get person names from OneDrive YIR clips for a given year.'''
    year = root.name
    person_names = [get_person_name(p) for p in root.iterdir() if p.is_dir() and get_actual_year(p)]
    return person_names

def mount_premiere(t=20):
    subprocess.Popen(PREMIERE_EXE)
    sleep(t)

def close_exe(exe):
    '''lose an executable by name or list of names.'''
    if isinstance(exe, list):
        # multiple executables
        for ex in exe:
            close_exe(ex)

    if isinstance(exe, (str, Path)):
        # valid single executable
        try:
            # /f = force, /im = by image name, suppress output
            subprocess.run(['taskkill', '/F', '/IM', Path(exe).name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def mount_g_drive():
    if Path(GOOGLE_DRIVE_FOLDER).exists():
        started = True

    else:
        # force quit Google Drive if open
        close_exe(GOOGLE_DRIVE_EXE)

        if Path(GOOGLE_DRIVE_EXE).exists():
            try:
                # Use START to detach on Windows so it keeps running if script exits
                subprocess.Popen(['cmd', '/c', 'start', '""', GOOGLE_DRIVE_EXE],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                started = True
            except Exception:
                started = False

        if not started:
            print('[gd] Could not find Google Drive executable. '
                  'Update GOOGLE_DRIVE_PATHS with your install path.')
            return False

            # Wait for the mount to come back
            deadline = time() + WAIT_UP
            while time() < deadline:
                if Path(GOOGLE_DRIVE_FOLDER).exists():
                    print('[gd] Google Drive is back.')
                    return True
                sleep(POLL)

            print('[gd] Timed out waiting for Google Drive to remount.')

def check_file_availability(file_path: Path):
    '''Return one of: 'pinned_local', 'local', 'cloud_placeholder', 'dehydrated_placeholder', 'unknown'.'''
    attrs = GetFileAttributesW(str(file_path))
    if attrs == 0xFFFFFFFF:  # INVALID_FILE_ATTRIBUTES
        return 'unknown'

    pinned = bool(attrs & FILE_ATTRIBUTE_PINNED)
    unpinned = bool(attrs & FILE_ATTRIBUTE_UNPINNED)
    reparse = bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)
    recall_any = bool(attrs & (FILE_ATTRIBUTE_RECALL_ON_OPEN | FILE_ATTRIBUTE_RECALL_ON_DATA))
    offline = bool(attrs & FILE_ATTRIBUTE_OFFLINE)

    # Heuristics consistent with OneDrive Files On-Demand flags
    if pinned:
        return 'pinned_local'
    if reparse and unpinned:
        # Cloud-only placeholder (won't be present on disk until opened)
        return 'cloud_placeholder'
    if recall_any or offline:
        # Item can recall data on access (dehydrated or partially recalled)
        return 'dehydrated_placeholder'
    # No special cloud flags -> file is fully local right now
    return 'local'

def is_file_available(file_path: Path):
    return check_file_availability(file_path) in ['pinned_local', 'local']