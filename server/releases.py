"""One definition of feature albums for browsing, popularity and acquisition."""

SECONDARY = (
    "compilation",
    "live",
    "remix",
    "demo",
    "soundtrack",
    "spokenword",
    "interview",
    "audiobook",
    "mixtape/street",
)


def feature_album(group):
    return group.get("primary-type", "").casefold() == "album" and not (
        {t.casefold() for t in group.get("secondary-types", [])} & set(SECONDARY)
    )


def release_query(artist_id, kind):
    feature = "primarytype:album" + "".join(
        " AND NOT secondarytype:" + ('"' + t + '"' if "/" in t else t)
        for t in SECONDARY
    )
    if kind == "album":
        expression = feature
    elif kind in {"single", "ep"}:
        expression = "primarytype:" + kind
    else:
        expression = (
            "NOT primarytype:single AND NOT primarytype:ep AND NOT (" + feature + ")"
        )
    return "arid:" + artist_id + " AND " + expression
