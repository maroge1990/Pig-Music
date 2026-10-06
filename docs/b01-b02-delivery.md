# Approved branding integration — 7 October 2026

B01/B02 use the approved Pig family 1.4.0 product exports from Pig-Branding. Source assets were checksum-checked against its manifest; `brand-asset-provenance.json` records exact inputs. The approved raster artwork and outlined wordmarks are unchanged. No font binary is distributed. The product mark has its own supplied optical placement; the old generic-pig anchor is removed.

Implemented:
- Exact light/dark horizontal lockup, mobile PigMusic mark, appearance-aware favicons, 180px Apple touch icon and scoped web manifest. Production routes serve assets and the manifest with correct MIME types; missing/traversal paths return 404.
- Deterministic approved tokens generate web CSS and Swift PigBrand colour roles. `scripts/generate_brand_tokens.py --check` and CI catch stale output. Swift PigKit compiles with strict Swift 6.
- Every CSS font-size uses rem with a minimum 0.75rem. Standard spacing/radii use generated tokens. Off-scale spacing is retained where needed to preserve density; no wholesale layout rewrite. Old colour aliases and duplicate legacy brand rules are removed.
- The protected dark player uses approved dark secondary/control-border/border roles instead of the three unapproved shades. Rose remains the control accent. Missing covers use an accent/raised placeholder; empty states use the exact product pig. Saved catalogue actions use a server cloud rather than a selection-like tick, and redundant album-card status ticks are removed.

Verification: 129 backend tests passed (127 baseline + brand drift/production route gates); three frontend tests, TypeScript/production build, formatting and token drift passed. PigBrand Swift package compiled. Browser checks at 375×812 and 1280×900 showed light/dark assets loading; 375px document width exactly matched viewport width, tabs stayed on one row and sort moved underneath. Screenshot evidence is in the chat workspace `outputs/branding-20261007`.

Not yet proven: physical iPhone Add to Home Screen icon/masking and Dynamic Type/VoiceOver, Watch icon appearances, and production deployment of this branding change. Apple icon source catalog is staged in `swift/BrandAssets`; the feasibility spike intentionally remains disposable and is not relabelled as the production app. Native playback/account/offline and physical signing gates remain tracked separately.

Artwork dominant-colour metadata and broader component/router extraction remain separate findings. Optional per-artwork player tint is not introduced: the final approved palette does not itself approve arbitrary artwork-derived UI colours.
