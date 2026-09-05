from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from pathlib import Path
from tempfile import TemporaryDirectory

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

def border_image(image_url: str, border_color:str) -> str|None:
    if image_url:
        return image_url.replace('/upload/', '/upload/e_grayscale/')

# # def grayscale_image(image_url:str) -> str|None:
# #     if image_url:
# #         return image_url.replace('/upload/', '/upload/e_grayscale/')

# # def grayscale_zero_images(image_url:str, value:int) -> str|None:
# #     if value == 0 or isnull(value):
# #         return grayscale_image(image_url)
# #     else:
# #         return image_url

def get_image_url(cloud_name:str, profile_id:str, grayscale=False,
                  border_color=None, border_width=5, pixels=None) -> str|None:
    if profile_id:
        url_start = f'{cloudinary_domain}/{cloud_name}/image/upload/'
        url_mids = [('e_grayscale', grayscale),
                    (f'bo_{border_width}px_solid_{border_color}', border_color),
                    (f'w_{pixels}', pixels)
                    ]
                    
        return url_start + ('/'.join(m for m, b in url_mids if b) + f'/{profile_id}').replace('//', '/')

def get_image_path(cloud_name: str, node_id) -> str:
    image_url = get_image_url(cloud_name, node_id, pixels=100)

    if not url_is_404(image_url):
        with TemporaryDirectory() as directory:
            image_path = Path(directory) / f'{node_id}.png'
            image_path.write_bytes(urlopen(image_url, timeout=10).read())
            return str(image_path)
