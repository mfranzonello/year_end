''' Environment secrets '''

import tomllib

# Use tomllib.load() to read secrets from the file
with open('.secrets/secrets.toml', 'rb') as f: # Use "rb" for binary read mode
    secrets = tomllib.load(f)