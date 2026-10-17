"""Small adapter for the extracted Music Grabber HTML source parsers.

PigMusic applies its own strict match and quality gates after search.
"""
TIMEOUT_FREEMP3CLOUD_SEARCH = 20
TIMEOUT_FREEMP3CLOUD_DOWNLOAD = 120
TIMEOUT_ZVU4NO_SEARCH = 15
TIMEOUT_ZVU4NO_DOWNLOAD = 120
TIMEOUT_JIOSAAVN_SEARCH = 20
TIMEOUT_JIOSAAVN_DOWNLOAD = 120


def parse_duration(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02}"


def score_search_result_with_breakdown(title, artist, query, **kwargs):
    return 0, ["PigMusic validates identity and quality after search"]
