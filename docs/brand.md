# Brand

Pig family **1.7.0**. The canonical source is the Pig-Branding repository: `tokens/brand-tokens.json`, `docs/pig-family-brand-guide.md`, `docs/integration.md` and `assets/products/pig-music`. Pig Music vendors copies, so builds and CI don't need a sibling checkout. Brand questions go to that repository's guide; this file covers only how Pig Music consumes the brand.

## Files and commands

| File | Role |
| --- | --- |
| `docs/pig-family-brand-tokens.json` | Canonical tokens; the Dockerfile copies it into the image |
| `client/src/tokens.css`, `swift/PigKit/Sources/PigBrand/Tokens.swift` | Generated from the tokens; don't edit by hand |
| `docs/brand-asset-provenance.json`, `docs/native-brand-assets.json` | Source paths and SHA-256 checksums of imported artwork |

```sh
.venv/bin/python scripts/sync_native_brand.py --source /path/to/Pig-Branding   # refresh imports; a new version needs review
.venv/bin/python scripts/sync_native_brand.py --check                         # verify provenance (CI)
.venv/bin/python scripts/generate_brand_tokens.py --check                     # verify generated roles (CI)
```

Don't move the JSON files: the Dockerfile, `.dockerignore`, both scripts and `tests/test_brand_delivery.py` read them at these paths.

## Rules to keep

- **Artwork:** Use the approved Pig Music product assets. Never redraw, recolour, change the aspect ratio or flatten transparency. Centre the pig on its optical anchor, not on its bounding box.
- **New names:** A new wordmark or product name needs approved artwork. Don't reuse PigTV lettering.
- **Type:** Interface text uses system type (Dynamic Type on Apple platforms). The wordmark font is never shipped.
- **Playback:** Keep protected surfaces and the fixed rose accent in both appearances.
- **Native presentation:** Decorative bloom disappears with Reduce Transparency and is static with Reduce Motion. Content stays on opaque surfaces. Native pickers, toggles and system bars keep platform semantics.
- **Icons:** The iOS icon is an Icon Composer document (default, dark and mono). The Watch uses the approved dark square export with the system mask.
