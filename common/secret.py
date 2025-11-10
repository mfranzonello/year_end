''' Environment secrets '''

from os import getenv

from dotenv import dotenv_values, find_dotenv, load_dotenv, set_key

dotenv_file = load_dotenv(find_dotenv())

def get_secret(name, default=None):
    secret = getenv(name)
    if secret is None:
        if default is not None:
            secret = default
        else:
            print(f'Secret for {name} not found!')

    return secret

def set_secret(name, value):
    set_key(find_dotenv(), name, value, 'never')
  
def list_secrets():
    return dotenv_values(find_dotenv())