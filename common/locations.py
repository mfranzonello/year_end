import json
import os
import sys
from pathlib import Path
from typing import Optional

# ---------- Helpers

def _first_existing(paths):
    for p in paths:
        if p and Path(p).exists():
            return Path(p)
    return None

def _glob_first(base: Path, pattern: str):
    matches = sorted(base.glob(pattern))
    return matches[0] if matches else None

# ---------- OneDrive

def detect_system() -> Optional[str]:
    match sys.platform:
        case 'win32':
            return 'windows'
        case 'darwin':
            return 'macos'
        case 'linux' | 'linux2':
            return 'linux'

def detect_onedrive_base() -> Path | None:
    """
    Returns the OneDrive *root* (the folder you see in Explorer/Finder), e.g.:
      Windows (consumer): C:\\Users\\mfran\\OneDrive
      Windows (business): C:\\Users\\mfran\\OneDrive - CompanyName
      macOS (personal):   ~/Library/CloudStorage/OneDrive-Personal
      macOS (business):   ~/Library/CloudStorage/OneDrive-<Tenant>
    """
    home = Path.home()

    match detect_system():
        case 'windows':
            # 1) Environment variable (most reliable for consumer; also appears for business)
            candidates = []
            for env_key in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
                val = os.environ.get(env_key)
                if val:
                    candidates.append(val)

            # 2) Common defaults under home (“OneDrive”, “OneDrive - *”)
            candidates += [home / "OneDrive"]
            candidates += list((home).glob("OneDrive - *"))

            # 3) Registry (user hive)
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\OneDrive") as k:
                    for name in ("UserFolder", "OneDrivePath"):
                        try:
                            val, _ = winreg.QueryValueEx(k, name)
                            candidates.append(val)
                        except FileNotFoundError:
                            pass
            except Exception:
                pass

            return _first_existing(candidates)

        case 'macos':
            # macOS (Apple File Provider)
            cloud_root = home / "Library" / "CloudStorage"
            # Prefer personal, else any OneDrive-*
            return _first_existing([
                cloud_root / "OneDrive-Personal",
                _glob_first(cloud_root, "OneDrive-*"),
                cloud_root / "OneDrive"  # rare legacy
            ])

# ---------- Google Drive

def detect_gdrive_base() -> Path | None:
    """
    Returns the *mounted* Google Drive root:
      Windows (streaming): G:\\  (but we’ll detect it dynamically)
      Windows (mount point path): e.g. C:\\Users\\...\\MyDrive (if configured as folder)
      macOS: ~/Library/CloudStorage/GoogleDrive-<account>
    NOTE: From this root, user content is under “My Drive/”.
    """
    home = Path.home()

    match detect_system():
        case 'windows':
            candidates = []

            # 1) DriveFS config file (most reliable)
            cfg_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "DriveFS"
            if cfg_dir.exists():
                # user-specific subfolder; ‘user_default’ or a GUID-like folder
                for sub in [cfg_dir / "user_default", *_safe_children(cfg_dir)]:
                    sync_cfg = sub / "sync_config.json"
                    if sync_cfg.exists():
                        try:
                            data = json.loads(sync_cfg.read_text(encoding="utf-8"))
                            # Either a drive letter (e.g., "G") or a full path mount point
                            letter = data.get("drive_letter")
                            if letter:
                                candidates.append(f"{letter}:\\")
                                candidates.append(f"{letter}:\\My Drive")
                            mount_point = data.get("mount_point_path") or data.get("mount_point")
                            if mount_point:
                                candidates.append(mount_point)
                                candidates.append(str(Path(mount_point) / "My Drive"))
                        except Exception:
                            pass

            # 2) Registry (DriveFS)
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\DriveFS") as k:
                    for name in ("DefaultMountPoint", "MountPointPath"):
                        try:
                            val, _ = winreg.QueryValueEx(k, name)
                            if val:
                                candidates.append(val)
                                candidates.append(str(Path(val) / "My Drive"))
                        except FileNotFoundError:
                            pass
                    # Sometimes a drive letter is stored
                    for name in ("DriveLetter",):
                        try:
                            val, _ = winreg.QueryValueEx(k, name)
                            if val:
                                candidates.append(f"{val}:\\")
                                candidates.append(f"{val}:\\My Drive")
                        except FileNotFoundError:
                            pass
            except Exception:
                pass

            # 3) Common fallbacks
            for letter in ("G", "H", "I"):
                candidates.append(f"{letter}:\\")
                candidates.append(f"{letter}:\\My Drive")

            return _first_existing(candidates)

        case 'macoS':
            # macOS (Apple File Provider)
            cloud_root = home / "Library" / "CloudStorage"
            # Typical names: GoogleDrive-<account>, GoogleDrive, GoogleDriveSharedDrives (the base).
            return _first_existing([
                _glob_first(cloud_root, "GoogleDrive-*"),
                cloud_root / "GoogleDrive",
            ])

def _safe_children(p: Path):
    try:
        return [c for c in p.iterdir() if c.is_dir()]
    except Exception:
        return []
    

from pathlib import Path

def list_versioned_dirs(base: Path, prefix: str):
    results = []

    for p in base.iterdir():
        if not p.is_dir():
            continue
        name = p.name

        if not name.startswith(prefix):
            continue

        # Extract everything after the prefix
        suffix = name[len(prefix):].strip()  # remove leading/trailing spaces

        # Try to parse version number; folders without versions get 0
        try:
            version = int(suffix) if suffix else 0
        except ValueError:
            # Contains something like "Adobe Premiere Pro Beta"
            version = 0

        results.append((version, p))

    # Sort descending by version
    results.sort(key=lambda x: x[0], reverse=True)

    # Return only the paths
    return [p for _, p in results]