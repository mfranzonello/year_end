"""Upload the minimal hosted OneDrive credentials to Azure Key Vault safely."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import tomllib


CLOUD_SECRET_NAME = "year-end-cloud-secrets"
TOKEN_SECRET_NAME = "onedrive-oauth-token"


def _find_azure_cli() -> str | None:
    """Return Azure CLI from PATH or its standard Windows installation."""
    azure_cli = shutil.which("az")
    if azure_cli:
        return azure_cli
    standard_windows_path = Path(
        "C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd"
    )
    return str(standard_windows_path) if standard_windows_path.is_file() else None


def _required_value(config: dict, section: tuple[str, ...], key: str) -> object:
    current = config
    for part in section:
        current = current.get(part, {})
        if not isinstance(current, dict):
            current = {}
            break
    value = current.get(key)
    if value is None or str(value).strip() == "":
        location = ".".join((*section, key))
        raise ValueError(f"Local secrets are missing {location}")
    return value


def build_cloud_secrets(local_secrets: dict) -> str:
    """Return TOML containing only credentials required by cloud inspection."""
    microsoft = {
        key: _required_value(local_secrets, ("microsoft", "desktop"), key)
        for key in ("client_id", "client_secret")
    }
    postgresql = {
        key: _required_value(local_secrets, ("postgresql",), key)
        for key in ("host", "port", "database", "user", "password")
    }
    lines = ["[microsoft]", "", "[microsoft.desktop]"]
    lines.extend(f"{key} = {json.dumps(str(value))}" for key, value in microsoft.items())
    lines.extend(["", "[postgresql]"])
    lines.extend(f"{key} = {json.dumps(str(value))}" for key, value in postgresql.items())
    return "\n".join(lines) + "\n"


def _run_azure(arguments: list[str]) -> None:
    subprocess.run(arguments, check=True)


def bootstrap(
    vault_name: str,
    secrets_file: Path,
    token_file: Path,
    subscription: str | None = None,
    apply: bool = False,
) -> None:
    """Validate local inputs and optionally upload the two hosted secrets."""
    azure_cli = _find_azure_cli()
    if azure_cli is None:
        raise RuntimeError("Azure CLI is not installed or is not available on PATH")
    if not secrets_file.is_file():
        raise FileNotFoundError(f"Local secrets file does not exist: {secrets_file}")
    if not token_file.is_file():
        raise FileNotFoundError(f"OneDrive token file does not exist: {token_file}")

    with secrets_file.open("rb") as source:
        cloud_secrets = build_cloud_secrets(tomllib.load(source))
    with token_file.open(encoding="utf-8") as source:
        token = json.load(source)
    if not token.get("refresh_token"):
        raise ValueError("The OneDrive token cache does not contain a refresh token")

    _run_azure([azure_cli, "account", "show", "--output", "none"])
    if subscription:
        _run_azure([azure_cli, "account", "set", "--subscription", subscription])
    _run_azure([
        azure_cli, "keyvault", "show", "--name", vault_name, "--output", "none",
    ])

    if not apply:
        print(
            f"Dry run: validated {vault_name!r}; would upload "
            f"{CLOUD_SECRET_NAME!r} and {TOKEN_SECRET_NAME!r}."
        )
        return

    with TemporaryDirectory(prefix="year-end-key-vault-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        cloud_path = temporary_path / "cloud-secrets.toml"
        token_path = temporary_path / "onedrive-token.json"
        cloud_path.write_text(cloud_secrets, encoding="utf-8")
        token_path.write_text(json.dumps(token), encoding="utf-8")
        for name, source_path in (
            (CLOUD_SECRET_NAME, cloud_path),
            (TOKEN_SECRET_NAME, token_path),
        ):
            _run_azure([
                azure_cli, "keyvault", "secret", "set",
                "--vault-name", vault_name,
                "--name", name,
                "--file", str(source_path),
                "--encoding", "utf-8",
                "--output", "none",
            ])
    print(f"Uploaded the hosted OneDrive credentials to {vault_name!r}.")


def main() -> None:
    """Parse bootstrap arguments and perform a dry run or explicit upload."""
    parser = argparse.ArgumentParser(
        description="Upload minimal OneDrive cloud-runner credentials to Key Vault.",
    )
    parser.add_argument("--vault-name", required=True)
    parser.add_argument("--subscription")
    parser.add_argument(
        "--secrets-file", type=Path, default=Path(".secrets/secrets.toml"),
    )
    parser.add_argument(
        "--token-file", type=Path,
        default=Path(".secrets/auths/tokens/azure/token.json"),
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Upload the validated credentials; defaults to a dry run.",
    )
    arguments = parser.parse_args()
    bootstrap(
        arguments.vault_name,
        arguments.secrets_file,
        arguments.token_file,
        subscription=arguments.subscription,
        apply=arguments.apply,
    )


if __name__ == "__main__":
    main()
