'''Functions to extract XMP metadata from video files after reviewed in Adobe Bridge.'''

from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime

from cv2 import VideoCapture, CAP_PROP_FRAME_COUNT, CAP_PROP_FPS, CAP_PROP_FRAME_WIDTH, CAP_PROP_FRAME_HEIGHT
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata
from hachoir.core import config as HachoirConfig
from hachoir.stream.input import NullStreamError
HachoirConfig.quiet = True

from common.system import file_type, is_file_available

# --- Single mmap scan ---

_XMP_STARTS = (b"<x:xmpmeta", b"<xmp:xmpmeta>")
_XMP_END = b"</x:xmpmeta>"

def is_examinable(file_path:Path, local_only:bool=False) -> bool:
    return (file_type(file_path) == 'VIDEO') and (not local_only or is_file_available(file_path))

def _find_xmp_bytes_fallback(path: Path, tail_bytes: int = 5000) -> bytes|None:
    """Search the last N bytes of the file for XMP metadata."""
    file_size = path.stat().st_size
    start_pos = max(file_size - tail_bytes, 0)

    with path.open("rb") as f:
        f.seek(start_pos)
        try:
            data = f.read()
        except OSError:
            print(f'{path} corrupted [xmp]')
            return

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

def _rating_from_xmp(xmp_bytes: bytes) -> int|None:
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

def get_video_rating(file_path:Path, local_only:bool=True) -> int|None:
    '''Scans for xmp and returns rating'''
    if is_examinable(file_path, local_only): ## avoids downloading from interweb       
        xmp = _find_xmp_bytes_fallback(file_path)
        rating = _rating_from_xmp(xmp) if xmp else None

        return rating

def get_video_cv2_details(file_path:Path, local_only:bool=True) -> list[float, str]:
    no_res = 'xx'
    resolution_ranges = [(320, 'vhs'), # VHS - 480x320
                         (480, 'sd'), # DVD / SD - 720x480
                         (720, 'hd'), # SMS HD - 1280x720
                         (1080, 'fhd'), # full-HD blu-ray - 1920x1080
                         (2160, '4k'), # ultra blu-ray - 3840x2160
                         (4320, '8k')] # 7680 x 4320

    if is_examinable(file_path, local_only): ## avoids downloading from interweb
        # get duration
        v = VideoCapture(file_path)

        if not v.isOpened() or v.get(CAP_PROP_FRAME_COUNT) < 1:
            # likely moov atom not found
            duration = 0
            resolution = no_res
            print(f'{file_path} corrupted [cv2]')

        else:
            # video is usable
            frame_count = v.get(CAP_PROP_FRAME_COUNT)
            fps = v.get(CAP_PROP_FPS)
            duration = round(frame_count / fps) if fps else 0 # return in seconds

            # get resolution
            w = v.get(CAP_PROP_FRAME_WIDTH)
            h = v.get(CAP_PROP_FRAME_HEIGHT)
            dimension = (min(w, h))
            for dim, res in resolution_ranges[::-1]:
                if dimension >= dim:
                    resolution = res
                    break
                resolution = res

        v.release()
        
    else:
        duration = 0
        resolution = None

    return duration, resolution

def parse_date_string(s: str):
    """
    Try multiple date formats commonly found in QuickTime/MP4 metadata.
    Returns a datetime or None.
    """
    s = s.strip()

    formats = [
        "%Y-%m-%d %H:%M:%S",      # 2024-04-19 16:08:32
        "%Y-%m-%dT%H:%M:%S",      # 2024-04-19T16:08:32
        "%Y-%m-%dT%H:%M:%SZ",     # 2024-04-19T16:08:32Z
        "%Y/%m/%d %H:%M:%S",      # 2024/04/19 16:08:32
        "%Y:%m:%d %H:%M:%S",      # 2024:04:19 16:08:32 (EXIF-style)
    ]

    for fmt in formats:
        try:
            return min(datetime.now(), datetime.strptime(s, fmt))
        except ValueError:
            pass

    return None

def get_video_date(file_path: Path, local_only=True) -> datetime|None:
    # look at QuickTime metadata
    if is_examinable(file_path, local_only): ## avoids downloading from interweb
        try:
            parser = createParser(str(file_path))
            if parser:
                metadata = extractMetadata(parser)
                if metadata:
                    for item in metadata.exportPlaintext():
                        if "creation date" in item.lower():
                            raw = item.split(":", 1)[1].strip()
                            return parse_date_string(raw)

        except NullStreamError:
            print(f'{file_path} corrupted [hachoir]')