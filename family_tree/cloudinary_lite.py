from urllib.request import urlopen
from urllib.error import HTTPError, URLError

def url_is_404(url:str) -> bool:
    try:
        with urlopen(url) as response:
            return response.status == 404
    except HTTPError as e:
        return e.code == 404   # real 404
    except URLError:
        return True  # network error -> treat as invalid

cloudinary_domain = 'https://res.cloudinary.com'

def greyscale_zero_images(image_url:str, value:int) -> str:
    if image_url and value == 0:
        return image_url.replace('/upload/', '/upload/e_grayscale/')
    else:
        return image_url

def get_image_url(cloud_name:str, profile_id:str) -> str:
    if profile_id:
        url = f'{cloudinary_domain}/{cloud_name}/image/upload/{profile_id}'

        return url
        ##if not url_is_404(url):
        ##    return url

    else:
        # maybe provide default image
        return