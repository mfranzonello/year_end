from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path
from uuid import UUID
from io import BytesIO
from datetime import datetime

import cloudinary
import cloudinary.api
import cloudinary.uploader
from cloudinary.exceptions import NotFound
from pandas import DataFrame
import streamlit as st

from database.db import Engine
from database.db_images import fetch_image_information, update_image_information

PROFILES = 'profile_images' ## this should move to a config/secrets file
CLOUDINARY_RESPONSE_COLS = {'version': 'version_number',
                            'created_at': 'upload_time',
                            }
CLOUDINARY_DOMAIN = 'https://res.cloudinary.com'

IMAGE_CACHE = Path('.cache/family-tree-images')

IMAGE_TYPES = {'person': 0, 'animal': 1}

def configure_cloud(cloud_name:str, api_key:str, api_secret:str):
    _ = cloudinary.config(cloud_name=cloud_name,
                          api_key=api_key,
                          api_secret=api_secret,
                          secure=True)

def is_cloundinary_image(image_url:str) -> bool:
    # sample url: dua0zy8wu/image/upload/v1762830428/agent_5_wbcywo.png
    return image_url.startswith(CLOUDINARY_DOMAIN)

def fetch_resource(public_id:UUID) -> bool:
    try:
        return cloudinary.api.resource(str(public_id))

    except NotFound:
        return False

@st.cache_data
def get_version(_engine:Engine, public_id:UUID) -> str:
    image_information = fetch_image_information(_engine, public_id)
    if len(image_information):
        return image_information['version_number'].iloc[0]
    
def upload_image(engine:Engine, public_id:UUID, display_name:str, image_path:Path=None, binary_data=None):
    if binary_data:
        file_stream = BytesIO(binary_data)
        file_stream.name = binary_data.name
    else:
        file_stream = image_path

    response = cloudinary.uploader.upload(image_path, public_id=str(public_id),
                                          display_name=display_name, asset_folder=PROFILES)

    image_information = DataFrame([response]).rename(columns=CLOUDINARY_RESPONSE_COLS)
    image_information['update_time'] = image_information['upload_time'] 
    update_image_information(engine, image_information)

def update_display_name(engine:Engine, public_id:UUID, display_name:str):
    response = cloudinary.api.update(str(public_id), display_name=display_name)

    image_information = DataFrame([response]).rename(columns=CLOUDINARY_RESPONSE_COLS)
    update_image_information(engine, image_information)

def url_is_404(url:str) -> bool:
    try:
        with urlopen(url) as response:
            return response.status == 404
    except HTTPError as e:
        return e.code == 404   # real 404
    except URLError:
        return True  # network error -> treat as invalid

def border_image(image_url: str, border_color:str) -> str|None:
    if image_url:
        return image_url.replace('/upload/', '/upload/e_grayscale/')

def get_image_url(engine:Engine, cloud_name:str, profile_id:str, profile_type:str=None,
                  grayscale=False, border_color=None, border_width=5, pixels=None, square=False) -> str|None:
    if profile_id:
        url_start = f'{CLOUDINARY_DOMAIN}/{cloud_name}/image/upload/'
        version = get_version(engine, profile_id)

        if not version:
            # check if a default image exists in the DB
            image_type = IMAGE_TYPES.get(profile_type, 0)
            profile_id = str(UUID(int=image_type))
            version = get_version(engine, profile_id)

        if not version:
            # check if any version exists in the cloud
            image_url_test = f'{url_start}/{profile_id}'

            if url_is_404(image_url_test):
                return None

        if not version:
            version_str = ''
        else:
            version_str = f'/v{version}'

        url_mids = [('e_grayscale', grayscale),
                    (f'bo_{border_width}px_solid_{border_color}', border_color),
                    (f'c_fill,w_{pixels},h_{pixels}', pixels),
                    (f'c_fill,ar_1:1', square)
                    ]
        image_url = url_start + ('/'.join(m for m, b in url_mids if b) + f'{version_str}/{profile_id}').replace('//', '/')

        return image_url

def get_image_path(engine:Engine, cloud_name: str, node_id: UUID, node_type: str) -> Path:

    # use cached folder
    IMAGE_CACHE.mkdir(parents=True, exist_ok=True)

    # check if default images exist
    default_image_paths = {}
    for n in IMAGE_TYPES:
        i = IMAGE_TYPES[n]
        default_image_path = IMAGE_CACHE / f'{UUID(int=i)}.png'
        if not default_image_path.exists():
            # download default image
            image_url = get_image_url(engine, cloud_name, UUID(int=i), pixels=100)
            default_image_path.write_bytes(urlopen(image_url, timeout=10).read())
        default_image_paths[n] = default_image_path
        
    # check if image already is in cached folder
    image_path = IMAGE_CACHE / f'{node_id}.png'
    if image_path.exists():
        # use downloaded image
        return str(image_path)

    else:
        # check if image exists in cloud
        version = get_version(engine, node_id)
        if version:
            # download image
            image_url = get_image_url(engine, cloud_name, node_id, pixels=100)
            image_path.write_bytes(urlopen(image_url, timeout=10).read())
        else:
            # use default
            image_path = default_image_paths[node_type]
    
    return str(image_path)