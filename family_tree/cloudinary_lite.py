from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from pandas import isnull

def url_is_404(url:str) -> bool:
    try:
        with urlopen(url) as response:
            return response.status == 404
    except HTTPError as e:
        return e.code == 404   # real 404
    except URLError:
        return True  # network error -> treat as invalid

cloudinary_domain = 'https://res.cloudinary.com'

def grayscale_image(image_url:str) -> str|None:
    if image_url:
        return image_url.replace('/upload/', '/upload/e_grayscale/')
    
def grayscale_zero_images(image_url:str, value:int) -> str|None:
    if value == 0 or isnull(value):
        return grayscale_image(image_url)
    else:
        return image_url

def get_image_url(cloud_name:str, profile_id:str) -> str|None:
    if profile_id:
        url = f'{cloudinary_domain}/{cloud_name}/image/upload/{profile_id}'

        return url
        ##if not url_is_404(url):
        ##    return url

    else:
        # maybe provide default image
        return