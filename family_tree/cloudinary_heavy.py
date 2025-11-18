from ast import Try
from pathlib import Path
from uuid import UUID

import cloudinary
import cloudinary.api
from cloudinary.exceptions import NotFound

CLOUDINARY_DOMAIN = 'https://res.cloudinary.com'
DEFAULT_IMAGE = 'images/default_image.png'

def configure_cloud(cloud_name:str, api_key:str, api_secret:str):
    _ = cloudinary.config(cloud_name=cloud_name,
                          api_key=api_key,
                          api_secret=api_secret,
                          secure=True)

def is_cloundinary_image(image_url:str) -> bool:
    # sample url: dua0zy8wu/image/upload/v1762830428/agent_5_wbcywo.png
    return image_url.startswith(CLOUDINARY_DOMAIN)

def is_uploaded(public_id:UUID) -> bool:
    try:
        result = cloudinary.api.resource(str(public_id))
        return True

    except NotFound:
        return False

def upload_image(public_id:UUID, image_path:Path):
    cloudinary.uploader.upload(image_path, public_id=str(UUID))

def fetch_image_url(public_id:UUID, default_url:str|None=None) -> str|None:
    try:
        result = cloudinary.api.resource(str(public_id))
        return result['secure_url']

    except NotFound:
        print('resource not found')
        return default_url

def fill_in_temp_pictures(public_ids:list[UUID], default_image:Path=Path(DEFAULT_IMAGE)):
    for public_id in public_ids:
        if not is_uploaded(public_id) and default_image:
            upload_image(public_id, default_image)