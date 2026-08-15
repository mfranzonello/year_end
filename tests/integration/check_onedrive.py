"""Authenticate with Microsoft Graph and inspect the OneDrive root without making changes."""

import argparse

from integrations.onedrive.auth import MicrosoftAuthError
from integrations.onedrive.client import GraphRequestError, inspect_my_drive


def main() -> None:
    parser = argparse.ArgumentParser(description="Authenticate and list the first page of your OneDrive root.")
    parser.add_argument("--login", action="store_true", help="Ignore a cached token and sign in again.")
    args = parser.parse_args()

    try:
        root, children = inspect_my_drive(force_login=args.login)
    except (MicrosoftAuthError, GraphRequestError) as error:
        raise SystemExit(f"OneDrive check failed: {error}") from error

    print(f"Connected to OneDrive root: {root['name']}")
    print(f"Web URL: {root['webUrl']}")
    print(f"First {len(children)} item(s):")
    for item in children:
        item_type = "folder" if "folder" in item else "file"
        print(f"  [{item_type}] {item['name']}")


if __name__ == "__main__":
    main()
