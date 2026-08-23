''' Environment secrets '''

import os
from pathlib import Path
import tomllib

# Use tomllib.load() to read secrets from the file
secret_file = Path(os.environ.get("YEAR_END_SECRETS_FILE", ".secrets/secrets.toml"))
with secret_file.open('rb') as f: # Use "rb" for binary read mode
    secrets = tomllib.load(f)
