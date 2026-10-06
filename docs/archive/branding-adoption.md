> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Pig Music branding adoption

Applied 5 October 2026 from the approved Pig family standard 1.0 in `C:\Users\markr\GitHub\Pig-Branding`. Draft studies and rejected rays were excluded.

- The original custom SVG pig is replaced with the supplied transparent 256 px pig, unchanged. Its optical anchor is positioned at 49.9694% across and 40.5360% down.
- The existing dark interface uses the approved canvas, surface, raised, text, secondary, accent, on-accent, hover, border, control-border and status roles. Semantic CSS variables replace the previous coral and grey palette.
- Persistent selection uses accent at 14% over surface with an inset bar; keyboard focus retains a separate outer ring. Application selection uses no ticks. Saved/completed status checks remain.
- Control edges use the control-border role. Actions use capsule shapes, compact controls use 6 px corners and cards use 10 px corners. The existing responsive layout and reduced-motion handling are retained.
- Real album artwork remains unchanged. Missing artwork uses neutral family surfaces rather than arbitrary generated hues.
- The shared pig is also used as the browser icon. No font file or third-party font service is introduced.

Reference copies are [family standard](../pig-family-brand-standard.md) and [exact tokens](../pig-family-brand-tokens.json). Copied standard references to other assets/documents refer to the source branding repository.

## Asset gap

The pack supplies PigTV wordmarks, but no Pig Music wordmark. Until a dedicated product wordmark is supplied, the sidebar uses the shared pig beside a plain system-font product label. This label is not a claim to reproduce the approved Arial Rounded MT Bold wordmark. The authoring font is intentionally absent from the asset pack and is not needed to consume supplied artwork.

## Validation

TypeScript checking and the production frontend build passed. Browser inspection confirmed the shared logo loads, dark canvas resolves to #15111A, dark accent resolves to #EF7AAE and selected tabs use the 14% composite. Desktop and 390 × 844 phone layouts were reviewed; phone browsing showed no horizontal overflow. Existing migration selections were preserved. The subsequent queue milestone adds the approved light palette, system-default appearance and device-local overrides; see [validation](queue-milestone.md). Native app icon exports remain separate work.
