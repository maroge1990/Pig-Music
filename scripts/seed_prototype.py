"""Import an Apple XML inventory into local review state; queues nothing."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.store import Store

parser = argparse.ArgumentParser()
parser.add_argument("--xml", type=Path, required=True)
parser.add_argument("--data", type=Path, default=Path(".localdata"))
args = parser.parse_args()
store = Store(args.data)
review = store.import_apple(args.xml.read_bytes())
print(
    json.dumps(
        {
            "source": review["source_name"],
            "migration": review["stats"],
            "library": store.library["stats"],
            "downloads_enabled": False,
        }
    )
)
