"""Authorize the Gmail send-only scope without sending a message."""

import argparse

from integrations.gmail.auth import GoogleAuthError, get_access_token


def main() -> None:
    parser = argparse.ArgumentParser(description="Authorize Gmail send access without sending email.")
    parser.add_argument("--login", action="store_true", help="Ignore cached Gmail credentials and show consent again.")
    args = parser.parse_args()
    try:
        get_access_token(force_login=args.login)
    except GoogleAuthError as error:
        raise SystemExit(f"Gmail authorization failed: {error}") from error
    print("Gmail send authorization is cached. No message was sent.")


if __name__ == "__main__":
    main()
