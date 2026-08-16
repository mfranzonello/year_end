"""Read non-secret TOML configuration without initializing local integrations."""

from pathlib import Path
from typing import Any
import tomllib


CONFIG_FOLDER = Path("config")


def read_toml(name: str) -> dict[str, Any]:
    """Return the named non-secret configuration document."""
    with (CONFIG_FOLDER / f"{name}.toml").open("rb") as config_file:
        return tomllib.load(config_file)
