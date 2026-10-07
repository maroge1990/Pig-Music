"""Repository checkout for source-level checks.

The image under test contains only runtime files; CI mounts the checkout
read-only at PIG_MUSIC_SOURCE. Locally the tests run from the checkout itself.
"""

import os
from pathlib import Path

SOURCE = Path(os.environ.get("PIG_MUSIC_SOURCE") or Path(__file__).resolve().parents[1])
