#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pull videos from Google Photos shared albums (no Picker).

- Reads a JSON/YAML mapping of albums you've been sent:
    [
      {
        "share_token": "AF1Qi…",   # share link token OR full /share/<token> URL
        "album_id": null,           # filled after first join
        "joined": false,            # flipped true after first join
        "year": 2024,
        "person": "David"
      },
      ...
    ]

- Joins each shared album (one-time), persists album_id + joined.
- Lists media items for each album and downloads NEW videos only
  into:  <GD_ROOT>\YIR Clips\<YEAR>\<PERSON> <YEAR>\

Required scopes: photoslibrary.readonly + photoslibrary.sharing
"""

from __future__ import annotations
import argparse
from pathlib import Path
from typing import Dict, Any, Iterable, List, Optional
from urllib.parse import urlparse
import requests

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GARequest
from googleapiclient.discovery import build


# Google auth

from secret import get_secret
from structure import GPHOTOS_PROJECT_ID, GPHOTOS_AUTH_URL, GPHOTOS_TOKEN_URI, \
    GPHOTOS_AUTH_PROVIDER_URL, GPHOTOS_SCOPES, GPHOTOS_ALBUMS_PATH, GPHOTOS_ALBUMS_J, \
    YIR_CLIPS, GOOGLE_DRIVE_FOLDER, \
    read_json, write_json

def load_mapping() -> List[Dict[str, Any]]:
    return read_json(GPHOTOS_ALBUMS_PATH, GPHOTOS_ALBUMS_J)
    ##return json.loads(path.read_text(encoding="utf-8"))

def save_mapping(data: List[Dict[str, Any]]) -> None:
    write_json(GPHOTOS_ALBUMS_PATH, GPHOTOS_ALBUMS_J, data)
    ##path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------- Auth (Desktop OAuth client) ----------
def get_photos_service():
    client_config = {
        "installed": {
            "client_id": get_secret("GPHOTOS_D_CLIENT_ID"),
            "client_secret": get_secret("GPHOTOS_D_CLIENT_SECRET"),
            "auth_uri": GPHOTOS_AUTH_URL,
            "token_uri": GPHOTOS_TOKEN_URI,
            "auth_provider_x509_cert_url": GPHOTOS_AUTH_PROVIDER_URL,
        }
    }

    creds: Optional[Credentials] = None
    token_cache = Path(".gphotos_token.json")
    if token_cache.exists():
        creds = Credentials.from_authorized_user_file(str(token_cache), scopes=GPHOTOS_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GARequest())
        else:
            flow = InstalledAppFlow.from_client_config(client_config, scopes=GPHOTOS_SCOPES)
            creds = flow.run_local_server(port=0)  # loopback redirect
        token_cache.write_text(creds.to_json(), encoding="utf-8")

    photos_service = build("photoslibrary", "v1", credentials=creds, static_discovery=False)

    return photos_service, creds


# ---------- Helpers ----------
def normalize_share_token(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("http"):
        u = urlparse(raw)
        parts = [p for p in u.path.split("/") if p]
        if "share" in parts:
            i = parts.index("share")
            tok = parts[i + 1] if i + 1 < len(parts) else ""
            return tok
        raise ValueError("Provided URL is not a /share/<token> link.")
    # bare token; strip any accidental query string
    return raw.split("?")[0]

def ensure_join_and_album_id(service, row: Dict[str, Any], apply: bool) -> bool:
    """
    If not joined or missing album_id, call sharedAlbums.join.
    Returns True if the mapping was updated.
    """
    token = normalize_share_token(row.get("share_token") or row.get("share_id") or "")
    row["share_token"] = token
    if row.get("joined") and row.get("album_id"):
        return False

    if not apply:
        print(f"[dry] Would join album for {row.get('person')} {row.get('year')} token={token[:12]}...")
        return False

    print(f'{token=}')
    resp = service.sharedAlbums().join(body={"shareToken": token}).execute()
    album = resp.get("album", {})
    aid = album.get("id")
    if not aid:
        raise RuntimeError("Join returned no album.id")
    row["album_id"] = aid
    row["joined"] = True
    row.setdefault("title", album.get("title"))
    print(f"Joined: {row.get('person')} {row.get('year')} → {album.get('title')} ({aid})")
    return True

def iter_media_items(service, album_id: str) -> Iterable[Dict[str, Any]]:
    page_token = None
    while True:
        body = {"albumId": album_id, "pageSize": 100}
        if page_token:
            body["pageToken"] = page_token
        resp = service.mediaItems().search(body=body).execute()
        for item in resp.get("mediaItems", []):
            yield item
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

def is_video(item: Dict[str, Any]) -> bool:
    mime = item.get("mimeType", "")
    return mime.startswith("video/")

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def already_exists(dest_dir: Path, filename: str) -> bool:
    return (dest_dir / filename).exists()

def download_video(item: Dict[str, Any], dest_dir: Path, apply: bool) -> Optional[Path]:
    base_url = item.get("baseUrl")
    filename = item.get("filename") or f"{item.get('id')}.mp4"
    if not base_url:
        return None
    # Per API docs: use =dv for original-quality video; =d for images
    url = f"{base_url}=dv"
    out = dest_dir / filename
    if already_exists(dest_dir, filename):
        return None
    if not apply:
        print(f"[dry] Would download {filename} -> {out}")
        return out

    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        ensure_dir(dest_dir)
        with open(out, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    return out

# ---------- Main process ----------
def run_pull(gd_root: Path, year_filter: Optional[int], person_filter: Optional[str], apply: bool):
    service, _creds = get_photos_service()

    data = load_mapping()
    changed = False

    total_new = 0
    per_person: Dict[str, int] = {}

    for row in data:
        y = row.get("year")
        p = row.get("person") or "Unknown"
        if year_filter and int(y) != int(year_filter):
            continue
        if person_filter and person_filter.lower() not in str(p).lower():
            continue

        # Join if needed (and persist album_id)
        if ensure_join_and_album_id(service, row, apply):
            changed = True

        album_id = row.get("album_id")
        if not album_id:
            print(f"Skip {p} {y}: no album_id yet.")
            continue

        # Destination folder
        dest_dir = gd_root / YIR_CLIPS / str(y) / f"{p} {y}"
        ensure_dir(dest_dir)

        new_count = 0
        for item in iter_media_items(service, album_id):
            if not is_video(item):
                continue
            if download_video(item, dest_dir, apply):
                new_count += 1

        total_new += new_count
        per_person[p] = per_person.get(p, 0) + new_count
        print(f"{p} {y}: {new_count} new video(s).")

    if changed and apply:
        save_mapping(data)

    print("\n=== Summary ===")
    for person, n in per_person.items():
        print(f"{person}: {n} new")
    if not per_person:
        print("No albums processed (filter?)")
    print(f"TOTAL new videos: {total_new}")
    if not apply:
        print("(dry run; nothing written)")

def main():
    ap = argparse.ArgumentParser(description="Pull NEW videos from Google Photos shared albums into local Google Drive.")
    ##ap.add_argument("--mapping", type=Path, required=True, help="Mapping file (json or yaml) with share_token/year/person/etc.")
    ap.add_argument("--gd-root", type=Path, default=Path(GOOGLE_DRIVE_FOLDER), help="Google Drive local root")
    ap.add_argument("--year", type=int, help="Only process a single year")
    ap.add_argument("--person", type=str, help="Only process a single person (substring match)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Write files / join albums")
    mode.add_argument("--dry-run", action="store_true", help="Plan only (default)")
    args = ap.parse_args()

    apply = bool(args.apply)
    run_pull(args.gd_root, args.year, args.person, apply)

if __name__ == "__main__":
    main()