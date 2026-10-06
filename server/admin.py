"""Local interactive owner bootstrap/recovery; never accepts a password argument."""

import argparse
from getpass import getpass
import os
from pathlib import Path
import sys

from .auth import Auth, AuthError
from .store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create-owner", "reset-password"])
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.exit(1, "Use an interactive terminal; no piped passwords.\n")
    password = getpass("Password (12–256 characters): ")
    if password != getpass("Repeat password: "):
        parser.exit(1, "Passwords do not match.\n")
    auth = Auth(Store(Path(os.environ.get("PIG_MUSIC_DATA", "/data"))))
    try:
        if args.command == "create-owner":
            auth.create_owner(args.username, password)
        else:
            auth.reset_password(args.username, password)
    except AuthError as exc:
        parser.exit(1, exc.code + "\n")
    print("Account updated. No credentials printed or logged.")


if __name__ == "__main__":
    main()
