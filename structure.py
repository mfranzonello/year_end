''' Project specific variables from YAML files '''

import json
import yaml
from pathlib import Path
import getpass

def read_yaml(filepath, filename, ext='.yaml'):
    with open(Path(filepath) / f'{filename}{ext}', 'r') as file:
        config = yaml.safe_load(file)
        
    return config

def read_json(filepath, filename, ext='.json'):
    with open(Path(filepath) / f'{filename}{ext}', 'r') as f:
        json_dict = json.load(f)
        
    return json_dict

def write_json(filepath, filename, json_dict, ext='.json'):
    with open(Path(filepath) / f'{filename}{ext}', 'w') as f:
        json.dump(json_dict, f)

def get_scope(folder):
    scope = read_json(folder, 'scopes')
    return ', '.join(scope)

_auths_folder = 'auths'
_tokens_folder = f'{_auths_folder}/tokens'
_config_folder = 'config'

_config = read_yaml(_config_folder, 'config')
_api = read_yaml(_config_folder, 'api')
_drives = read_yaml(_config_folder, 'drives')

# FILETYPES
VIDEO_EXTS = {
    ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".wmv", ".flv", ".webm",
    ".mpg", ".mpeg", ".mts", ".m2ts", ".ts", ".3gp"
}
PR_EXT = '.prproj'
AE_EXT = '.aep'

# EXECUTABLES
GOOGLE_DRIVE_EXE = _drives['executables']['google_drive'].replace('<user>', getpass.getuser())
PREMIERE_EXE = _drives['executables']['premiere'].replace('<user>', getpass.getuser())
EDGE_EXE = [p.replace('<user>', getpass.getuser()) for p in _drives['executables']['edge']]
CHROME_DATA = _drives['user_data']['chrome'].replace('<user>', getpass.getuser())
EDGE_DATA = _drives['user_data']['edge'].replace('<user>', getpass.getuser())

# LOCATIONS
AZURE_LOGIN_URL = _api['azure']['urls']['login']
AZURE_GRAPH_URL = _api['azure']['urls']['graph']
GPHOTOS_AUTH_URL = _api['gphotos']['urls']['auth']
GPHOTOS_TOKEN_URI = _api['gphotos']['urls']['token_uri']

GPHOTOS_PROJECT_ID = _config['gphotos']['project_id']
GPHOTOS_JS_ORIGINS = _config['gphotos']['javascript_origins']

ONE_DRIVE_FOLDER = _drives['local_storage']['one_drive'].replace('<user>', getpass.getuser())
GOOGLE_DRIVE_FOLDER = _drives['local_storage']['google_drive'].replace('<user>', getpass.getuser())
ADOBE_FOLDER = _drives['local_storage']['premiere'].replace('<user>', getpass.getuser())
YIR_CLIPS = _drives['add_ons']['clips']
YIR_REVIEWS = _drives['add_ons']['reviews']
YIR_PROJECT = _drives['add_ons']['project']

# MAPPINGS
SHARED_ALBUMS = read_json(_config_folder, 'albums')

# LIMITS
AZURE_RATE_LIMIT = _api['azure']['limits']['rate']

# VALUES
AZURE_TOKENS_FOLDER = f'{_tokens_folder}/azure'
AZURE_REDIRECT_URI = _config['azure']['redirect_uri']
AZURE_SCOPE = _config['azure']['scope']
AZURE_TENANT_ID = _config['azure']['tenant_id']
AZURE_YIR_FOLDER = _config['azure']['yir_folder_path']

GPHOTOS_SCOPES = _config['gphotos']['scope']
GPHOTOS_AUTH_PROVIDER_URL = _api['gphotos']['urls']['auth_provider_x509_cert_url']

COLOR_LABELS = read_json(_config_folder, 'labels')
ADOBE_BIN = _drives['add_ons']['videos_bin']

CHROME_STATE = read_json(CHROME_DATA, 'Local State', '')
EDGE_STATE = read_json(EDGE_DATA, 'Local State', '')
