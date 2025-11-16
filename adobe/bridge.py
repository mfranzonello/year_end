'''Functions to extract XMP metadata from video files after reviewed in Adobe Bridge.'''

from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional

from cv2 import VideoCapture, CAP_PROP_FRAME_COUNT, CAP_PROP_FPS, CAP_PROP_FRAME_WIDTH, CAP_PROP_FRAME_HEIGHT

from common.system import file_type, is_file_available

# --- Single mmap scan ---

_XMP_STARTS = (b"<x:xmpmeta", b"<xmp:xmpmeta>")
_XMP_END = b"</x:xmpmeta>"

def _find_xmp_bytes_fallback(path: Path, tail_bytes: int = 5000) -> Optional[bytes]:
    """Search the last N bytes of the file for XMP metadata."""
    file_size = path.stat().st_size
    start_pos = max(file_size - tail_bytes, 0)

    with path.open("rb") as f:
        f.seek(start_pos)
        data = f.read()

        # quick search for known start markers
        start_candidates = [data.find(m) for m in _XMP_STARTS]
        start_candidates = [i for i in start_candidates if i != -1]
        if not start_candidates:
            return None

        start = min(start_candidates)
        end = data.find(_XMP_END, start)
        if end == -1:
            return None
        end += len(_XMP_END)

        return data[start:end]


# --- Extract xmp:Rating from an XMP XML packet ---

def _rating_from_xmp(xmp_bytes: bytes) -> Optional[int]:
    try:
        root = ET.fromstring(xmp_bytes)
    except Exception:
        return None
    # Attribute form on rdf:Description
    for desc in root.findall(".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
        for k, v in desc.attrib.items():
            if k.endswith("}Rating") or k.endswith(":Rating"):
                try:
                    n = int(v)
                    if 0 <= n <= 5:
                        return n
                except Exception:
                    pass
    # Element form anywhere
    for el in root.iter():
        tag = el.tag
        if isinstance(tag, str) and (tag.endswith("}Rating") or tag.endswith(":Rating")):
            txt = (el.text or "").strip()
            if txt.isdigit():
                n = int(txt)
                if 0 <= n <= 5:
                    return n
    return None

# --- Public API ---

def get_xmp_rating(file_path: Path) -> Optional[int]:
    '''Scans for xmp and returns rating'''
    if file_type(file_path) == 'VIDEO':
        xmp = _find_xmp_bytes_fallback(file_path)
        rating = _rating_from_xmp(xmp) if xmp else None

        return rating

def get_rated_videos(videos: list[Path], min_stars:int, local_only:bool=True) -> list[Path, list]:
    '''Returns a list of video files in file_path with xmp:Rating >= min_stars and all ratings. '''
    rated_videos = []
    video_ratings = []

    for video in videos:
        if local_only and is_file_available(video): ## avoids downloading from interweb
            rating = get_xmp_rating(video)
            if rating is not None:
                if rating >= min_stars:
                    rated_videos.append(video)
                video_ratings.append(rating)

    return rated_videos, video_ratings

def get_video_durations(videos: list[Path], local_only:bool=True) -> list[float]:
    video_durations = []
    for video in videos:
        if local_only and is_file_available(video): ## avoids downloading from interweb
            v = VideoCapture(video)
            frame_count = v.get(CAP_PROP_FRAME_COUNT)
            fps = v.get(CAP_PROP_FPS)
            duration = frame_count / fps if fps else 0
        else:
            duration = 0
        video_durations.append(duration)

    return video_durations

def get_video_resolutions(videos: list[Path], local_only:bool=True) -> list[float]:
    video_resolutions = []
    resolution_ranges = [(480, 'lo'), (720, 'SD'), (1080, 'HD'), (1920, '4K')]
    for video in videos:
        if local_only and is_file_available(video): ## avoids downloading from interweb
            v = VideoCapture(video)
            w = v.get(CAP_PROP_FRAME_WIDTH)
            h = v.get(CAP_PROP_FRAME_HEIGHT)
            res_short = (min(w, h))
            for res, res_name in resolution_ranges[::-1]:
                if res_short >= res:
                    resolution = res_name
                    break
                resolution = res_name

        else:
            resolution = None

        video_resolutions.append(resolution)

    return video_resolutions