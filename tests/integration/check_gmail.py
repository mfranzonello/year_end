"""Authorize Gmail compose access without creating or sending a message."""

import argparse

from integrations.google.auth import GoogleAuthError, get_access_token


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Authorize Gmail compose access without changing the mailbox."
    )
    parser.add_argument("--login", action="store_true", help="Ignore cached Gmail credentials and show consent again.")
    args = parser.parse_args()
    try:
        get_access_token("gmail", force_login=args.login)
    except GoogleAuthError as error:
        raise SystemExit(f"Gmail authorization failed: {error}") from error
    print("Gmail compose authorization is cached. No draft or message was created.")


if __name__ == "__main__":
    main()
