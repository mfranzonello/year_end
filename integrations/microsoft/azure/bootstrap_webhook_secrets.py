"""Create the Key Vault secrets required by the drive webhook host."""

import argparse
from pathlib import Path
from secrets import token_urlsafe
import subprocess
from tempfile import TemporaryDirectory

from integrations.microsoft.azure.bootstrap_key_vault import (
    _find_azure_cli, _run_azure,
)


GITHUB_PRIVATE_KEY_SECRET_NAME = "github-actions-dispatch-private-key"
ONEDRIVE_CLIENT_STATE_SECRET_NAME = "onedrive-webhook-client-state"
GOOGLE_DRIVE_CHANNEL_TOKEN_SECRET_NAME = "google-drive-channel-token"


def _validate_private_key(private_key: str) -> None:
    """Reject empty or visibly non-PEM GitHub App private keys."""
    stripped = private_key.strip()
    if not stripped.startswith("-----BEGIN ") or not stripped.endswith(
        " PRIVATE KEY-----"
    ):
        raise ValueError("GitHub App private key must be a PEM private key")


def _secret_exists(azure_cli: str, vault_name: str, secret_name: str) -> bool:
    result = subprocess.run(
        [
            azure_cli, "keyvault", "secret", "show",
            "--vault-name", vault_name,
            "--name", secret_name,
            "--query", "id",
            "--output", "none",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def bootstrap_webhook_secrets(
    vault_name: str,
    github_private_key_file: Path,
    *,
    subscription: str | None = None,
    apply: bool = False,
    replace_verification_secrets: bool = False,
) -> None:
    """Validate and optionally create webhook-host secrets without logging values."""
    azure_cli = _find_azure_cli()
    if azure_cli is None:
        raise RuntimeError("Azure CLI is not installed or is not available on PATH")
    if not github_private_key_file.is_file():
        raise FileNotFoundError(
            f"GitHub App private key does not exist: {github_private_key_file}"
        )
    private_key = github_private_key_file.read_text(encoding="utf-8")
    _validate_private_key(private_key)

    _run_azure([azure_cli, "account", "show", "--output", "none"])
    if subscription:
        _run_azure([azure_cli, "account", "set", "--subscription", subscription])
    _run_azure([
        azure_cli, "keyvault", "show", "--name", vault_name, "--output", "none",
    ])

    if not apply:
        print(
            f"Dry run: validated {vault_name!r} and the GitHub App private key; "
            "no secret values were created or changed."
        )
        return

    verification_names = (
        ONEDRIVE_CLIENT_STATE_SECRET_NAME,
        GOOGLE_DRIVE_CHANNEL_TOKEN_SECRET_NAME,
    )
    with TemporaryDirectory(prefix="year-end-webhook-secrets-") as temporary:
        temporary_path = Path(temporary)
        key_path = temporary_path / "github-app-private-key.pem"
        key_path.write_text(private_key, encoding="utf-8")
        _run_azure([
            azure_cli, "keyvault", "secret", "set",
            "--vault-name", vault_name,
            "--name", GITHUB_PRIVATE_KEY_SECRET_NAME,
            "--file", str(key_path),
            "--encoding", "utf-8",
            "--output", "none",
        ])

        created_verification_secrets = []
        preserved_verification_secrets = []
        for secret_name in verification_names:
            if (
                not replace_verification_secrets
                and _secret_exists(azure_cli, vault_name, secret_name)
            ):
                preserved_verification_secrets.append(secret_name)
                continue
            secret_path = temporary_path / f"{secret_name}.txt"
            secret_path.write_text(token_urlsafe(48), encoding="utf-8")
            _run_azure([
                azure_cli, "keyvault", "secret", "set",
                "--vault-name", vault_name,
                "--name", secret_name,
                "--file", str(secret_path),
                "--encoding", "utf-8",
                "--output", "none",
            ])
            created_verification_secrets.append(secret_name)

    print(
        f"Stored {GITHUB_PRIVATE_KEY_SECRET_NAME!r}; created or replaced "
        f"{len(created_verification_secrets)} verification secrets and preserved "
        f"{len(preserved_verification_secrets)} existing verification secrets."
    )


def main() -> None:
    """Parse command-line arguments and bootstrap webhook secrets."""
    parser = argparse.ArgumentParser(
        description="Safely create Key Vault secrets for drive webhooks.",
    )
    parser.add_argument("--vault-name", required=True)
    parser.add_argument("--github-private-key-file", required=True, type=Path)
    parser.add_argument("--subscription")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--replace-verification-secrets",
        action="store_true",
        help=(
            "Rotate the OneDrive/Google verification values; existing provider "
            "subscriptions must then be replaced."
        ),
    )
    arguments = parser.parse_args()
    bootstrap_webhook_secrets(
        arguments.vault_name,
        arguments.github_private_key_file,
        subscription=arguments.subscription,
        apply=arguments.apply,
        replace_verification_secrets=arguments.replace_verification_secrets,
    )


if __name__ == "__main__":
    main()
