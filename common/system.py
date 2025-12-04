'''System-level functions for managing Google Drive and Premiere Pro.'''

import os
import re
from pathlib import Path
from time import time, sleep
import subprocess

from common.locations import detect_system
from common.structure import VIDEO_EXTS, PR_EXT, AE_EXT, GOOGLE_DRIVE_FOLDER, GOOGLE_DRIVE_EXE, PREMIERE_EXE

system_name = detect_system()
if system_name == 'windows':
    import ctypes
    from ctypes import wintypes
    import pythoncom
    from win32com.shell import shell

REQUIRED_PATH = Path(GOOGLE_DRIVE_FOLDER)
WAIT_UP = 120 # seconds to wait for drive to reappear
POLL = 3 # seconds between checks


# Define constants for file attributes
match system_name:
    case 'windows':
        FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
        FILE_ATTRIBUTE_OFFLINE = 0x1000
        FILE_ATTRIBUTE_PINNED = 0x80000       # Always keep on this device
        FILE_ATTRIBUTE_UNPINNED = 0x100000      # Not kept locally
        FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
        FILE_ATTRIBUTE_RECALL_ON_DATA = 0x00400000
            
        GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
        GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
        GetFileAttributesW.restype  = wintypes.DWORD
    case _:
        pass

def clear_screen():
    '''Clears the console screen based on the operating system.'''
    match system_name:
        case 'windows':
            os.system('cls')
        case _:
            os.system('clear')

def file_type(file_path: Path) -> str:
    if file_path.is_dir():
        return 'DIRECTORY'
    
    if file_path.is_file():
        suffix = file_path.suffix.lower()

        if suffix in VIDEO_EXTS:
            return 'VIDEO'
        elif suffix == PR_EXT:
            return 'PREMIERE_PROJECT'
        elif suffix == AE_EXT:
            return 'AFTER_EFFECTS_PROJECT'
        elif suffix == '.lnk':
            return 'SHORTCUT'

    return 'UNKNOWN'

def get_file_sizes(videos:list[Path]) -> list[int]:
    file_sizes = [int(v.stat().st_size // 1e6) for v in videos]
    return file_sizes

def get_file_types_in_folder(folder:Path, f_type:str, recursive) -> list[Path]:
    '''Get list of specific file types in a folder'''
    files = []
    if folder.exists():
        if recursive:
            files = [p for p in folder.rglob('*') if file_type(p) == f_type]
        else:
            files = [p for p in folder.glob('*') if file_type(p) == f_type]
    return files

def get_videos_in_folder(folder:Path, recursive=False) -> list[Path]:
    '''Get list of video files in a folder'''
    return get_file_types_in_folder(folder, 'VIDEO', recursive)

def get_premiere_projects_in_folder(folder:Path, recursive=False) -> list[Path]:
    '''Get list of prproj files in a folder'''
    return get_file_types_in_folder(folder, 'PREMIERE_PROJECT', recursive)

def get_after_effecst_projects_in_folder(folder:Path, recursive=False) -> list[Path]:
    '''Get list of prproj files in a folder'''
    return get_file_types_in_folder(folder, 'AFTER_EFFECTS_PROJECT', recursive)

def get_shortcuts_in_folder(folder:Path, recursive=False) -> list[Path]:
    '''Get list of video files in a folder'''
    if system_name != 'windows':
        return []
    else:
        return get_file_types_in_folder(folder, 'SHORTCUT', recursive)
    
def get_year_folders(root:Path) -> list[Path]:
    ''' All folder names that are a year (e.g., '2020') '''
    if not root.exists():
        return []
    else:
        return [p for p in root.iterdir() if p.is_dir() and is_year_folder(p)]

def is_year_folder(path:Path) -> bool:
    name = path.name  # just the final component
    return len(name) == 4 and name.isdigit()

def get_actual_year(folder_name:str) -> int|None:
    match = re.search(r"\s(\d{4})$", folder_name)
    return int(match.group(1)) if match else None

def get_person_folders(root:Path) -> list[Path]:
    """Immediate child directories (e.g., 'Michael 2025')."""
    if not root.exists():
        return []
    else:
        return [p for p in root.iterdir() if p.is_dir()]

def get_subfolders(root:Path) -> list[Path]:
    '''All subdirectories, including via shortcuts'''
    if not root.exists():
        return []
    else:
        subfolders = []
        for r in set([root] + get_shortcuts_in_folder(root)):
            subfolders.append(p for p in r.rglob('*') if p.is_dir())
        
        return subfolders

def get_person_name(folder_path:Path|str) -> str:
    folder_name = folder_path.name if isinstance(folder_path, Path) else str(folder_path)
    year = get_actual_year(folder_name)
    return folder_name.replace(f' {year}', '').strip()  

def get_person_names(root:Path):
    '''Get person names from OneDrive YIR clips for a given year.'''
    person_names = [get_person_name(p) for p in root.iterdir() if p.is_dir() and get_actual_year(p.name)]
    return person_names

def sort_paths(folder_paths:list[Path]):
    return sorted(folder_paths, key=lambda p: p.name.lower())

def rebuild_path(parent_folder:Path, folder_name:str, subfolder_name:str, file_name:str) -> Path:
    if subfolder_name:
        return parent_folder / folder_name / subfolder_name / file_name
    else:
        return parent_folder / folder_name / file_name

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
    match system_name:
        case 'windows':
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
        
        case 'macos':
            # check file size
            if file_path.stat().st_blocks == 0:
                return 'cloud_placeholder'
            else:
                return 'pinned_local'
            
def is_file_available(file_path: Path):
    return check_file_availability(file_path) in ['pinned_local', 'local']

def resolve_relative_path(parent_path:Path, rel_path:str) -> Path:
# Combine with the project folder and resolve the .. segments
    return (parent_path / rel_path.replace("\\", "/")).resolve()

def resolve_shortcut_target(shortcut_path:Path) -> Path|None:
    """
    Resolve a Windows .lnk shortcut to its target path using pywin32.
    Returns a Path or None if it can't be resolved.
    """
    if system_name == 'windows':
        # Create COM ShellLink object
        pythoncom.CoInitialize()
        try:
            link = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink,
                None,
                pythoncom.CLSCTX_INPROC_SERVER,
                shell.IID_IShellLink
            )
            persist_file = link.QueryInterface(pythoncom.IID_IPersistFile)

            # Load the .lnk file
            persist_file.Load(str(shortcut_path), 0)

            # Get the target path
            path_buf, _ = link.GetPath(shell.SLGP_UNCPRIORITY)
            if not path_buf:
                return None

            return Path(path_buf)
        finally:
            pythoncom.CoUninitialize()
