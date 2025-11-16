''' Project specific variables from TOML and JASON files '''

import os
import json
from pathlib import Path
import getpass
import tomllib

from common.locations import detect_system, detect_gdrive_base, detect_onedrive_base, list_versioned_dirs

_auths_folder = 'auths'
_config_folder = 'config'
_tokens_folder = f'{_auths_folder}/tokens'

system = detect_system()

def read_toml(toml_name:str):
    with open(f'{_config_folder}/{toml_name}.toml', 'rb') as f: # Use "rb" for binary read mode
        struct = tomllib.load(f)
    return struct

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

def get_scope(folder):
    scope = read_json(folder, 'scopes')
    if scope:
        return ', '.join(scope)

def get_app_path(apps_details, app_name):
    app_path = None
    app_details = apps_details[system][app_name]
    match system:
        case 'windows':
            drive, _ = os.path.splitdrive(os.getcwd())
            program_files = ['program_files', 'program_files_x86']
            for p_f in program_files:
                applications = Path(f'{drive}/{p_f}')
                vendor_path = applications / app_details['vendor']
                if vendor_path.exists():
                    # check if versions, like Adobe Premiere 2025
                    app_versions = list_versioned_dirs(vendor_path, app_details['name'])
                    if len(app_versions):
                        for exe in app_details["exe"]:
                            app_path = app_versions[0] / f'{exe}.exe'
                            if app_path.exists():
                                return app_path
                
        case 'macos':
            applications = Path('/Applications')
            app_verions = list_versioned_dirs(applications, app_details['name'])
            if len(app_verions):
                for name in app_details['name']:
                    app_path = applications / f'{name}.app' / 'Contents' / 'MacOS' / name
                    if app_path.exists():
                        return app_path
            
def get_browser_data(browser_details):
    match system:
        case 'windows':
            drive, _ = os.path.splitdrive(os.getcwd())
            return Path(drive) / 'Users' / getpass.getuser() / browser_details / 'User Data'
        case 'macos':
            user_path = Path.home()
            return user_path / 'Library' / 'Application Support' / browser_details

_config = read_toml('config')
_api = read_toml('api')
_drives = read_toml('drives')

# FILETYPES
VIDEO_EXTS = {
    ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".wmv", ".flv", ".webm",
    ".mpg", ".mpeg", ".mts", ".m2ts", ".ts", ".3gp"
}
PR_EXT = '.prproj'
AE_EXT = '.aep'

# EXECUTABLES
GOOGLE_DRIVE_EXE = get_app_path(_drives['executables'], 'google_drive')
PREMIERE_EXE = get_app_path(_drives['executables'], 'premiere')
CHROME = get_app_path(_drives['executables'], 'chrome')
EDGE_EXE = get_app_path(_drives['executables'], 'edge')

CHROME_DATA = get_browser_data(_drives['user_data']['chrome'])
EDGE_DATA = get_browser_data(_drives['user_data']['edge'])
CHROME_STATE = read_json(CHROME_DATA, 'Local State', '')
EDGE_STATE = read_json(EDGE_DATA, 'Local State', '')

# LOCATIONS
one_drive_base = detect_onedrive_base()
google_drive_base = detect_gdrive_base()
ONE_DRIVE_FOLDER = one_drive_base / _drives['local_storage']['onedrive']['videos']
GOOGLE_DRIVE_FOLDER = one_drive_base / _drives['local_storage']['google_drive']['videos']
ADOBE_FOLDER = one_drive_base / _drives['local_storage']['adobe']['projects']

YIR_REVIEWS = _drives['local_storage']['adobe']['reviews']
YIR_PROJECT = _drives['local_storage']['adobe']['project']

# MAPPINGS
SHARED_ALBUMS = read_json(_config_folder, 'albums')
COLOR_LABELS = read_json(_config_folder, 'labels')
ADOBE_BIN = _drives['local_storage']['adobe']['bin']

# APIS
AZURE_LOGIN_URL = _api['azure']['urls']['login']
AZURE_GRAPH_URL = _api['azure']['urls']['graph']
AZURE_TOKENS_FOLDER = f'{_tokens_folder}/azure'
AZURE_REDIRECT_URI = _config['azure']['redirect_uri']
AZURE_SCOPE = _config['azure']['scope']
AZURE_TENANT_ID = _config['azure']['tenant_id']
AZURE_YIR_FOLDER = _config['azure']['yir_folder_path']
AZURE_RATE_LIMIT = _api['azure']['limits']['rate']

GPHOTOS_AUTH_URL = _api['gphotos']['urls']['auth']
GPHOTOS_TOKEN_URI = _api['gphotos']['urls']['token_uri']
GPHOTOS_PROJECT_ID = _config['gphotos']['project_id']
GPHOTOS_JS_ORIGINS = _config['gphotos']['javascript_origins']
GPHOTOS_SCOPES = _config['gphotos']['scope']
GPHOTOS_AUTH_PROVIDER_URL = _api['gphotos']['urls']['auth_provider_x509_cert_url']