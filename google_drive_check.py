"""Authenticate to Google Drive and list root-level items without making changes."""

from __future__ import annotations

import argparse

from integrations.google_drive.auth import GoogleAuthError
from integrations.google_drive.client import GoogleDriveRequestError, list_root_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Authenticate and list the first page of Google Drive root items.")
    parser.add_argument("--login", action="store_true", help="Ignore a cached token and sign in again.")
    args = parser.parse_args()
    try:
        items = list_root_items(force_login=args.login)
    except (GoogleAuthError, GoogleDriveRequestError) as error:
        raise SystemExit(f"Google Drive check failed: {error}") from error
    print(f"Connected to Google Drive. First {len(items)} root item(s):")
    for item in items:
        item_type = "folder" if item["mimeType"] == "application/vnd.google-apps.folder" else "file"
        print(f"  [{item_type}] {item['name']}")


if __name__ == "__main__":
    main()
