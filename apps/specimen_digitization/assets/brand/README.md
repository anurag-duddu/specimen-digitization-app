# Brand assets

The owner's selected [primary mark](../../design/brand-reference/owner-primary-mark.png)
and [Paper app icon](../../design/brand-reference/owner-app-icon.png) are the visual
authority. Their provenance is retained in
[brand-reference/README.md](../../design/brand-reference/README.md).
The mark has three interlocking ribbons, an open aperture in the front ribbon,
and a shaded Iris, Amber and Obsidian fold. The primary mark darkens toward
the upper end; the app icon returns to Amber at that end. Both named gradients
are retained in the canonical vector. The former pin is retired. Interface icons
remain Phosphor.

`specimen-mark.svg` is the canonical vector. Both the platform raster renderer
and `tool/brand/generate_flutter_mark.py` consume this source. Flutter renders
its generated `MarkGeometry`; the Python raster pipeline does not duplicate the
paths. The SVG colours are checked against the exact `BrandPalette` values in
`packages/specimen_ui/lib/src/foundation/palette.dart`.

These files are generator inputs and reference renders, so they do not require
an application `assets:` entry in `pubspec.yaml`.

## Files and platform treatment

| File | Purpose |
|---|---|
| `specimen-mark.svg` | Canonical 512 square vector, traced from the retained owner reference. |
| `mark-1024.png` | Primary mark on opaque Paper. |
| `mark-mono-1024.png` | The same three paths and aperture, all Obsidian on Paper. |
| `icon-1024.png` | App-icon mark on opaque Paper for iOS and legacy Android launchers. The platform supplies its rounded mask. |
| `icon-foreground-1024.png` | Transparent full-colour mark in the central 66 percent frame for an Android adaptive icon, over its configured Paper background. |
| `icon-maskable-1024.png` | Paper to every edge with the mark in the central 80 percent frame for web masks. |
| `splash-mark-1024.png` | The owner's Paper rounded tile with transparent corners, keeping the Obsidian ribbons visible on both Paper and Obsidian launch backgrounds. |
| `splash-mark-android12-1024.png` | Transparent mark in the central two-thirds frame, entirely inside the Android 12 safe circle. Android supplies a Paper icon background in both themes. |

The SVG already contains the owner's visual margins. The adaptive and maskable
frames scale the complete vector, using its `fold-app-icon` gradient and
preserving the same relative foreground size when each platform applies its
mask. Opaque launcher sources do not pre-cut corners: doing so would compound
platform masks and give iOS an alpha channel.
The 64 px browser favicon uses the rounded Paper tile to remain visible on dark
browser surfaces.

## Regenerating

From `apps/specimen_digitization`:

```bash
python3 tool/brand/generate_flutter_mark.py
dart format packages/specimen_ui/lib/src/foundation/mark_geometry.dart
uv run --with resvg-py==0.5.0 --with pillow==11.3.0 python tool/brand/render_mark.py
dart run flutter_launcher_icons
dart run flutter_native_splash:create
uv run --with resvg-py==0.5.0 --with pillow==11.3.0 python tool/brand/render_mark.py --only web
```

The final pass restores the 64 px favicon, Apple touch icon, and the safe-area
web maskable icons after the launcher generator resizes its single input.
`--only sources` updates just the seven source rasters. The renderer checks the
vector, native YAML, HTML and web manifest against the Flutter palette before
writing anything. It never generates a new design or uses a raster photograph
as the launcher source.

`resvg-py` 0.5.0 renders the source at four times the requested output size. Pillow
11.3.0 composes the Paper plate, then resolves colour and alpha together using
premultiplied Lanczos resampling. Both rendering tools are pinned in the command;
no Flutter application dependency is added. The generated PNGs contain no
timestamps or other varying metadata.

Run the asset and mark regression checks after generation:

```bash
flutter test test/theme/brand_assets_test.dart
cd packages/specimen_ui
flutter test test/foundation/brand_test.dart test/foundation/mark_test.dart
```

The asset test checks every active source, Android, iOS and web PNG for Obsidian
and the approved fold gradient, and retains the rejected yellow-green hue guard.
It checks the actual ribbon silhouette, aperture and separation gaps at useful
raster resolutions, opaque Paper launcher backgrounds, transparent foreground
safe circles, source palette consistency and the absence of the retired vector.
The Flutter mark test checks the same canonical geometry and its mono variant.
Historical screenshots and golden baselines are outside the generated-asset scan.

**Generator caveat:** `flutter_launcher_icons` 0.14.4 can rewrite
`ASSETCATALOG_COMPILER_GENERATE_SWIFT_ASSET_SYMBOL_EXTENSIONS` from its boolean
value to `AppIcon`. Restore each original `YES` or `NO` value after generation;
the regression test rejects a nonboolean. Preserve application identifiers,
unrelated `Info.plist` formatting, web-manifest `purpose: any` entries, and final
newlines. Strip generated Android XML trailing whitespace before the whitespace
check. Generator side effects do not authorize bundle identity changes.
