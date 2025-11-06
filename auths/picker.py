# picker_server.py
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional
import argparse
import yaml
import requests

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel
import uvicorn

from structure import GOOGLE_DRIVE_FOLDER, YIR_CLIPS, GPHOTOS_API_KEY, GPHOTOS_SCOPES #VIDEO_EXTS
from secret import get_secret

# ====== CONFIG ======
YAML_PATH = Path("albums.yaml")
STATIC_DIR = Path(__file__).resolve().parent  # points to yir/auths

# ---- Your existing Photos auth (env/YAML based) goes here ----
# Reuse the Desktop-app flow function you built earlier.
# Must provide readonly + sharing scopes.
from typing import Tuple
from googleapiclient.discovery import build
# from your_module import get_photos_service  # <- use your implementation

def get_photos_service() -> Tuple[Any, Any]:
    """Placeholder: replace with YOUR env/YAML-based implementation that returns (service, tokens)."""
    raise NotImplementedError("Hook up your env/YAML-based get_photos_service() here.")

# =============================================================

def load_cfg() -> dict:
    if YAML_PATH.exists():
        return yaml.safe_load(YAML_PATH.read_text(encoding="utf-8")) or {}
    return {}

def save_cfg(cfg: dict) -> None:
    YAML_PATH.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")

def ensure_album_mapping(cfg: dict, album_id: str, album_title: str) -> dict:
    cfg.setdefault("albums", {})
    if album_id not in cfg["albums"]:
        print(f"\nNew album detected:\n  {album_title}\n  id={album_id}")
        year = input("Enter year (e.g., 2025): ").strip()
        person = input("Enter person name (e.g., Veronica): ").strip()
        cfg["albums"][album_id] = {"year": int(year), "person": person, "title": album_title}
    return cfg

class AlbumRef(BaseModel):
    id: str
    name: Optional[str] = None

class RegisterPayload(BaseModel):
    albums: List[AlbumRef]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=True
)

@app.post("/register_albums")
def register_albums(payload: RegisterPayload):
    cfg = load_cfg()
    for a in payload.albums:
        cfg = ensure_album_mapping(cfg, a.id, a.name or "")
    save_cfg(cfg)
    return {"status": "ok", "registered": [a.id for a in payload.albums]}

# ------- Sync helpers (uses Photos Library API once we have albumIds) -------

def iter_album_videos(service, album_id: str):
    page = None
    while True:
        body = {"albumId": album_id, "pageSize": 100}
        if page: body["pageToken"] = page
        r = service.mediaItems().search(body=body).execute()
        for it in r.get("mediaItems", []):
            if "video" in it.get("mediaMetadata", {}):
                yield it
        page = r.get("nextPageToken")
        if not page:
            break

def ensure_dest(year: int, person: str) -> Path:
    dest = Path(GOOGLE_DRIVE_FOLDER) / YIR_CLIPS / str(year) / f"{person} {year}"
    dest.mkdir(parents=True, exist_ok=True)
    return dest

def download_with_bearer(url: str, out_path: Path, access_token: str):
    with requests.get(url, headers={"Authorization": f"Bearer {access_token}"}, stream=True) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1<<20):
                if chunk:
                    f.write(chunk)

def sync_all(dry_run: bool = True):
    cfg = load_cfg()
    albums = (cfg.get("albums") or {})
    if not albums:
        print("No albums mapped yet. Use the picker to register some.")
        return

    # Build Photos service (your env-based function should return a usable access token)
    service, tokens = get_photos_service()
    access_token = tokens["token"]

    total_new = 0
    for album_id, meta in albums.items():
        year = int(meta["year"])
        person = str(meta["person"])
        title = meta.get("title", "")
        dest = ensure_dest(year, person)
        existing = {p.name.casefold() for p in dest.glob("*") if p.is_file()}

        new_count = 0
        for mi in iter_album_videos(service, album_id):
            name = (mi.get("filename") or f"{mi['id']}.mp4")
            if name.casefold() in existing:
                continue
            if dry_run:
                print(f"[dry] {title}: would download {name} -> {dest}")
            else:
                url = mi["baseUrl"] + "=dv"
                download_with_bearer(url, dest / name, access_token)
            existing.add(name.casefold())
            new_count += 1

        print(f"{title or album_id}: new = {new_count}{' (dry-run)' if dry_run else ''}")
        total_new += new_count

    print(f"\nDONE. New videos: {total_new}{' (dry-run)' if dry_run else ''}")

@app.get("/sync")
def sync_endpoint(dry_run: bool = True):
    sync_all(dry_run=dry_run)
    return {"status": "ok"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="Run the picker receiver server (default: 127.0.0.1:8000)")
    ap.add_argument("--sync", action="store_true", help="Run a one-off sync right now")
    ap.add_argument("--apply", action="store_true", help="With --sync: actually download (default is dry-run)")
    args = ap.parse_args()

    if args.sync:
        sync_all(dry_run=not args.apply)
        return

    # default: serve API (for picker.html to call /register_albums)
    uvicorn.run(app, host="127.0.0.1", port=8000)

@app.get("/picker_config")
def picker_config():
    return {
        "CLIENT_ID": get_secret("GPHOTOS_CLIENT_ID"),
        "API_KEY": GPHOTOS_API_KEY,
        "SCOPES": GPHOTOS_SCOPES,
        }

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    main()

