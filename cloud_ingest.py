"""Run Google Drive to OneDrive ingestion without mounted cloud drives."""

import argparse
from datetime import date

from common.secret import secrets
from database.db import get_engine
from repositories.ingest import ingest_google_drive_cloud
from repositories.iterate import get_media_locations


class LineConsole:
    """Emit cloud-runner-friendly status lines without cursor control."""

    @staticmethod
    def add_update(message: str) -> None:
        print(message, flush=True)


def _engine():
    """Build the configured project database engine."""
    config = secrets["postgresql"]
    return get_engine(
        config["host"], str(config["port"]), config["database"],
        config["user"], config["password"],
    )


def ingest(project_year: int, dry_run: bool = True) -> None:
    """Sweep every configured media type for one project year."""
    engine = _engine()
    ui = LineConsole()
    try:
        mode = "dry run" if dry_run else "apply"
        ui.add_update(
            f"Starting Google Drive cloud ingest for {project_year} ({mode})."
        )
        for media_type, _supfolder_name in get_media_locations(engine):
            ingest_google_drive_cloud(
                engine,
                media_type,
                project_year,
                ui,
                dry_run=dry_run,
            )
        ui.add_update("Google Drive cloud ingest complete.")
    finally:
        engine.dispose()


def main() -> None:
    """Parse cloud-ingestion arguments and run the selected year."""
    parser = argparse.ArgumentParser(
        description="Stream missing Google Drive videos into OneDrive.",
    )
    parser.add_argument(
        "--year", type=int, default=date.today().year,
        help="Project year to ingest; defaults to the current year.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Copy missing files.")
    mode.add_argument(
        "--dry-run", action="store_true",
        help="Inspect without copying files (the default).",
    )
    arguments = parser.parse_args()
    ingest(arguments.year, dry_run=not arguments.apply)


if __name__ == "__main__":
    main()
