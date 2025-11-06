'''System-level functions for managing Google Drive and Premiere Pro.'''

from pathlib import Path
from time import time, sleep
import subprocess

from structure import VIDEO_EXTS, PR_EXT, AE_EXT, GOOGLE_DRIVE_FOLDER, \
    GOOGLE_DRIVE_EXE, PREMIERE_EXE

REQUIRED_PATH = Path(GOOGLE_DRIVE_FOLDER)
WAIT_UP = 120 # seconds to wait for drive to reappear
POLL = 3 # seconds between checks

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

def get_videos_in_folder(folder: Path) -> list[Path]:
    '''Get list of video files in a folder (non-recursive).'''
    videos = []
    if folder.exists():
        videos = [p for p in folder.iterdir() if file_type(p) == 'VIDEO']
    return videos

def get_person_name(path: Path, year: int) -> str:
    return path.name.replace(f' {year}', '').strip()

def mount_premiere(t=20):
    subprocess.Popen(PREMIERE_EXE)
    sleep(t)

def mount_g_drive():
    if Path(GOOGLE_DRIVE_FOLDER).exists():
        started = True

    else:
        # force quit Google Drive if open
        # /T kills child processes; ignore errors if not running
        subprocess.run(['taskkill', '/IM', GOOGLE_DRIVE_EXE.name, '/F', '/T'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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