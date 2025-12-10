from pathlib import Path
from uuid import UUID

from pandas import DataFrame
import cloudinary
import cloudinary.api
import cloudinary.uploader
from cloudinary.exceptions import NotFound

CLOUDINARY_DOMAIN = 'https://res.cloudinary.com'
DEFAULT_IMAGE = 'images/default_image.png'
PROFILES = 'profile_to_replace'

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

def upload_image(public_id:UUID, image_path:Path, display_name:str):
    cloudinary.uploader.upload(image_path, public_id=str(public_id), display_name=display_name, asset_folder=PROFILES)

def update_display_name(public_id:UUID, display_name:str):
    cloudinary.api.update(str(public_id), display_name=display_name)

def fill_in_temp_pictures(display_names:DataFrame, default_image:Path=Path(DEFAULT_IMAGE)):
    if default_image:
        for _, (member_id, full_name) in display_names.iterrows():
            print(f'Looking for {full_name}')
            result = fetch_resource(member_id)
            if not result:
                upload_image(public_id=member_id, image_path=default_image, display_name=full_name)
            else:
                if result['display_name'] != full_name:
                    update_display_name(member_id, full_name)
