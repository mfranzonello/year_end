"""Preview or synchronize non-secret TOML configuration through GitHub CLI."""

import argparse
import json
from pathlib import Path
import subprocess

from common.config import CONFIG_NAMES, parse_config, variable_name


def gh(arguments: list[str], body: str | None = None) -> str:
    """Invoke authenticated GitHub CLI without exposing configuration in errors."""
    try:
        result = subprocess.run(['gh', *arguments], input=body, text=True,
                                encoding='utf-8', capture_output=True, check=False,
                                timeout=60)
    except FileNotFoundError:
        raise ValueError('Install GitHub CLI and authenticate with gh auth login.') from None
    except subprocess.TimeoutExpired:
        raise ValueError('GitHub config request timed out; inspect remote state before retrying.') from None
    if result.returncode:
        raise ValueError('GitHub config request failed; check authentication, repository, '
                         'environment, and Variables permissions. No response values were logged.')
    return result.stdout


def validate_document(text: str, name: str) -> dict:
    """Reject templates, oversized variables, and credential-bearing documents."""
    data = parse_config(text, name)
    if len(text.encode('utf-8')) > 48000:
        raise ValueError(f'{name} exceeds the supported variable size.')
    def check(table: dict) -> None:
        for key, value in table.items():
            if any(part in key.lower() for part in
                   ('password', 'secret', 'private_key', 'access_token', 'refresh_token', 'api_key')):
                raise ValueError(f'{name} contains a credential-like key; use the secret store.')
            if isinstance(value, dict):
                check(value)
    check(data)
    return data


def sync(direction: str, name: str, path: Path, repository: str,
         environment: str | None = None, apply: bool = False,
         overwrite: bool = False) -> str:
    """Synchronize one document; previews disclose only names and change status."""
    variable = variable_name(name)
    scope = ['--repo', repository]
    if environment:
        scope += ['--env', environment]
    # Listing distinguishes a missing variable from authentication/network failure.
    records = json.loads(gh(['variable', 'list', *scope, '--json', 'name,value']))
    remote = next((row['value'] for row in records if row['name'] == variable), None)
    if direction == 'push':
        text = path.read_text(encoding='utf-8')
        validate_document(text, name)
        if remote == text:
            return f'{variable}: unchanged'
        action = 'create' if remote is None else 'update'
        if apply:
            gh(['variable', 'set', variable, *scope], body=text)
        return f'{variable}: {action}' + ('' if apply else ' (preview)')
    if remote is None:
        raise ValueError(f'{variable} is not configured in the selected scope.')
    validate_document(remote, name)
    if path.exists() and path.read_text(encoding='utf-8') == remote:
        return f'{variable}: unchanged'
    if apply:
        if path.exists() and not overwrite:
            raise ValueError('Local file differs; review the preview and use --overwrite to replace it.')
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation preserves an existing file unless replacement was requested.
        with path.open('w' if overwrite else 'x', encoding='utf-8', newline='') as output:
            output.write(remote)
    return f'{variable}: download' + ('' if apply else ' (preview; existing local file may differ)')


def main() -> None:
    """Parse an explicit scope and preview by default; never sync secrets implicitly."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('direction', choices=('push', 'pull'))
    parser.add_argument('name', choices=CONFIG_NAMES)
    parser.add_argument('--repo', required=True, help='GitHub owner/repository')
    parser.add_argument('--environment', help='Existing GitHub environment; omit for repository variables')
    parser.add_argument('--file', type=Path, help='Input/output TOML path; defaults to config/NAME.toml')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--overwrite', action='store_true', help='Allow pull to replace a local file')
    args = parser.parse_args()
    path = args.file or Path('config') / f'{args.name}.toml'
    if '.example.' in path.name:
        parser.error('Example files cannot be synchronized.')
    try:
        print(sync(args.direction, args.name, path, args.repo,
                   args.environment, args.apply, args.overwrite))
    except json.JSONDecodeError:
        parser.exit(1, 'GitHub CLI returned an invalid response. No values were logged.\n')
    except ValueError as error:
        parser.exit(1, f'{error}\n')
    except OSError:
        parser.exit(1, 'Cannot read or write the selected config file; check file access.\n')


if __name__ == '__main__':
    main()
