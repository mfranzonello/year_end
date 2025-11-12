cloudinary_domain = 'https://res.cloudinary.com'

def greyscale_zero_images(image_url, value):
    if image_url and value == 0:
        return image_url.replace('/upload/', '/upload/e_grayscale/')
    else:
        return image_url

def get_image_url(cloud_name:str, profile_id:str):
    if profile_id:
        return f'{cloudinary_domain}/{cloud_name}/image/upload/{profile_id}'
    else:
        # maybe provide default image
        return