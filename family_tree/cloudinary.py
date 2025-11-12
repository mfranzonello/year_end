import cloudinary
import cloudinary.api
from cloudinary.exceptions import NotFound

CLOUDINARY_DOMAIN = 'https://res.cloudinary.com'

def configure_cloud(cloud_name, api_key, api_secret):
    _ = cloudinary.config(cloud_name=cloud_name,
                          api_key=api_key,
                          api_secret=api_secret,
                          secure=True)

def change_to_greyscale(image_url):
    return image_url.replace('/upload/', '/upload/e_greyscale/')

def fetch_image_url(profile_id, default_url=None):
    try:
        result = cloudinary.api.resource(str(profile_id))
        return result['secure_url']

    except NotFound:
        print('resource not found')
        return default_url

def is_cloundinary_image(image_url: str):
    # sample url: dua0zy8wu/image/upload/v1762830428/agent_5_wbcywo.png
    return image_url.startswith(CLOUDINARY_DOMAIN)