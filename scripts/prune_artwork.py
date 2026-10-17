"""Prune old unreferenced hash covers and expired metadata in appdata only."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    args = parser.parse_args()
    if not (args.data / "pig-music.sqlite3").is_file():
        parser.error("Use an existing PigMusic appdata directory")
    # Stop the service before CLI maintenance; the in-process weekly task uses
    # the same Store and locks as its scanner.
    print(json.dumps(Store(args.data).prune_artwork()))


if __name__ == "__main__":
    main()
