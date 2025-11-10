''' Environment secrets '''

from os import getenv

from dotenv import dotenv_values, find_dotenv, load_dotenv, set_key

from common.structure import read_json, write_json

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

def get_token(directory, user_id):
    token_info = read_json(directory, user_id)
    return token_info

def save_token(directory, user_id, token_dict):
    token_info = read_json(directory, user_id)
    token_info.update(token_dict)
    write_json(directory, user_id, token_dict)
