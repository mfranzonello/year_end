"""Run canonical OneDrive inventory from a local or hosted cloud environment."""

import argparse
from datetime import date

from common.config import read_toml
from common.secret import secrets
from database.db import get_engine
from repositories.cloud_inspect import inspect_onedrive_cloud_contents
from repositories.iterate import get_media_locations


class LineConsole:
    """Emit cloud-runner-friendly status lines without terminal cursor control."""

    @staticmethod
    def add_update(message: str) -> None:
        print(message, flush=True)


def _engine():
    config = secrets["postgresql"]
    return get_engine(
        config["host"], str(config["port"]), config["database"],
        config["user"], config["password"],
    )


def inspect(project_year: int, dry_run: bool = True) -> None:
    """Reconcile one project year from OneDrive into Neon."""
    engine = _engine()
    ui = LineConsole()
    try:
        media_locations = get_media_locations(engine)
        project_root = read_toml("drives")["local_storage"]["onedrive"]["videos"]
        mode = "dry run" if dry_run else "apply"
        ui.add_update(f"Starting OneDrive cloud inspection for {project_year} ({mode}).")
        for media_type, supfolder_name in media_locations:
            inspect_onedrive_cloud_contents(
                engine,
                project_root,
                media_type,
                supfolder_name,
                ui,
                dry_run=dry_run,
                project_year=project_year,
            )
        ui.add_update("OneDrive cloud inspection complete.")
    finally:
        engine.dispose()


def main() -> None:
    """Parse cloud-inspection arguments and run the selected year."""
    parser = argparse.ArgumentParser(
        description="Inspect OneDrive through Microsoft Graph and reconcile Neon.",
    )
    parser.add_argument(
        "--year", type=int, default=date.today().year,
        help="Project year to inspect; defaults to the current year.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply database changes.")
    mode.add_argument(
        "--dry-run", action="store_true",
        help="Inspect without database changes (the default).",
    )
    arguments = parser.parse_args()
    inspect(arguments.year, dry_run=not arguments.apply)


if __name__ == "__main__":
    main()
