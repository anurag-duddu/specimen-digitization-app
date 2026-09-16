# Brand assets

The mark is the pin: a vertical stroke with a filled circular head, standing in
a disc. The specification is
[`design/09-brand-direction.md`](../../design/09-brand-direction.md) section 9.

Everything in this directory is generated from one geometry, stated once at the
24 dp mark and scaled from there. Nothing here is loaded at runtime, so there is
no `assets:` entry for it in `pubspec.yaml`; these are the inputs the two
platform generators read, plus the reference renderings.

## The vector source

`pin.svg` is the source of truth for anyone working outside Flutter. It carries
the derivation of the two coordinates that are not printed in 09: the head's
centre at y 5.5 and the shaft's end at y 18, both of which fall out of the
1 dp optical rise.

Two other files draw the same geometry and have to move with it:
`../../tool/brand/render_mark.py` for the rasters and
`../../packages/specimen_ui/lib/src/foundation/mark.dart` for `UiMark`.

## The files

| File | What it is |
|---|---|
| `pin.svg` | The mark at 24 dp. The vector source. |
| `mark-1024.png` | The mark as it appears in the product: accent disc, pin, on `ground` light. Opaque. The reference rendering. |
| `mark-mono-1024.png` | The monochrome variant: `paper` disc, `ink` pin, on `ground` light. Opaque. Its pair. |
| `splash-mark-1024.png` | The same disc with its square cut away, so the splash composites it on `ground` in light and on `ground` dark in dark. |
| `splash-mark-android12-1024.png` | The same again at two thirds of the size, for Android 12 and later. That platform clips the splash icon to a circle and masks a third of the foreground away, and the mark's head reaches three quarters of the disc's radius, so the full bleed disc comes back with a flattened head. |
| `icon-1024.png` | The app icon: an accent superellipse at exponent 5 with the pin at 44 percent of the height, corners in `ground` light. Opaque, because iOS rejects an icon with an alpha channel. iOS and the legacy Android launcher. |
| `icon-foreground-1024.png` | The Android adaptive foreground: the pin alone, on nothing. Sized against the safe zone, which is the central 66 percent of the canvas a launcher mask shows. |
| `icon-maskable-1024.png` | The web maskable icon: accent to every edge, pin sized against the central 80 percent a maskable mask guarantees. |

The pin is always 44 percent of the icon a mask shows, never 44 percent of the
source canvas. That is what makes the masked Android icon, the masked maskable
icon and the iOS icon carry a pin of the same optical size.

## Regenerating

From `apps/specimen_digitization`:

```bash
uv run --with pillow python tool/brand/render_mark.py
dart run flutter_launcher_icons
dart run flutter_native_splash:create
uv run --with pillow python tool/brand/render_mark.py --only web
```

The last line is not a mistake. `flutter_launcher_icons` resizes one source
into all four web files, which leaves a 16 px favicon and two maskable icons
with `ground` in their corners, so the renderer runs again afterwards and
replaces `web/favicon.png`, `web/icons/apple-touch-icon-180.png` and the two
`web/icons/Icon-maskable-*.png`. `--only sources` renders the other half on its
own.

Every run also checks that `flutter_launcher_icons.yaml`,
`flutter_native_splash.yaml`, `web/index.html` and `web/manifest.json` still
carry the palette, and exits non zero naming anything that drifted.

Two generated files are one hook away from what the generators write: the
repository's `trailing-whitespace` hook strips a trailing space from a comment
line in `android/app/src/main/res/values-v31/styles.xml` and its night
counterpart. Re-running the generator reintroduces it and the hook removes it
again.

## Drawing

Rasters are drawn at four times the output side and resolved with a Lanczos
filter, which is where the anti-aliasing comes from: Pillow draws hard edged
polygons. Colour and coverage are separate channels, resolved separately, so a
disc on transparency keeps its edge instead of the dark halo an
un-premultiplied RGBA resize leaves behind.
