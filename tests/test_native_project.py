"""The native project generator and the committed Xcode project must agree on
the iPhone app's Info.plist contents, so regenerating never drops a key."""

import plistlib
import re
from pathlib import Path

from scripts.generate_native_project import IPHONE_INFO

ROOT = Path(__file__).resolve().parents[1]


def test_local_network_description_survives_regeneration():
    project = (ROOT / "swift/PigMusic.xcodeproj/project.pbxproj").read_text()
    info = plistlib.loads((ROOT / "swift/PigMusic/Info.plist").read_bytes())
    key = "INFOPLIST_KEY_NSLocalNetworkUsageDescription"
    assert IPHONE_INFO[key]
    # Debug and Release of the iPhone target carry the generator's value.
    found = re.findall(re.escape(key) + r' = "([^"]*)";', project)
    assert found == [IPHONE_INFO[key]] * 2
    # One source only: the hand-written Info.plist does not repeat it.
    assert "NSLocalNetworkUsageDescription" not in info
    assert info["UIBackgroundModes"] == ["audio"]
