"""Generate deterministic web/Swift roles from the approved branding source."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def kebab(value):
    return re.sub(r"([A-Z])", r"-\1", value).lower()


def outputs():
    tokens = json.loads((ROOT / "docs/pig-family-brand-tokens.json").read_text())
    css = [f"/* Generated from Pig family {tokens['version']}; do not edit. */"]
    for theme in ("light", "dark"):
        selector = (
            ':root,\n:root[data-theme="light"]'
            if theme == "light"
            else ':root[data-theme="dark"]'
        )
        css += [selector + " {", f"  color-scheme: {theme};"]
        css += [
            f"  --{kebab(key)}: {value.lower()};"
            for key, value in tokens[theme].items()
        ]
        css += ["}"]
    css += [":root {"]
    for name, value in tokens["radii"]["web"].items():
        css += [f"  --radius-{name}: {value / 16:g}rem;"]
    css += ["  --radius-hero: 1.375rem;", "  --radius-capsule: 999px;"]
    for size in tokens["spacing"]:
        css += [f"  --space-{size}: {size / 16:g}rem;"]
    for name, size in [("caption", 12), ("body", 16), ("title", 24), ("heading", 32)]:
        css += [f"  --type-{name}: {size / 16:g}rem;"]
    css += [
        "  --selected-fill: color-mix(in srgb, var(--accent) 14%, var(--surface));",
        "  --success-fill: color-mix(in srgb, var(--success) 14%, var(--surface));",
        "  --warning-fill: color-mix(in srgb, var(--warning) 14%, var(--surface));",
        "  --danger-fill: color-mix(in srgb, var(--danger) 14%, var(--surface));",
        f"  --media-secondary: {tokens['dark']['secondary'].lower()};",
        f"  --media-control-border: {tokens['dark']['controlBorder'].lower()};",
        f"  --media-border: {tokens['dark']['border'].lower()};",
        "}",
    ]
    swift = [
        f"// Generated from Pig family {tokens['version']}; do not edit.",
        "import SwiftUI",
        "",
        "public enum PigBrand {",
    ]
    # Both platforms resolve appearance in their views, with no UIKit dependency on Watch.
    for key in tokens["light"]:
        swift += [f"    public static func {key}(_ scheme: ColorScheme) -> Color {{"]
        rgb = []
        for theme in ("light", "dark"):
            h = tokens[theme][key].lstrip("#")
            rgb.append(
                ", ".join(
                    f"{name}: {int(h[i:i+2],16) / 255:.8f}"
                    for name, i in [("red", 0), ("green", 2), ("blue", 4)]
                )
            )
        swift += [
            f"        scheme == .dark ? Color({rgb[1]}) : Color({rgb[0]})",
            "    }",
        ]
    swift += ["}"]
    return {
        ROOT / "client/src/tokens.css": "\n".join(css) + "\n",
        ROOT / "swift/PigKit/Sources/PigBrand/Tokens.swift": "\n".join(swift) + "\n",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in outputs().items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    if stale:
        parser.exit(1, "Stale brand output: " + ", ".join(stale) + "\n")


if __name__ == "__main__":
    main()
