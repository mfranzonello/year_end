import requests

CLOUD = "dua0zy8wu"
PRESET = "your_unsigned_preset"

def upload_image(path_or_remote_url: str):
    url = f"https://api.cloudinary.com/v1_1/{CLOUD}/image/upload"
    data = {"upload_preset": PRESET, "file": path_or_remote_url}
    r = requests.post(url, data=data, timeout=15)
    r.raise_for_status()
    return r.json()["secure_url"]  # store this in Neon