"""Read non-secret TOML configuration without initializing local integrations."""

from pathlib import Path
from typing import Any
import argparse
import os
import tomllib


CONFIG_FOLDER = Path("config")
CONFIG_NAMES = ('api', 'drives', 'webhooks')


def variable_name(name: str) -> str:
    """Return the environment variable for an explicitly supported config file."""
    if name not in CONFIG_NAMES:
        raise ValueError('Config must be api, drives, or webhooks; examples are not runtime config.')
    return f'YEAR_END_CONFIG_{name.upper()}_TOML'


def parse_config(text: str, name: str) -> dict[str, Any]:
    """Parse configuration without exposing values in validation errors."""
    variable_name(name)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise ValueError(f'Invalid TOML in {name} configuration.') from None
    if not data or 'REPLACE_ME' in text:
        raise ValueError(f'Complete the required values in {name} configuration.')
    return data


def config_text(name: str) -> str:
    """Read a complete environment document, otherwise the local TOML file."""
    variable = variable_name(name)
    if variable in os.environ:
        text = os.environ[variable]
    else:
        try:
            text = (CONFIG_FOLDER / f'{name}.toml').read_text(encoding='utf-8')
        except FileNotFoundError:
            raise ValueError(f'Set {variable} or create config/{name}.toml.') from None
    parse_config(text, name)
    return text


def read_toml(name: str) -> dict[str, Any]:
    """Read runtime configuration; environment replaces the entire local document."""
    return parse_config(config_text(name), name)


def main() -> None:
    """Validate runtime configuration and optionally package it for deployment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('names', nargs='+', choices=CONFIG_NAMES)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    documents = {name: config_text(name) for name in args.names}
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, text in documents.items():
            (args.output_dir / f'{name}.toml').write_text(text, encoding='utf-8')
    print('Validated configuration: ' + ', '.join(documents))


if __name__ == '__main__':
    main()
