''' Project specific variables from TOML and JASON files '''

from pathlib import Path
import json
import tomllib

from common.locations import detect_gdrive_base, detect_onedrive_base, detect_app_path, get_browser_data

_auths_folder = 'auths'
_config_folder = 'config'
_tokens_folder = f'{_auths_folder}/tokens'

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
    else:
        print(f'Path {path} does not exist. Cannot write JSON.')

def get_scope(folder):
    scope = read_json(folder, 'scopes')
    if scope:
        return ', '.join(scope)
            
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
GOOGLE_DRIVE_FOLDER = google_drive_base / _drives['local_storage']['google_drive']['videos']
ADOBE_FOLDER = one_drive_base / _drives['local_storage']['adobe']['projects']
COMMON_FOLDER = ADOBE_FOLDER / _drives['local_storage']['adobe']['common']

QUARANTINE = _drives['local_storage']['quarantine']
YIR_REVIEWS = _drives['local_storage']['adobe']['reviews']
YIR_PROJECT = _drives['local_storage']['adobe']['project']
LABEL_PRESET = _drives['local_storage']['adobe']['label_preset']

# MAPPINGS
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