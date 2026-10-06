# Integrating the Pig family system 1.4.0

Use the assets for the product, not the generic family pig as a replacement app icon. Wordmarks retain Arial Rounded MT Bold as outlined paths; generated concept captions are superseded.

## Web and desktop

Map `tokens/pig-family.css` into the existing component system. Resolve and persist System/Light/Dark preference in the application. Use product SVGs with intrinsic proportions and meaningful alt text only when the name is not already adjacent. Preserve labels, targets, keyboard order and at least 6 px of painting space around focus rings, including scroll containers. Set actual manifest URLs and scope. ICO, PNG and ICNS files are supplied.

## Apple and Apple TV

Import required dynamic colours from `tokens/PigColors.xcassets`, checking for duplicate names. Product `Apple/AppIcon.appiconset` includes light/dark square sources. Product `Apple/layers` contains foreground/background sources for the target icon workflow; do not bake an outer rounded mask into artwork. Review system-generated clear/tinted appearances in the target tools.

For TV use the product's `AppleTV/lockup-*` icon-and-name layout. Each `AppleTV/light` or `AppleTV/dark` folder has a complete layered catalog; choose one, not both, since asset names are shared. Keep icon and name on one front layer. Top Shelf and welcome exports are included. Preserve app-specific dynamic Top Shelf behaviour. Verify cropping and focus/parallax on hardware before release.

No app integration or deployment is performed by generating this kit.

## Regeneration

1. If names change, regenerate outlined wordmarks with `tools/make-wordmarks.swift` on macOS with Arial Rounded MT Bold available.
2. Run `tools/final-icon-masters.py`, then `tools/render-final-assets.cjs`.
3. Run `tools/finish-platform-assets.py`.
4. Run `tools/build-family-guide.py` and inspect the rendered PDF.
5. Run `tools/check-preview.cjs`, then `tools/package-family.py`.

Python needs Pillow, ReportLab and pypdf; the renderer uses Playwright and Edge. Local runtime paths in these authoring scripts may need adapting on another workstation. Consumers need no authoring dependencies or installed wordmark font. Do not distribute the font binary.
