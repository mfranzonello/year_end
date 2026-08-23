''' Project specific variables from TOML and JASON files '''

from pathlib import Path
import json

from common.config import read_toml
from common.video import VIDEO_EXTS
from common.locations import (detect_gdrive_base, detect_onedrive_base, detect_app_path, 
                              detect_external_drive, get_browser_data)

def read_json(filepath, filename, ext='.json'):
    path = Path(filepath) / f'{filename}{ext}'
    if path.exists():
        with open(path, 'r') as f:
            json_dict = json.load(f)
            
        return json_dict

def write_json(filepath, filename, json_dict, ext='.json'):
    path = Path(filepath) / f'{filename}{ext}'
    if path.exists():
        with open(Path(filepath) / f'{filename}{ext}', 'w') as f:
            json.dump(json_dict, f)
    else:
        print(f'Path {path} does not exist. Cannot write JSON.')

def get_scope(folder):
    scope = read_json(folder, 'scopes')
    if scope:
        return ', '.join(scope)
            
_drives = read_toml('drives')

# FILETYPES
PR_EXT = '.prproj'
AE_EXT = '.aep'
PR_LABEL_EX = '.prlabelpreset'

# EXECUTABLES
GOOGLE_DRIVE_EXE = detect_app_path(_drives['executables'], 'google_drive')
PREMIERE_EXE = detect_app_path(_drives['executables'], 'premiere')
CHROME = detect_app_path(_drives['executables'], 'chrome')
EDGE_EXE = detect_app_path(_drives['executables'], 'edge')

CHROME_DATA = get_browser_data(_drives['user_data']['chrome'])
EDGE_DATA = get_browser_data(_drives['user_data']['edge'])
CHROME_STATE = read_json(CHROME_DATA, 'Local State', '')

EDGE_STATE = read_json(EDGE_DATA, 'Local State', '')

# LOCATIONS
one_drive_base = detect_onedrive_base()
google_drive_base = detect_gdrive_base()

ONE_DRIVE_ROOT = one_drive_base
ONE_DRIVE_FOLDER = one_drive_base / _drives['local_storage']['onedrive']['videos']
GOOGLE_DRIVE_FOLDER = (
    google_drive_base / _drives['local_storage']['google_drive']['videos']
    if google_drive_base
    else None
)
ADOBE_FOLDER = one_drive_base / _drives['local_storage']['adobe']['projects']
COMMON_FOLDER = ADOBE_FOLDER / _drives['local_storage']['adobe']['common']

external_drive = detect_external_drive(_drives['ssd']['name'])
QUARANTINE_FOLDER = external_drive / _drives['ssd']['videos'] if external_drive else ONE_DRIVE_FOLDER

QUARANTINE = _drives['local_storage']['quarantine']
YIR_REVIEWS = _drives['local_storage']['adobe']['reviews']
YIR_PROJECT = _drives['local_storage']['adobe']['project']
LABEL_PRESET = _drives['local_storage']['adobe']['label_preset']

# MAPPINGS
ADOBE_BIN = _drives['local_storage']['adobe']['bin']
