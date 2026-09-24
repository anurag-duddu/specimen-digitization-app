# Design system: Specimen Digitization

> **Partly superseded on 2026-09-16.** Sections 2 (brand direction), 3 (colour), 4 (typography), 5.3 (shape), 6 (iconography), 7 (atomic inventory) and 8 (Flutter implementation plan) are replaced by [09-brand-direction.md](09-brand-direction.md) and [10-component-library.md](10-component-library.md). They remain here as the record of the v1 rebuild that shipped to `main`. Sections 1, 5.1, 5.2, 5.4 to 5.9 and 9 still apply, read together with 09 section 12. [11-fit-and-scale.md](11-fit-and-scale.md) and [13-screen-composition.md](13-screen-composition.md) sit on top of 09 and 10 and win over both: 11 owns text scale, window classes and what a control does with less room than it needs, and 13 owns how a screen is composed from the controls.


Owner: design systems. Applies to every widget in `apps/specimen_digitization/lib/`.

Every contrast ratio in this document was computed from the hex values printed here using the
WCAG relative-luminance formula, not estimated. Every color role name matches Material 3.

## Sources read for this document

| Source | URL |
|---|---|
| M3 color roles (26 roles, six groups, pairing rules) | <https://m3.material.io/styles/color/roles> |
| M3 type scale and tokens (Major Second, base 14, language height) | <https://m3.material.io/styles/typography/type-scale-tokens> |
| M3 shape principles | <https://m3.material.io/styles/shape/overview-principles> |
| M3 corner radius scale and optical roundness | <https://m3.material.io/styles/shape/corner-radius-scale> |
| M3 elevation (tonal surfaces over shadows) | <https://m3.material.io/styles/elevation/overview> |
| Flutter `ColorScheme.fromSeed` (47 overrides, contrast caveat) | <https://api.flutter.dev/flutter/material/ColorScheme/ColorScheme.fromSeed.html> |
| Flutter `ThemeExtension` | <https://api.flutter.dev/flutter/material/ThemeExtension-class.html> |
| Flutter `TextTheme` | <https://api.flutter.dev/flutter/material/TextTheme-class.html> |
| Flutter theming cookbook | <https://docs.flutter.dev/cookbook/design/themes> |
| WCAG 2.2 SC 1.4.3 Contrast (Minimum) | <https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html> |
| WCAG 2.2 SC 1.4.11 Non-text Contrast | <https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html> |
| Atomic design, chapter 2 | <https://atomicdesign.bradfrost.com/chapter-2/> |
| Material Symbols variable axes | <https://developers.google.com/fonts/docs/material_symbols> |
| `material_symbols_icons` package | <https://pub.dev/packages/material_symbols_icons> |
| `google_fonts` package | <https://pub.dev/packages/google_fonts> |
| JetBrains Mono design notes | <https://www.jetbrains.com/lp/mono/> |
| IBM Plex family | <https://www.ibm.com/plex/> |
| Field Museum public site | <https://www.fieldmuseum.org/> |
| iDigBio specimen portal | <https://portal.idigbio.org/portal/search> |
| DigiVol volunteer transcription portal | <https://volunteer.ala.org.au/> |
| Zooniverse, Notes from Nature: Capturing California's Flowers | <https://www.zooniverse.org/projects/md68135/notes-from-nature-capturing-californias-flowers> |
| Linear method | <https://linear.app/method/introduction> |

`https://www.gbif.org/occurrence/search` was attempted and returned a bot-verification interstitial,
so it is not cited. Nothing in this document is drawn from it.

### What the references taught us

**iDigBio specimen portal.** Two lessons. First, the filter panel exposes presence as a first-class
axis: each field carries `Present` / `Missing` / `Fuzzy` toggles under a "Data Flags" group, so a
user can search for absence. Absence is data, not an empty cell. Second, the results table prints
the literal string `no data` in the Date Collected column rather than leaving it blank, and the
column set is user-configurable. Our `FieldRow` and queue table follow both: absence is rendered
with a word and an icon, and it is filterable.

**DigiVol.** Work is organized as named expeditions with a visible completion percentage and task
count, not as an undifferentiated backlog. Our queue summary shows the same shape: per-collection
counts by disposition, and the age of the oldest item, so a manager can see where work is stuck
without opening a record.

**Zooniverse, Notes from Nature.** The project page reports 180,421 classifications against 57,465
subjects, roughly three independent readings per subject, aggregated afterwards. Independent
observation before consensus is the same invariant our backend enforces with two vision models.
The lesson for the interface: never render the two model readings as one merged "result" with a
confidence number. Render them as two peers, then render the comparison as a third thing.

**Linear method.** The stated position is "Simple first, then powerful" and to avoid invented
terminology. We take one concrete rule from it: no internal vocabulary in the first sentence a
reviewer reads. `revision`, `digest`, `artifact`, `lease` and `CAS` live behind a disclosure, not
in a card title.

**Field Museum public site.** Computed styles on `https://www.fieldmuseum.org/` at desktop width
resolve to a single typeface (`Switzer`, a neutral geometric grotesque) across 1,174 elements, a
near-black text color `rgb(26, 28, 31)`, white and a cool off-white `rgb(248, 250, 253)` for
grounds, a saturated blue `rgb(19, 51, 247)` as the interactive accent, and a small set of pastel
category accents (`#FFD469`, `#9ACDE5`, `#9BE0C1`, `#D7AEF2`, `#FFA764`). The transferable cues are
one typeface, near-black rather than black, a very light neutral ground, and a single saturated
accent. We are building for the museum, not impersonating it: we do not use their logo, their
typeface, their blue, or any claim of their brand guidelines.

---

## 1. Design principles

Eight principles. Each decides an argument that will actually happen in this codebase.

### 1.1 The pixels outrank the parse

The photograph is the record; everything else is a claim about it.

- **So we do** give the source image the largest continuous area in the review layout at every
  window size, keep it on screen while a field is edited, and make every reading, field and region
  clickable back to the pixels that produced it.
- **So we never do** put the source image behind a tab, a dialog, or a scroll position the reviewer
  has to restore. The current `ChoiceChip` tab row in `workbench.dart` puts Readings, Fields and
  History in tabs; the image must never join them.

### 1.2 Absence is a value

Unknown, unreadable, not present, unmeasured and uncalibrated each get a token, an icon, a word,
and a place in the layout.

- **So we do** render every abstention with `AbstentionMark`: a Material Symbol, the word, and
  `onSurfaceVariant` color, occupying the same slot a value would.
- **So we never do** render an absent value as an empty string, a dash, a zero, or a collapsed row.
  The existing "Unmeasured" handling in `capture_quality.dart` is the standard, not the exception.

### 1.3 Two readings are two readings

Independent observations stay visually independent until a human resolves them.

- **So we do** give each model reading its own `ReadingCard` with its own `EvidenceSource` header,
  and render the comparison as a separate `DiffText` layer that names both sides.
- **So we never do** show a single merged transcription with a confidence badge, or let agreement
  between two models render in the same visual treatment as a human confirmation.

### 1.4 A score never travels alone

Any number that summarizes something shows its inputs in the same component.

- **So we do** make `RiskMeter` structurally incapable of rendering a total without its component
  rows: the constructor takes a non-empty list of components and the widget asserts on an empty
  list. Uncalibrated stays on the face of the meter, not in a footnote.
- **So we never do** ship the current pattern, `risk_assessment.dart:30`, which renders
  "Review risk (uncalibrated)" as a heading over a bare number.

### 1.5 Color repeats, meaning does not

Hue is a fast index into a meaning the label already states. It is never the statement itself.

- **So we do** pair every status with an icon and a word, and reuse one hue family across several
  semantic tokens where the meanings are related (green is human-affirmed; steel is machine).
- **So we never do** add a status that is distinguishable only by hue, and we never let a hue carry
  meaning inside a photograph, where we cannot control the background.

### 1.6 Quiet until it matters

The interface has almost no visual energy so that a disagreement, a block or an error is
unmistakable.

- **So we do** default every surface to elevation level 0 with tonal separation and hairline
  outlines, keep saturated color to status and actions, and cap simultaneous saturated elements in
  one viewport at three.
- **So we never do** use gradients, shadows for decoration, surface tint overlays, animated
  accents, or a colored app bar. `AppBarTheme.surfaceTintColor` stays transparent, as it already is
  at `main.dart:123`.

### 1.7 Every consequence is visible before the commit

- **So we do** put the reason field, the diff of what will change, and the confirm control in one
  surface (`ReasonSheet`), and keep the confirm control disabled until the reason is non-empty.
- **So we never do** open a confirmation dialog that restates the action in prose without showing
  the change, and we never let a mutation fire from a row tap.

### 1.8 One component, learned once

- **So we do** ship exactly one status chip, one evidence disclosure, one reason sheet, one diff
  renderer, one authority card, and reuse them in the queue, the workbench, and the history browser.
- **So we never do** hand-roll a second variant inline. The current codebase has four different
  ad hoc containers for status text across `workspace.dart`, `workbench.dart`,
  `operational_panel.dart` and `review_context.dart`; the redesign collapses them to one.

---

## 2. Brand direction

### The look, in words

A collection cabinet under even north light. A pale, almost colorless ground with a whisper of
green in it, so that a specimen photograph placed on it reads true and is never tinted by its
surround. Text in near-black, never pure black, set in one engineering-grade sans across the whole
product. Structure carried by 1dp hairlines and by half-step changes in surface tone, not by
shadows or cards floating on cards. Deep herbarium green for the one thing a human commits to.
Steel blue for what a machine produced. Verdigris teal for an external authority. Ochre for
attention. Oxide red for a stop. Everything else grey.

The reference points are the instrument, the cabinet and the catalogue: a spectrophotometer front
panel, a Cornell drawer under glass, a printed determination slip. Not a consumer app, not a
dashboard, not a museum gift shop.

### What we explicitly reject

**Purple and violet gradients, glows and glassmorphism.** The current app already carries one
instance of this failure mode: `disposition.deferred` is `Color(0xff594d7c)` at
`workspace.dart:305`, a lavender that reads as a brand accent rather than as "parked". We replace
it with a warm neutral clay. There is no gradient anywhere in this system. Every fill in the token
table is a flat color.

**Beige plus brass, the "heritage museum" default.** Warm cream grounds with gold rules look like a
donor wall and, worse, they shift the perceived color of a specimen photograph toward warm. Our
light ground `#FBFCFA` is neutral to within one unit per channel with a single point of green cast.
There is no gold, no bronze, no serif small caps, no textured paper, no drop-shadowed frames.

**Purely dark "pro tool" chrome.** Reviewers work in collection rooms with the lights on and in
offices with them off. Both modes ship, and neither is the afterthought.

### Both modes ship

Light and dark are both first class and both defined by hand in this document. `themeMode` follows
the platform by default (`ThemeMode.system`) and is overridable in settings. Dark mode is not an
inverted light mode: the dark surface ramp uses larger tonal steps (1.13 to 1.66 against `surface`,
versus 1.06 to 1.33 in light) because tonal separation is harder to see at low luminance, and dark
accents are lifted in lightness and reduced in chroma so they do not bloom.

---

## 3. Color

### 3.1 How the seed feeds `ColorScheme.fromSeed`, and where we override

The seed is `Color(0xFF14513D)`, a deep herbarium green. It replaces the current
`0xff174f3b` at `main.dart:109`, which is one step lighter and slightly bluer.

`ColorScheme.fromSeed` takes a seed, derives tonal palettes, and exposes 47 optional per-role
overrides; the documentation states that the generated colors "are designed to work well together
and meet contrast requirements for accessibility" and that a developer supplying overrides takes on
that responsibility
(<https://api.flutter.dev/flutter/material/ColorScheme/ColorScheme.fromSeed.html>).

Running `ColorScheme.fromSeed(seedColor: Color(0xFF14513D))` on this repository's toolchain
(Flutter 3.38.5, `material_color_utilities` 0.11.1) produces:

| Role | fromSeed, light | fromSeed, dark |
|---|---|---|
| `primary` | `#1B6B51` | `#8BD6B6` |
| `primaryContainer` | `#A6F2D1` | `#00513B` |
| `secondary` | `#4C6358` | `#B3CCBF` |
| `tertiary` | `#3E6374` | `#A6CCE0` |
| `error` | `#BA1A1A` | `#FFB4AB` |
| `surface` | `#F5FBF5` | `#0F1512` |
| `surfaceContainerLow` | `#EFF5F0` | `#171D1A` |
| `surfaceContainer` | `#E9EFEA` | `#1B211E` |
| `surfaceContainerHigh` | `#E4EAE4` | `#252B28` |
| `surfaceContainerHighest` | `#DEE4DF` | `#303633` |
| `surfaceDim` | `#D6DBD6` | `#0F1512` |
| `onSurface` | `#171D1A` | (mirrors) |
| `onSurfaceVariant` | `#404944` | (mirrors) |
| `outline` | `#707974` | (mirrors) |
| `outlineVariant` | `#BFC9C2` | (mirrors) |

**What we keep from the generator.** The luminance ladder. Our surface steps sit within one or two
units of the generated ones in both modes, so the hierarchy the generator was tuned for is intact,
and the `on*` roles land in the same tonal bands.

**What we override, and why.**

1. **Neutral chroma, all surface roles, both modes.** The generated light `surface` `#F5FBF5` has a
   6-unit green cast (R 245, G 251, B 245). On a screen showing an insect label photographed on a
   white card, that cast shifts the perceived hue of the card and of any faded ink on it. We flatten
   the neutrals to at most a 1-unit cast. This is the single most important override in the system
   and it is a color-judgment requirement, not a taste preference.
2. **`primary`, light.** The generated `#1B6B51` is tone 40 and gives 5.22:1 against white. Ours is
   `#14513D` at 9.23:1 against white. Filled primary buttons carry the commit action and are read
   for hours; we spend the extra contrast.
3. **`tertiary`.** The generator picks a blue `#3E6374`, which collides with our machine-evidence
   steel. We set tertiary to verdigris teal so "external authority" has its own hue.
4. **`error`.** The generated `#BA1A1A` is a fire-engine red. We use oxide `#A32617`, which is
   darker and less saturated, so a single error in a dense record does not dominate the viewport.
5. **Every product token in section 3.4.** These do not exist in `ColorScheme` at all and are
   supplied by the `SpecimenColors` `ThemeExtension`.

Implementation shape:

```dart
ColorScheme.fromSeed(
  seedColor: const Color(0xFF14513D),
  brightness: Brightness.light,
).copyWith(/* every role in 3.2, explicitly */);
```

We call `.copyWith` with every role listed in 3.2 rather than relying on the generator for any of
them. The generator is used to prove the ladder is sane, then pinned. Rationale: a future Flutter
upgrade that changes `material_color_utilities` must not silently move a shipped color.

### 3.2 Semantic color roles, light

Ground truth surfaces: `surface #FBFCFA`, `surfaceContainerLowest #FFFFFF`,
`surfaceContainerLow #F4F6F2`, `surfaceContainer #EEF1EB`, `surfaceContainerHigh #E7EBE4`,
`surfaceContainerHighest #E1E5DD`, `surfaceDim #DADED6`. `surfaceBright` equals `surface` in light.

"Min across surfaces" is the smallest contrast ratio the color achieves against any of those seven
distinct values, so it is the number that has to clear the bar.

| Role | Hex | Paired with | Ratio | Min across surfaces | Use |
|---|---|---|---|---|---|
| `surface` | `#FBFCFA` | `onSurface` | 16.96:1 | n/a | Page ground, workbench content pane |
| `surfaceContainerLowest` | `#FFFFFF` | `onSurface` | 17.45:1 | n/a | Image pane matte, input field fill |
| `surfaceContainerLow` | `#F4F6F2` | `onSurface` | 16.05:1 | n/a | Queue row resting fill |
| `surfaceContainer` | `#EEF1EB` | `onSurface` | 15.31:1 | n/a | Cards, navigation rail, sheets |
| `surfaceContainerHigh` | `#E7EBE4` | `onSurface` | 14.46:1 | n/a | Nested panels, expanded rows |
| `surfaceContainerHighest` | `#E1E5DD` | `onSurface` | 13.67:1 | n/a | Code and JSON escape hatch |
| `surfaceDim` | `#DADED6` | `onSurface` | 12.80:1 | n/a | Scrolled-under app bar band |
| `surfaceBright` | `#FBFCFA` | `onSurface` | 16.96:1 | n/a | Equals `surface` in light. Dialog and menu ground. |
| `onSurface` | `#161B17` | all surfaces | 12.80:1 to 17.45:1 | 12.80 | All primary text and icons |
| `onSurfaceVariant` | `#414A42` | all surfaces | 6.75:1 to 9.20:1 | 6.75 | Secondary text, metadata, `diff.unchanged` |
| `outline` | `#6C756C` | all surfaces | 3.50:1 to 4.77:1 | 3.50 | Input borders, chip borders |
| `outlineVariant` | `#C0C8BF` | all surfaces | 1.26:1 to 1.71:1 | 1.26 | Decorative dividers only. Never a boundary a user must find. |
| `primary` | `#14513D` | `onPrimary #FFFFFF` | 9.23:1 | 6.77 | Filled commit actions, focus-adjacent selection bar |
| `onPrimary` | `#FFFFFF` | on `primary` | 9.23:1 | n/a | Text and icons on primary |
| `primaryContainer` | `#BCEDD7` | `onPrimaryContainer #00291D` | 12.16:1 | n/a | Selected nav destination, tonal button |
| `onPrimaryContainer` | `#00291D` | on `primaryContainer` | 12.16:1 | n/a | Text on primary container |
| `secondary` | `#2F5A78` | `onSecondary #FFFFFF` | 7.36:1 | 5.40 | Machine-origin chrome, region overlay stroke |
| `onSecondary` | `#FFFFFF` | on `secondary` | 7.36:1 | n/a | Text on secondary |
| `secondaryContainer` | `#D3E4F1` | `onSecondaryContainer #0A2E48` | 10.78:1 | n/a | Model reading card header |
| `onSecondaryContainer` | `#0A2E48` | on `secondaryContainer` | 10.78:1 | n/a | Text on secondary container |
| `tertiary` | `#1D6A73` | `onTertiary #FFFFFF` | 6.25:1 | 4.58 | Authority links and markers |
| `onTertiary` | `#FFFFFF` | on `tertiary` | 6.25:1 | n/a | Text on tertiary |
| `tertiaryContainer` | `#CFEAEE` | `onTertiaryContainer #043F46` | 9.23:1 | n/a | Authority candidate card header |
| `onTertiaryContainer` | `#043F46` | on `tertiaryContainer` | 9.23:1 | n/a | Text on tertiary container |
| `error` | `#A32617` | `onError #FFFFFF` | 7.38:1 | 5.41 | Error text, error icons |
| `onError` | `#FFFFFF` | on `error` | 7.38:1 | n/a | Text on error |
| `errorContainer` | `#FADAD3` | `onErrorContainer #5C1409` | 10.28:1 | n/a | Inline error banner fill |
| `onErrorContainer` | `#5C1409` | on `errorContainer` | 10.28:1 | n/a | Text on error container |
| `inverseSurface` | `#2B312C` | `inverseOnSurface #EFF2EB` | 11.77:1 | n/a | Snackbar, tooltip |
| `inverseOnSurface` | `#EFF2EB` | on `inverseSurface` | 11.77:1 | n/a | Snackbar text |
| `inversePrimary` | `#8BD6B6` | on `inverseSurface` | 7.85:1 | n/a | Snackbar action |
| `scrim` | `#000000` at 40% | over any surface | n/a | n/a | Behind dialogs and sheets |
| `shadow` | `#000000` | n/a | n/a | n/a | Only at the four elevations in section 5 |

### 3.3 Semantic color roles, dark

Ground truth surfaces: `surface #101311`, `surfaceContainerLowest #0A0D0B`,
`surfaceContainerLow #181C19`, `surfaceContainer #1C201D`, `surfaceContainerHigh #262B27`,
`surfaceContainerHighest #313631`, `surfaceBright #373C37`. `surfaceDim` equals `surface`.

| Role | Hex | Paired with | Ratio | Min across surfaces | Use |
|---|---|---|---|---|---|
| `surface` | `#101311` | `onSurface` | 14.79:1 | n/a | Page ground |
| `surfaceContainerLowest` | `#0A0D0B` | `onSurface` | 15.45:1 | n/a | Image pane matte |
| `surfaceContainerLow` | `#181C19` | `onSurface` | 13.63:1 | n/a | Queue row resting fill |
| `surfaceContainer` | `#1C201D` | `onSurface` | 13.05:1 | n/a | Cards, rail, sheets |
| `surfaceContainerHigh` | `#262B27` | `onSurface` | 11.40:1 | n/a | Nested panels |
| `surfaceContainerHighest` | `#313631` | `onSurface` | 9.76:1 | n/a | Raw JSON escape hatch |
| `surfaceBright` | `#373C37` | `onSurface` | 8.92:1 | n/a | Dialog and menu ground |
| `onSurface` | `#E2E6DF` | all surfaces | 8.92:1 to 15.45:1 | 8.92 | Primary text and icons |
| `onSurfaceVariant` | `#BFC8BE` | all surfaces | 6.56:1 to 11.36:1 | 6.56 | Secondary text, `diff.unchanged` |
| `outline` | `#8A938A` | all surfaces | 3.55:1 to 6.16:1 | 3.55 | Borders |
| `outlineVariant` | `#424A42` | all surfaces | 1.23:1 to 2.13:1 | 1.23 | Decorative dividers only |
| `primary` | `#7FD6B0` | `onPrimary #00382A` | 7.60:1 | 6.52 | Filled commit actions |
| `onPrimary` | `#00382A` | on `primary` | 7.60:1 | n/a | Text on primary |
| `primaryContainer` | `#0F4535` | `onPrimaryContainer #9CE7C4` | 7.61:1 | n/a | Selected nav destination |
| `onPrimaryContainer` | `#9CE7C4` | on `primaryContainer` | 7.61:1 | n/a | Text on primary container |
| `secondary` | `#9CC3E4` | `onSecondary #0A2E48` | 7.57:1 | 6.08 | Machine-origin chrome |
| `onSecondary` | `#0A2E48` | on `secondary` | 7.57:1 | n/a | Text on secondary |
| `secondaryContainer` | `#123249` | `onSecondaryContainer #CBE0F3` | 9.82:1 | n/a | Model reading card header |
| `onSecondaryContainer` | `#CBE0F3` | on `secondaryContainer` | 9.82:1 | n/a | Text on secondary container |
| `tertiary` | `#7ED3DD` | `onTertiary #00363C` | 7.69:1 | 6.57 | Authority links |
| `onTertiary` | `#00363C` | on `tertiary` | 7.69:1 | n/a | Text on tertiary |
| `tertiaryContainer` | `#0C3D43` | `onTertiaryContainer #A9E4EA` | 8.49:1 | n/a | Authority candidate header |
| `onTertiaryContainer` | `#A9E4EA` | on `tertiaryContainer` | 8.49:1 | n/a | Text on tertiary container |
| `error` | `#F0A79A` | `onError #5A140A` | 6.95:1 | 5.74 | Error text and icons |
| `onError` | `#5A140A` | on `error` | 6.95:1 | n/a | Text on error |
| `errorContainer` | `#5C1A10` | `onErrorContainer #FFD9D0` | 9.99:1 | n/a | Inline error banner fill |
| `onErrorContainer` | `#FFD9D0` | on `errorContainer` | 9.99:1 | n/a | Text on error container |
| `inverseSurface` | `#E2E6DF` | `inverseOnSurface #2B312C` | 10.53:1 | n/a | Snackbar |
| `inverseOnSurface` | `#2B312C` | on `inverseSurface` | 10.53:1 | n/a | Snackbar text |
| `inversePrimary` | `#14513D` | on `inverseSurface` | 7.31:1 | n/a | Snackbar action |
| `scrim` | `#000000` at 60% | over any surface | n/a | n/a | Behind dialogs and sheets |

### 3.4 Product semantic tokens

Seven hue primitives carry every product token. Meaning comes from the icon and the word; the hue
is an index, not a statement (principle 1.5).

| Primitive | Light content | Light fill | Light on-fill | Dark content | Dark fill | Dark on-fill |
|---|---|---|---|---|---|---|
| green | `#1A6D4F` | `#D3EFE1` | `#063D2A` | `#2CBB86` | `#0E3B2B` | `#A5E9CA` |
| steel | `#2F6594` | `#D9E7F4` | `#0B3554` | `#78A9D4` | `#14344B` | `#B8D6F0` |
| teal | `#1D6A73` | `#CFEAEE` | `#043F46` | `#31B4C3` | `#0D383D` | `#A9E4EA` |
| ochre | `#84580B` | `#F7E3B4` | `#4A3400` | `#E19512` | `#43310A` | `#F2D79B` |
| oxide | `#A83D28` | `#F8DDD6` | `#5C1B0E` | `#E1907F` | `#4E241B` | `#FFCFC3` |
| slate | `#546275` | `#DFE4EB` | `#2E3846` | `#99A6B5` | `#29313A` | `#C8D3DF` |
| clay | `#6D5E52` | `#E7E1DA` | `#3E3630` | `#B0A397` | `#332D28` | `#DED3C8` |

Measured ratios for the primitives:

| Primitive | Light content min across the 7 light surfaces | Light on-fill on its fill | Light content on its fill | Dark content min across the 7 dark surfaces | Dark on-fill on its fill | Dark content on its fill |
|---|---|---|---|---|---|---|
| green | 4.61:1 | 10.07:1 | 5.14:1 | 4.59:1 | 9.00:1 | 5.10:1 |
| steel | 4.52:1 | 10.10:1 | 4.89:1 | 4.52:1 | 8.58:1 | 5.19:1 |
| teal | 4.58:1 | 9.23:1 | 4.96:1 | 4.53:1 | 9.07:1 | 5.12:1 |
| ochre | 4.55:1 | 9.31:1 | 4.91:1 | 4.57:1 | 8.90:1 | 5.06:1 |
| oxide | 4.58:1 | 10.08:1 | 4.85:1 | 4.56:1 | 9.40:1 | 5.34:1 |
| slate | 4.56:1 | 9.28:1 | 4.86:1 | 4.55:1 | 8.68:1 | 5.32:1 |
| clay | 4.57:1 | 9.11:1 | 4.94:1 | 4.58:1 | 9.22:1 | 5.11:1 |

Every `content` value clears 4.5:1 on every surface in its mode, so a product token can be used as
text anywhere without checking which surface it landed on. Every `on-fill` clears 4.5:1 on its own
fill by a wide margin. Fills sit between 1.19:1 and 1.26:1 against `surface` in light and between
1.32:1 and 1.50:1 in dark, which is intentionally below the 3:1 non-text threshold: a chip's
boundary is carried by a 1dp border in the `content` color, which clears 4.5:1 against the
surrounding surface, satisfying SC 1.4.11 for the component boundary
(<https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html>).

#### Token map

| Token | Primitive | Light content | Dark content | Notes |
|---|---|---|---|---|
| `disposition.cleared` | green | `#1A6D4F` | `#2CBB86` | Same family as `primary`. Green means a human affirmed it. Intentional, not a collision: the commit action and the state it produces share a family. |
| `disposition.needsReview` | ochre | `#84580B` | `#E19512` | Attention, not failure. |
| `disposition.deferred` | clay | `#6D5E52` | `#B0A397` | Replaces the lavender `#594D7C` at `workspace.dart:305`. Shelved, not judged. |
| `state.processing` | steel | `#2F6594` | `#78A9D4` | Never a final queue. Always paired with a progress affordance. |
| `state.blocked` | oxide | `#A83D28` | `#E1907F` | Operational, not evidentiary. The copy says which stage. |
| `evidence.model` | slate | `#546275` | `#99A6B5` | Deliberately neutral. A model reading is an observation, not a decision, so it gets the least assertive hue in the set. |
| `evidence.human` | green | `#1A6D4F` | `#2CBB86` | Human authority is the only thing in this product that is allowed to look affirmative. |
| `evidence.authority` | teal | `#1D6A73` | `#31B4C3` | External reference file (taxonomy, geography). |
| `diff.added` (text) | green | `#1A6D4F` | `#2CBB86` | Marker `+` plus a 3dp leading bar. |
| `diff.added` (fill) | green | `#D6F2E4` (`onSurface` on it: 14.69:1) | `#123B2C` (`onSurface` on it: 9.85:1) | Highlight behind body text. |
| `diff.changed` (text) | ochre | `#84580B` | `#E19512` | Marker `~` plus an underline. |
| `diff.changed` (fill) | ochre | `#FBEBC8` (`onSurface` on it: 14.81:1) | `#40300B` (`onSurface` on it: 10.10:1) | Replaces the raw `Color(0xffffe7a3)` at `workbench.dart:672`. |
| `diff.unchanged` | neutral | `onSurfaceVariant #414A42` (8.94:1 on `surface`) | `onSurfaceVariant #BFC8BE` (10.88:1 on `surface`) | No fill, no marker. |
| `region.overlay` | steel | stroke `#2F6594`, 2dp | stroke `#78A9D4`, 2dp | Drawn over a photograph. Always with a 1dp `#FFFFFF` outer casing in light (6.16:1 against the core) and a 1dp `#101311` outer casing in dark (7.50:1), so the stroke survives any pixel behind it. |
| `region.selected` | fixed | core `#FFC02E`, 3dp, 1dp `#101311` casing both sides | identical in both modes | 11.42:1 against the casing. Selection is transient and lives only over the image, so it is the one token that does not follow the mode. It replaces `Colors.amber` at `workbench.dart:544` and `region_editor.dart:133`, which had no casing and could vanish on a pale label. |
| `risk.low` | green | `#1A6D4F` | `#2CBB86` | One filled bar of three. |
| `risk.medium` | ochre | `#84580B` | `#E19512` | Two filled bars of three. |
| `risk.high` | oxide | `#A83D28` | `#E1907F` | Three filled bars of three. |
| `environment.synthetic` | ochre | fill `#F7E3B4`, text `#4A3400` (9.31:1) | fill `#4A3608`, text `#F2D79B` (8.21:1) | Retunes the existing `#FFE7A3` / `#483500` pair at `workspace.dart:606-610`, which already passed. Full-bleed band, never dismissible. |
| `focus.ring` | reserved | `#0F5FA8` | `#7FC4F5` | Light min 4.78:1 across surfaces; dark min 5.96:1. Reserved. Never used for status. |
| `disabled.content` | neutral | `#5A625A` (4.63:1 to 6.31:1 across surfaces; 3.67:1 to 4.95:1 on `disabled.container`) | `#A3ACA3` (4.82:1 to 8.36:1; 3.52:1 to 6.46:1 on `disabled.container`) | See 3.6. Raised from `outline` by finding V-8. |
| `disabled.outline` | neutral | `#6F786F` (3.35:1 to 4.57:1 across surfaces) | `#848D84` (3.29:1 to 5.70:1) | The border of a disabled outlined control and of a disabled field. Non-text, so 3:1. |
| `disabled.container` | neutral | `onSurface` at 12% | `onSurface` at 12% | |

### 3.5 Status is never color alone

Every status renders as `StatusChip`: a Material Symbol, then a word, then a 1dp border in the
`content` color, on the `fill`. The chip is legible with the color channel removed and legible to a
screen reader from `Semantics(label:)` alone.

| Status | Icon (`material_symbols_icons`) | FILL | Label string | Token |
|---|---|---|---|---|
| Cleared | `Symbols.check_circle` | 1 | `Cleared` | `disposition.cleared` |
| Needs human review | `Symbols.flag` | 1 | `Needs human review` | `disposition.needsReview` |
| Deferred | `Symbols.pause_circle` | 1 | `Deferred` | `disposition.deferred` |
| Processing | `Symbols.autorenew` | 0 | `Processing` | `state.processing` |
| Processing blocked | `Symbols.block` | 0 | `Processing blocked` | `state.blocked` |
| Retry scheduled | registry `time` (09 section 7) | 0 | `Retry scheduled` | `state.blocked` |
| Paused | registry `blocked` (09 section 7) | 0 | `Paused` | `state.blocked` |
| Cancelled | registry `stop` (09 section 7) | 0 | `Cancelled` | `state.blocked` |
| State unknown | `Symbols.help` | 0 | `State unknown` | `slate` |
| Model reading | `Symbols.memory` | 0 | `Model A` / `Model B` | `evidence.model` |
| Human decision | `Symbols.person` | 1 | `Reviewer` plus name | `evidence.human` |
| Authority match | `Symbols.menu_book` | 0 | `Authority` plus source name | `evidence.authority` |
| Risk, low | `Symbols.signal_cellular_alt_1_bar` | 0 | `Low` | `risk.low` |
| Risk, medium | `Symbols.signal_cellular_alt_2_bar` | 0 | `Medium` | `risk.medium` |
| Risk, high | `Symbols.signal_cellular_alt` | 0 | `High` | `risk.high` |
| Synthetic environment | `Symbols.science` | 0 | `Synthetic environment` | `environment.synthetic` |
| Added in diff | `Symbols.add` | 0 | announced as `added: <text>` | `diff.added` |
| Changed in diff | `Symbols.change_circle` | 0 | announced as `differs: <a> versus <b>` | `diff.changed` |
| Unchanged in diff | none | n/a | no announcement | `diff.unchanged` |

The three stopped run states (PRD 10.1) were added by the go-live UI
workstream on 2026-09-23 and confirmed by the coordinator under G5
(`docs/execution/golive/UI.md` T1.2): the PRD's words on the operational
triple, with registry glyphs that already existed. Their semantic label names
the run, not the queue ("Run: paused").

The abstention marks use the same rule:

| Abstention | Icon | Label |
|---|---|---|
| Unknown | `Symbols.help` | `Unknown` |
| Unreadable | `Symbols.visibility_off` | `Unreadable` |
| Not present | `Symbols.horizontal_rule` | `Not present` |
| Unmeasured | `Symbols.hide_source` | `Unmeasured` |

### 3.6 Disabled state, and why it does not use 38%

Material's default disabled treatment is 38% opacity on the content color. Measured against this
product's own surfaces it lands between 2.26:1 and 2.39:1 in light and between 2.68:1 and 3.08:1 in
dark, and the two controls finding V-8 caught, `Correct label regions` and `Approve record`, read at
2.38:1 and 2.25:1. In this product a disabled action is carrying information: it means the server
does not permit this decision yet, and the control's own label and hint say which. WCAG exempts
inactive components (SC 1.4.3 excludes text in an inactive user interface component, and SC 1.4.11
excludes inactive components), but the exemption is not a reason to make a load-bearing sentence
illegible.

Rule, as of finding V-8:

- `disabled.content` is `#5A625A` in light and `#A3ACA3` in dark. It clears the **text** minimum of
  4.5:1 on all eight surface roles in both modes (light 4.63:1 to 6.31:1, dark 4.82:1 to 8.36:1),
  and still clears it over `disabled.container` (light 3.67:1 to 4.95:1, dark 3.52:1 to 6.46:1),
  which is where a disabled `FilledButton` draws it. It is deliberately quieter than
  `onSurfaceVariant` on every surface, so a disabled control is legible and still reads as disabled.
- `disabled.outline` is `#6F786F` in light and `#848D84` in dark: light 3.35:1 to 4.57:1, dark
  3.29:1 to 5.70:1, over the 3:1 non-text floor everywhere.
- `disabled.container` stays `onSurface` at 12%.

These are not advisory. `specimenFilledButtonTheme`, `specimenOutlinedButtonTheme`,
`specimenTextButtonTheme`, `specimenIconButtonTheme`, `specimenChipTheme` and `specimenInputTheme`
each take the token layer and pass the pair to Material, so no call site can fall back to the 38%
default. `test/theme/contrast_test.dart` holds all four claims: 3:1 for both tokens on every
surface, 4.5:1 for the content, 3:1 for the content over its own container, and that the content
beats the Material default it replaces on every surface while staying under `onSurfaceVariant`.

A disabled action always carries a tooltip and a `Semantics(hint:)` that names the reason.

---

## 4. Typography

### 4.1 The pairing

| Role | Family | Package | Why |
|---|---|---|---|
| Plain and brand | IBM Plex Sans | `google_fonts` (`GoogleFonts.ibmPlexSans`) | One family for both M3 typeface slots. |
| Literal and identifier | JetBrains Mono | `google_fonts` (`GoogleFonts.jetBrainsMono`) | Verbatim transcription, IDs, digests. |

M3's type scale allows a brand typeface for Display and Headline and a plain typeface for Body and
Label (<https://m3.material.io/styles/typography/type-scale-tokens>). We deliberately set both
slots to IBM Plex Sans and express hierarchy with weight and size only. Introducing a second display
face in a tool whose job is to make two nearly identical strings distinguishable would spend the
reader's attention on the wrong difference.

**Why IBM Plex Sans.**

- *Long reading sessions.* Plex was drawn as a corporate text and interface face, so it holds up in
  running text at 16sp, which is where the reason field, the review context and the history entries
  live. Its open apertures and low stroke contrast keep 22 line breaks per card readable without
  the reader tracking back.
- *Tiny label transcriptions.* Plex's terminals are cut on the horizontal and vertical, which keeps
  the shape of an `a`, `e` and `s` intact at 12sp on a 2x display.
- *Mixed scripts including Latin diacritics.* IBM Plex ships Sans, Serif, Mono and Condensed plus
  Arabic, Devanagari, Thai, Hebrew, Japanese, Korean, Simplified and Traditional Chinese cuts
  (<https://www.ibm.com/plex/>). The Latin cut covers Latin-1 and Latin Extended-A along with Greek
  and Cyrillic, which is what a collection of specimens collected across Europe, Central Asia and
  Latin America needs: `Ł`, `ș`, `ǎ`, `ő`, `ħ`, `ẞ`, `ı`. Diacritics only work if they are not
  clipped, so no text container in this product has a fixed height, and no line height below 1.3 is
  permitted on any role that can carry a value from a label. M3 warns that ignoring language height
  causes overlapping text and broken UI.
- *Numeric IDs.* Plex has tabular figures. Every catalog number, count and coordinate is set with
  `FontFeature.tabularFigures()` so digits align in a column and a changed digit is visible by
  position.

**Why JetBrains Mono for literal text.** JetBrains states that in JetBrains Mono the zero "has a
dot inside. The letter 'O' does not", that `1`, `l` and `I` are "easily distinguishable from each
other", that the comma and period have distinctly different shapes, and that the height of the
lowercase is maximized so each letter occupies more pixels at a given size
(<https://www.jetbrains.com/lp/mono/>).

**Why literal transcription must render in a disambiguating font.** A literal transcription is a
claim about what characters are physically on the label. If the reviewer cannot tell whether the
model transcribed `1` or `l`, or `0` or `O`, the transcription layer stops being evidence and
becomes a second guess. Collector numbers (`No. 1015`), determination initials (`det. J.O.`),
elevation values (`1050 m`) and catalog numbers all turn on exactly those pairs. The failure is
silent: the reviewer approves a record they misread. A dotted zero and a serifed `1` remove the
ambiguity at the glyph level, before it can become a data error.

**Ligatures are disabled in the literal role.** JetBrains Mono ships code ligatures. A ligature
replaces a character sequence with a single glyph, which is precisely wrong for verbatim text.
`mono.literal` sets `FontFeature.disable('liga')` and `FontFeature.disable('calt')`.

**Slashed zero in the sans.** Where a numeric value is set in IBM Plex Sans and a zero could be
misread, add `FontFeature.slashedZero()`. Anything transcription-critical goes in JetBrains Mono
instead and relies on its dotted zero, which is guaranteed.

**Packaging.** `google_fonts` fetches from fonts.google.com at runtime by default. Collection rooms
have unreliable networks, so we bundle: download the IBM Plex Sans and JetBrains Mono files into
`assets/google_fonts/`, list the folder under `flutter: assets:` in `pubspec.yaml`, and set
`GoogleFonts.config.allowRuntimeFetching = false` in `main()`. Register the OFL license with
`LicenseRegistry.addLicense` in `main()`, as the package instructs
(<https://pub.dev/packages/google_fonts>). Weights bundled: 400, 500, 600 for IBM Plex Sans;
400, 500 for JetBrains Mono. No italics; this product has no use for them.

### 4.2 The type scale

Sizes are in logical pixels. Line height is stated in pixels and as the Flutter `height` multiple.
Letter spacing is in logical pixels, matching Flutter's `TextStyle.letterSpacing`.

Where our values differ from the M3 baseline, the reason is in the last column. The largest
systematic change is letter spacing: M3's Body tracking of +0.25 to +0.5 is tuned for Roboto, which
is narrower than IBM Plex Sans. Applying it to Plex loosens running text and makes two similar
transcriptions harder to compare.

| TextTheme role | Size | Weight | Line height | Tracking | Where it is used | Change from M3 baseline |
|---|---|---|---|---|---|---|
| `displayLarge` | 40 | 600 | 48 (1.20) | -0.4 | Sign-in wordmark only | Down from 57. No screen in this product needs 57. |
| `displayMedium` | 32 | 600 | 40 (1.25) | -0.3 | Empty-state headline, expanded windows | Down from 45 |
| `displaySmall` | 28 | 600 | 36 (1.29) | -0.2 | Not used. Mapped so third-party widgets do not crash. | Down from 36 |
| `headlineLarge` | 28 | 600 | 36 (1.29) | -0.2 | Screen title, expanded and large windows | Weight up from 400 |
| `headlineMedium` | 24 | 600 | 32 (1.33) | -0.15 | Screen title, compact and medium windows | Down from 28, weight up |
| `headlineSmall` | 20 | 600 | 28 (1.40) | -0.1 | Specimen identifier header in the workbench | Down from 24, weight up |
| `titleLarge` | 18 | 600 | 26 (1.44) | 0 | Card and section headers ("Readings", "Fields and evidence") | Down from 22, weight up from 400 |
| `titleMedium` | 16 | 600 | 24 (1.50) | +0.05 | Dialog and sheet titles, field group headers | Weight up from 500, tracking down from +0.15 |
| `titleSmall` | 14 | 600 | 20 (1.43) | +0.05 | Sub-headers, table column headers | Weight up from 500 |
| `bodyLarge` | 16 | 400 | 26 (1.625) | 0 | Reading text, reason text, review context prose | Line height up from 24. Long-session reading. |
| `bodyMedium` | 14 | 400 | 22 (1.57) | 0 | Default UI body, queue row secondary text | Line height up from 20, tracking down from +0.25 |
| `bodySmall` | 12 | 400 | 18 (1.50) | +0.1 | Timestamps, helper text, captions | Line height up from 16, tracking down from +0.4 |
| `labelLarge` | 14 | 600 | 20 (1.43) | +0.1 | Button labels | Weight up from 500 |
| `labelMedium` | 12 | 600 | 16 (1.33) | +0.3 | Chip labels, tab labels, badge counts | Weight up from 500, tracking down from +0.5 |
| `labelSmall` | 11 | 600 | 16 (1.45) | +0.4 | Overline, dense metadata. Never used for anything a decision depends on. | Weight up from 500 |

### 4.3 The monospace roles

These are not `TextTheme` roles. They live on the `SpecimenTypography` `ThemeExtension` so that a
call site cannot reach them by accident.

| Token | Family | Size | Weight | Line height | Tracking | Features | Use |
|---|---|---|---|---|---|---|---|
| `mono.literal` | JetBrains Mono | 16 | 400 | 26 (1.625) | 0 | `tnum`, `liga` off, `calt` off | Verbatim label transcription in a `ReadingCard` |
| `mono.literalDense` | JetBrains Mono | 14 | 400 | 22 (1.57) | 0 | `tnum`, `liga` off, `calt` off | Verbatim transcription inside a `FieldRow` literal layer |
| `mono.identifier` | JetBrains Mono | 13 | 500 | 20 (1.54) | +0.2 | `tnum` | Specimen IDs, catalog numbers, region IDs, revision numbers |
| `mono.digest` | JetBrains Mono | 12 | 400 | 18 (1.50) | +0.2 | `tnum` | SHA-256 digests, artifact IDs, lease IDs, mutation keys. Always truncated to first 12 characters with a copy control. |
| `mono.code` | JetBrains Mono | 13 | 400 | 20 (1.54) | 0 | `tnum` | The raw JSON escape hatch, on `surfaceContainerHighest` |

Which layer gets which font:

| `FieldRow` layer | Font | Rationale |
|---|---|---|
| Literal (what is on the label) | `mono.literalDense` | It is a character-by-character claim. |
| Parsed (what the extractor made of it) | `bodyMedium` | It is an interpretation, in prose. |
| Normalized (what goes to the authority) | `bodyMedium` with `tnum`, or `mono.identifier` when the normalized value is a code | Depends on whether the value is language or an identifier. |

---

## 5. Spacing, sizing, shape, elevation, borders

### 5.1 Spacing, 4px base grid

| Token | Value | Use |
|---|---|---|
| `space0` | 0 | Flush |
| `space1` | 4 | Icon to label inside a chip; gap between stacked metadata lines |
| `space2` | 8 | Gap between related controls; chip to chip |
| `space3` | 12 | Internal padding of a chip or a dense list row |
| `space4` | 16 | Default padding inside a card; gap between form fields; compact-window screen gutter |
| `space5` | 20 | Reserved for optical corrections only |
| `space6` | 24 | Gap between cards; medium and expanded screen gutter |
| `space8` | 32 | Gap between major sections in a pane |
| `space10` | 40 | Space above a screen title |
| `space12` | 48 | Empty-state vertical rhythm |
| `space16` | 64 | Maximum. Above this, the layout is wrong. |

Rules. Vertical rhythm inside a pane uses `space2`, `space4`, `space6`, `space8` only. `space1`,
`space3` and `space5` are for internal component construction. Never nest two containers that each
apply the gutter; the gutter belongs to the pane, and cards inside it are flush to it.

### 5.2 Sizing

| Token | Value | Use |
|---|---|---|
| `size.icon.inline` | 20 | Icons sitting on a `bodyMedium` or `labelMedium` baseline |
| `size.icon.action` | 24 | Icon buttons, navigation destinations |
| `size.icon.display` | 40 | Empty states only |
| `size.target.min` | 48 | Hit box for every interactive element, always |
| `size.target.visual.min` | 40 | Smallest a control may look. Below this, pad the hit box transparently. |
| `size.row.compact` | 72 | Queue row, compact window |
| `size.row.medium` | 64 | Queue row, medium window |
| `size.row.expanded` | 56 | Queue row, expanded and large windows |
| `size.appbar` | 56 | All windows |
| `size.rail` | 80 | Navigation rail |
| `size.pane.detail.min` | 400 | Minimum width for the workbench content pane before it stacks |
| `size.reading.max` | 640 | Maximum measure for prose. Reason text, review context, error explanations. |

### 5.3 Shape

M3 defines a ten-step corner radius scale (0, 4, 8, 12, 16, 20, 28, 32, 48, full)
(<https://m3.material.io/styles/shape/corner-radius-scale>). We use six steps.

| Token | Value | Applied to |
|---|---|---|
| `radius.none` | 0 | Table cells, diff spans, region overlays, dividers, the image matte, the environment banner |
| `radius.xs` | 4 | Chips, badges, input fields, tags, `KeyCap` |
| `radius.sm` | 8 | Cards, queue rows, menus, tooltips, buttons |
| `radius.md` | 12 | Sheets, dialogs, panels |
| `radius.lg` | 16 | Top corners of a bottom sheet |
| `radius.full` | full | Avatars and the progress ring cap only |

**The one rule.** A container that holds text at `bodyMedium` or smaller never exceeds
`radius.md`, and a nested container's radius equals its parent's radius minus its own inset
padding, floored at 0. This is M3's optical roundness formula, outer radius minus padding equals
inner radius, applied as a hard constraint rather than a suggestion. M3 also warns against large or
full corners on information-dense components. Concretely: a `radius.sm` card with `space4` padding
gives its nested rows `radius.none` (8 minus 16, floored at 0), which is why the field rows inside a
card are square.

Buttons are `radius.sm`, not `full`. M3's default button shape is fully rounded; we remap it,
which M3 explicitly permits at the component level.

### 5.4 Elevation

M3 states that shadows should be used "only when required to create additional protection against a
background or to encourage interaction" and that color, not shadow, is the M3 way to communicate
elevation (<https://m3.material.io/styles/elevation/overview>).

Policy: **surface tone plus a hairline outline, not shadow.** Four levels are permitted.

| Level | dp | Shadow | Surface role | Applied to |
|---|---|---|---|---|
| 0 | 0 | none | the appropriate `surfaceContainer*` step plus a 1dp `outlineVariant` border | Everything that does not float: cards, queue rows, panels, app bar, navigation rail, banners, the image pane |
| 1 | 1 | soft | `surfaceContainerLow` | Bottom sheet, plus scrim |
| 2 | 3 | soft | `surfaceContainer` | Menus, dropdowns, tooltips |
| 3 | 6 | soft | `surfaceContainerHigh` (light) / `surfaceBright` (dark) | Dialogs, snackbar, plus scrim |

Levels 4 and 5 are not used. `surfaceTintColor` is set to `Colors.transparent` on
`ThemeData`, `AppBarTheme`, `CardThemeData`, `DialogThemeData`, `BottomSheetThemeData`,
`MenuThemeData` and `NavigationRailThemeData`. M3's surface tint blends `primary` into an elevated
surface, which puts a green cast on any panel adjacent to a specimen photograph. This is the same
reason we flattened the neutrals in 3.1.

There is no hover elevation change. M3 raises a component one level on hover; in a dense list that
produces a viewport of twitching cards. Hover is a state layer only (see 5.7).

Scroll edge: the app bar does not change elevation on scroll. It changes fill from `surface` to
`surfaceDim` and gains a 1dp `outlineVariant` bottom border.

### 5.5 Touch targets

| Platform | Minimum | Source |
|---|---|---|
| Android | 48x48 dp | Material and Android accessibility guidance |
| iOS | 44x44 pt | Apple Human Interface Guidelines |
| Web and all platforms | 24x24 CSS px absolute floor | WCAG 2.2 SC 2.5.8 |

Our rule takes the maximum: **every interactive element has a 48x48 hit box on every platform**,
implemented as `ConstrainedBox(constraints: BoxConstraints(minWidth: 48, minHeight: 48))` around
the gesture detector, independent of the element's visual size. Density (5.6) changes visual size
and internal padding only; it never shrinks a hit box.

Two specific cases:

- **Region overlays.** The overlay's visible border traces the true bounding box, which for a small
  pinned-insect label can be a handful of logical pixels. The gesture target is a separate
  `ConstrainedBox` of at least 48x48 centered on the box. Visible geometry stays truthful; the
  target does not.
- **Adjacent targets.** Two 48dp targets must not touch. Minimum `space1` between them, so a gloved
  finger cannot land on the boundary.

### 5.6 Density

Density follows the input modality, not the device name and not the window width. A 13 inch
Windows tablet at 1366 wide is a touch device.

| Context | `VisualDensity` | Row height | Gutter |
|---|---|---|---|
| Android, iOS, any touch primary input | `VisualDensity.standard` (0, 0) | `size.row.compact` or `size.row.medium` by window | `space4` compact, `space6` medium and up |
| Web and desktop with a mouse or trackpad | `VisualDensity.compact` (-2, -2) | `size.row.expanded` | `space6` |
| Web and desktop with touch detected | `VisualDensity.standard` | `size.row.medium` | `space6` |

Implementation: seed `ThemeData.visualDensity` with `VisualDensity.adaptivePlatformDensity`, then
override to `VisualDensity.standard` when `MediaQuery.of(context).navigationMode` or a pointer
capability probe indicates touch. Hit boxes stay at 48 in every row of this table.

### 5.7 State layers

| State | Overlay | On |
|---|---|---|
| Hover | `onSurface` at 8% | The full row or component bounds |
| Focus | see 5.8 | |
| Pressed | `onSurface` at 10% | Full bounds |
| Dragged | `onSurface` at 16% | Full bounds |
| Selected | `primaryContainer` fill plus a 3dp leading bar in `primary` | Queue rows, navigation destinations, region list entries |
| Disabled | see 3.6 | |

Selection is never carried by the state layer alone. The 3dp leading bar means a selected row is
identifiable in a screenshot printed in greyscale.

### 5.8 Focus ring

WCAG 2.2 SC 2.4.13 requires the indicator to be at least as large as a 2px border around the
component and to reach 3:1 against adjacent colors.

Spec:

- 2dp stroke in `focus.ring` (`#0F5FA8` light, `#7FC4F5` dark).
- 2dp gap in the parent surface color between the component edge and the ring.
- Ring radius equals the component radius plus 4.
- The ring is drawn outside the component bounds, so it never reflows layout. Reserve 4dp of
  padding around any focusable element that sits flush to a container edge.

The gap is not decoration. `focus.ring` measures only 1.42:1 against `primary` in light and 1.09:1
in dark, so a ring drawn flush against a filled primary button would fail SC 2.4.13. The gap makes
the ring's adjacent colors the surface on both sides, where it measures 4.78:1 or better in light
and 5.96:1 or better in dark.

Over the image pane, the ring gains a 1dp `#101311` outer casing and a 1dp `#FFFFFF` inner casing so
it survives an arbitrary photograph.

`focus.ring` is reserved. No status, no evidence source and no risk level uses it. It is the only
blue in the system that is not `secondary` steel, and it appears for at most one element at a time.

### 5.9 Dividers

| Token | Stroke | Color | Use |
|---|---|---|---|
| `border.hairline` | 1 | `outlineVariant` | Between rows in a list, between sections in a card. Decorative separation only. |
| `border.boundary` | 1 | `outline` | Input field borders, chip borders, the outline of any container the user must be able to find. Minimum 3.50:1 light, 3.55:1 dark. |
| `border.emphasis` | 2 | `content` color of the relevant token, or `focus.ring` | Selected chip, region overlay, focus ring |
| `border.strong` | 3 | `region.selected` core, or `primary` for a selected row bar | Selected region, selected row leading bar |

M3 is explicit: `outlineVariant` is for decorative elements such as dividers, and should not be
used to define the visual boundary of a target; `outline` or another 3:1 color is required for that
(<https://m3.material.io/styles/color/roles>). We follow this exactly. `outlineVariant` measures
1.26:1 to 1.71:1 in light and 1.23:1 to 2.13:1 in dark, so it is decorative by construction.

Dividers are inset to the container's content padding, not full bleed, except between top-level
sections of a scrolling pane. Never stack a divider with a surface tone change; pick one.

---

## 6. Iconography

### 6.1 The set and the axes

Material Symbols, Outlined style, via `material_symbols_icons`
(<https://pub.dev/packages/material_symbols_icons>). Flutter's built-in `Icons` class is the older
Material Icons set and has no variable axes; we stop using it.

Material Symbols exposes four axes: weight 100 to 700, fill 0 to 1, grade -50 to 200, and optical
size 20dp to 48dp (<https://developers.google.com/fonts/docs/material_symbols>).

| Axis | Light | Dark | Rule |
|---|---|---|---|
| Style | Outlined | Outlined | Rounded and Sharp are not used. Outlined matches Plex's cut terminals. |
| `weight` | 400 | 400 | 500 only for an icon rendered at 16 or smaller, where a 400 stroke drops below one device pixel at 1x. Never 700. |
| `fill` | 0 | 0 | 1 only for two things: an icon in a `StatusChip` that marks the record's current settled disposition, and a selected navigation destination. Fill is a state, not an emphasis knob. |
| `grade` | 0 | -25 | Google's guidance is that low grades such as -25 reduce glare on light symbols against dark backgrounds. Dark mode sets -25 in `IconThemeData`. |
| `opticalSize` | equals rendered size | equals rendered size | 20 inline, 24 for actions and navigation, 40 for empty states. Never below 16. |

Set app-wide defaults through `ThemeData.iconTheme` and `IconButtonThemeData`; the package supports
`IconThemeData` and per-`Icon` axis parameters.

### 6.2 The icon per meaning

Disposition, state, evidence source and risk are in the table at 3.5. Actions:

| Action | Icon | Where |
|---|---|---|
| Record review approval | `Symbols.task_alt` | Workbench action bar, primary filled button |
| Confirm label coverage | `Symbols.frame_inspect` | Workbench action bar |
| Correct classification | `Symbols.edit` | Workbench action bar, `FieldRow` |
| Retry processing | `Symbols.refresh` | Workbench action bar when `state.blocked` |
| Give a reason | `Symbols.rate_review` | `ReasonSheet` header |
| View raw evidence | `Symbols.data_object` | `EvidenceDrawer` trigger. Replaces the `ExpansionTile` JSON dumps at `audit_history.dart:125,201,213,225,238` and `review_context.dart`. |
| Decision history | `Symbols.history` | Workbench supporting pane |
| Copy identifier | `Symbols.content_copy` | Beside any `mono.identifier` or `mono.digest` |
| Zoom to region | `Symbols.zoom_in` | Image pane toolbar |
| Fit image | `Symbols.fit_screen` | Image pane toolbar |
| Rotate | `Symbols.rotate_right` | Image pane toolbar |
| Add region | `Symbols.add_box` | Region editor |
| Merge regions | `Symbols.merge` | Region editor |
| Delete region | `Symbols.delete` | Region editor |
| Reorder region | `Symbols.drag_indicator` | Region editor |
| Choose files | `Symbols.upload_file` | Intake |
| Take photograph | `Symbols.photo_camera` | Intake |
| Filters | `Symbols.filter_list` | Queue |
| Search | `Symbols.search` | Queue |
| Queue destination | `Symbols.inventory_2` | Navigation |
| Intake destination | `Symbols.add_a_photo` | Navigation |
| Sign out | `Symbols.logout` | App bar overflow |
| Back | `Symbols.arrow_back` | App bar. On iOS, pair with the platform back swipe. |
| Product mark | `Symbols.biotech` | Sign-in and connection-setup screens only |

Rules. One icon means one thing across the whole product: `Symbols.refresh` is retry processing and
nothing else; reloading the queue uses a text button labeled `Reload`, not a second refresh glyph.
No icon-only control ships without a `tooltip` and a `Semantics(label:)`. No icon appears without a
label anywhere a decision is made; icon-only is permitted only in the image pane toolbar and the
app bar, where the tooltip carries the name.

---

## 7. Atomic inventory

Stages follow Brad Frost: atoms are the smallest useful pieces, molecules are small groups with one
job, organisms are distinct interface sections, templates are page-level structures without real
content, and pages are templates with real content
(<https://atomicdesign.bradfrost.com/chapter-2/>).

### 7.1 Atoms

`lib/src/ui/atoms/`

| Atom | What it is |
|---|---|
| `SymbolIcon` | `Icon` wrapper applying the section 6 axis defaults. The only way an icon enters the tree. |
| `MonoText` | Text in one of the five `mono.*` roles. Takes an enum, not a `TextStyle`. |
| `NumericText` | Text with `FontFeature.tabularFigures()` applied. |
| `AbstentionMark` | Icon plus word for Unknown, Unreadable, Not present, Unmeasured. |
| `Hairline` | 1dp `outlineVariant` divider, inset-aware. |
| `Boundary` | 1dp `outline` border decoration. |
| `FocusRingDecoration` | The 5.8 spec as a reusable `ShapeDecoration`. |
| `RiskBar` | One of three segments. Filled or empty. Never rendered alone. |
| `ProgressRing` | Determinate and indeterminate. Respects reduced motion. |
| `KeyCap` | A keyboard shortcut glyph in `mono.identifier` on `surfaceContainerHigh`. |
| `CopyButton` | 48dp target, `Symbols.content_copy`, confirms in a snackbar. |
| `Scrim` | 40% black light, 60% black dark. |
| `Gutter` | The pane padding widget. Enforces "one gutter per pane". |

### 7.2 Molecules

`lib/src/ui/molecules/`

| Molecule | Anatomy |
|---|---|
| `StatusChip` | `SymbolIcon` + label + 1dp `content` border + `fill`. Optional trailing count. `radius.xs`. |
| `EvidenceSource` | `SymbolIcon` + source name + relative timestamp + optional model version in `mono.identifier`. |
| `DiffRun` | One run of `DiffText`. Carries marker, style and its own `Semantics`. |
| `MetaPair` | Label in `labelMedium` `onSurfaceVariant` over value in `bodyMedium`. |
| `IdentifierRow` | `MonoText(identifier)` + `CopyButton`. |
| `PhaseLine` | Phase name + `ProgressRing` + elapsed time. |
| `SectionHeader` | `titleLarge` + optional count + optional single trailing action. |
| `SkeletonRow` | Three `surfaceContainerHigh` bars at 60%, 40% and 80% width. No shimmer. |
| `InlineError` | `Symbols.error` + message + retry action, wrapped in `Semantics(liveRegion: true)`. Keeps the pattern already correct at `main.dart:227` and `workspace.dart`. |
| `EmptyState` | 40dp icon + `titleMedium` + one sentence + at most one action. |
| `ConfidenceNote` | Value + the word `uncalibrated` when uncalibrated. Never renders a bare number. |
| `KeyboardHint` | `KeyCap` sequence + one verb. Desktop and web only. |
| `RegionChip` | Region index + `StatusChip` at `labelSmall`. |

### 7.3 Organisms

`lib/src/ui/organisms/`. States listed as: default, hover, focus, pressed, disabled, loading,
error, empty, selected.

**`QueueRow`**
Anatomy: 56dp thumbnail, specimen identifier in `mono.identifier`, one-line plain-language reason,
`StatusChip`, age in `bodySmall`, `Symbols.chevron_right`.
States: default `surfaceContainerLow`; hover `onSurface` 8%; focus ring per 5.8; pressed 10%;
disabled not applicable, rows are always openable; loading `SkeletonRow`; error the row is replaced
by `InlineError` with a retry; empty the list shows `EmptyState`; selected `primaryContainer` fill
plus a 3dp `primary` leading bar.
Responsive: compact stacks the reason under the identifier at 72dp; medium and up put them on one
line at 64dp or 56dp; at expanded and large the row is a two-column grid so status and age align
into columns.

**`ReadingCard`**
Anatomy: `EvidenceSource` header on `secondaryContainer`, literal transcription in `mono.literal`,
per-character `DiffText` overlay toggle, footer with `ConfidenceNote` and a `View raw` trigger.
States: default `surfaceContainer` at level 0; hover no change, the card is not clickable as a
whole; focus applies to the interactive children only; pressed not applicable; disabled the whole
card dims to `disabled.content` when the record is a historical read-only revision; loading two
`SkeletonRow`s; error `InlineError` inside the card body; empty renders `AbstentionMark` for
Unreadable with the model's stated reason; selected a 2dp `primary` border when the reviewer has
picked this reading as the supported one.
Responsive: at expanded and larger the two model cards sit side by side; below 900 they stack, and
the diff toggle moves into the section header so it is not duplicated.

**`FieldRow`**
Anatomy: field name in `labelMedium`, with the value's layer ("As written", "Settled" or "Derived
from …", UI.md T2.3 part four) as the row's secondary line; three stacked layers, Literal in
`mono.literalDense`, Parsed
in `bodyMedium`, Normalized in `bodyMedium` or `mono.identifier`; an `EvidenceSource` per layer; a
trailing `Symbols.edit` action. From the processing thread (UI.md T2.3): when no single reading was
chosen, Literal lists each reader's text under its source in secondary `bodySmall`, each label's
text first naming its label when the field spans labels, and an entry whose reading settled the
value ends by saying so; a Literal settled from a reading it does not show carries one secondary
line per such reading under its texts, naming the reading and, when the field spans labels, its
label; a Parsed value whose century a rule set carries one secondary line saying so;
and the authority line becomes one line per source, naming how it bears on the value.
States: default flush inside the card, `radius.none`; hover `onSurface` 8% across the full row;
focus ring around the row; pressed 10%; disabled edit action uses `disabled.content` and a tooltip
naming the server reason; loading the three layers are `SkeletonRow`s; error the row keeps its
layers and appends `InlineError`; empty each missing layer shows an `AbstentionMark`, never a blank;
selected 3dp `primary` leading bar while its `ReasonSheet` is open.
Responsive: compact collapses Parsed and Normalized behind a `Show interpretation` disclosure and
always shows Literal; medium and up show all three.

**`RegionOverlay`**
Anatomy: a stroked rectangle over the image with a corner label badge carrying the region index.
States: default 2dp `region.overlay` with casing; hover 3dp; focus the 5.8 ring plus casings;
pressed 3dp plus 10% white fill; disabled 1dp at 50% for regions excluded from processing; loading
regions are not drawn until geometry arrives, and the image pane shows an indeterminate
`ProgressRing`; error the overlay draws in `state.blocked` oxide with `Symbols.block` in the badge;
empty the image pane shows `EmptyState` "No label regions detected"; selected 3dp
`region.selected` with a `#101311` casing on both sides.
Responsive: the badge moves inside the box below 64dp box width, and disappears below 32dp, where
the region is addressable only from the region list.

**`AuthorityCandidateCard`**
Anatomy: `tertiaryContainer` header with `Symbols.menu_book` and the authority name; candidate name;
matched fields as `MetaPair`s; a match-quality `StatusChip`; a `Select` action; a
`View authority record` external link.
States: default level 0 on `surfaceContainer`; hover 8%; focus ring; pressed 10%; disabled
`Select` disabled with a tooltip when the record is not editable; loading three `SkeletonRow`s;
error `InlineError` with retry inside the list; empty `EmptyState` "No authority candidates
returned" with the query that was run; selected 2dp `tertiary` border plus a `Selected` chip.
Responsive: below 700 the matched fields become a two-line list; at expanded and larger they lay out
as a two-column definition grid.

**`RiskMeter`**
Anatomy: three `RiskBar` segments, the level word, the `uncalibrated` qualifier when uncalibrated,
and a mandatory list of component rows, each a `MetaPair` naming the contributing signal and its
value.
States: default all of the above; hover no change; focus ring when the component list is
collapsible and focused; pressed not applicable; disabled not applicable; loading `SkeletonRow`s for
the components and no bars, because bars without components are forbidden; error the meter is
replaced by `InlineError`; empty if the server returns no components the meter renders
`AbstentionMark` for Unmeasured and no number; selected not applicable.
Responsive: components collapse to a `Show components` disclosure below 600, expanded by default.
Constructor asserts `components.isNotEmpty`. This is the structural fix for `risk_assessment.dart:30`.

**`ReasonSheet`**
Anatomy: title naming the action; a diff of exactly what will change, rendered with `DiffText`; a
reason text field with a character counter; a `Cancel` and a filled `Confirm`.
States: default `Confirm` disabled until the reason is non-empty; hover and pressed standard;
focus the field is autofocused, focus order is field then Cancel then Confirm; disabled `Confirm`
uses `disabled.content` and a `Semantics(hint:)` naming the reason; loading `Confirm` shows an
inline `ProgressRing` and both buttons disable; error `InlineError` above the actions, the sheet
stays open and the typed reason is preserved; empty not applicable; selected not applicable.
Responsive: a modal bottom sheet at `radius.lg` below 600, a constrained dialog at 480 wide and
`radius.md` at 600 and above.

**`EnvironmentBanner`**
Anatomy: full-bleed band, `Symbols.science`, one short sentence, `radius.none`, no dismiss control.
States: only default and focus, and focus only on the `What this means` link.
Responsive: text wraps to two lines below 480; never truncates. Replaces
`workspace.dart:600-612`, including its em-dash.

**`UploadItem`**
Anatomy: thumbnail, filename in `mono.identifier`, local quality measurements as `MetaPair`s,
server preflight result as a `StatusChip`, determinate `ProgressRing`, cancel action.
States: default queued; hover 8%; focus ring; pressed 10%; disabled cancel disabled once the
transfer commits; loading the ring is determinate with a byte count; error `state.blocked` chip plus
`InlineError` with a retry, the item stays in the list; empty not applicable; selected not
applicable.
Responsive: compact is a two-line row with the ring as a trailing 24dp indicator; medium and up put
the measurements in a trailing column.

**`RecordActionBar`**
Anatomy: one filled primary action, up to two outlined secondary actions, an overflow menu, and a
left-aligned `StatusChip` showing the record's current disposition.
States: default; hover and pressed standard; focus ring per control; disabled each control disables
independently with its own tooltip naming the server reason, preserving today's correct behavior;
loading the acting control shows an inline ring and the rest disable; error handled by `ReasonSheet`
or `InlineError` above the bar; empty not applicable; selected not applicable.
Responsive: sticky to the bottom of the content pane below 900 with a 1dp top `outlineVariant`
border; inline at the top of the content pane at 900 and above.

**`EvidenceDrawer`**
Anatomy: a `View raw` trigger, and a side sheet or bottom sheet containing `mono.code` JSON on
`surfaceContainerHighest`, with a copy control and a byte count.
States: default closed; hover and pressed on the trigger; focus ring on the trigger and on the
first focusable element inside; disabled when no raw payload was returned; loading a `SkeletonRow`
block; error `InlineError`; empty "No raw payload for this phase"; selected not applicable.
Responsive: bottom sheet below 900, right side sheet at 400 wide at 900 and above.
This is where every current `ExpansionTile` JSON dump goes.

**`HistoryEntry`**
Anatomy: timestamp, `EvidenceSource`, the action, the reason in `bodyLarge`, a `DiffText` of what
changed, and a revision number in `mono.identifier`.
States: default; hover 8%; focus ring; pressed 10%; disabled not applicable; loading `SkeletonRow`;
error `InlineError`; empty `EmptyState` "No decisions recorded yet"; selected 3dp `primary` leading
bar when the reviewer is viewing that revision's read-only record.
Responsive: the diff collapses behind `Show change` below 600.

**`FiltersSheet`**
Anatomy: grouped `FilterChip` sets by disposition, state, age and presence; a count of matching
records that updates live; `Clear all` and `Apply`.
States: default; hover, pressed, focus standard; disabled `Apply` disabled while the count is
loading; loading the count shows a small ring; error `InlineError` with retry, filters stay
selected; empty "No records match. Clear a filter."; selected chips use `secondaryContainer` plus a
`Symbols.check` leading icon, so selection is not color alone.
Responsive: bottom sheet below 900, persistent left panel at 320 wide at 1200 and above.
Adopts the iDigBio presence idea: every field group carries `Any`, `Present`, `Missing` chips.

**`QueueSummary`**
Anatomy: one row per disposition with a `StatusChip`, a `NumericText` count, and the age of the
oldest item; a separate line for `state.blocked` with the stage it is blocked at.
States: default; hover and pressed on each row, which applies the filter; focus ring; disabled not
applicable; loading `SkeletonRow`s; error `InlineError`; empty "This collection has no records
yet"; selected the row whose filter is active gets a 3dp `primary` leading bar.
Responsive: a vertical list below 900, a horizontal band of four cells at 900 and above.

**`SpecimenHeader`**
Anatomy: specimen identifier in `mono.identifier` with `CopyButton`, collection name, current
`StatusChip`, and revision in `mono.digest` behind a disclosure.
States: default and focus only.
Responsive: the collection name drops below 480.

**`SourceImagePane`**
Anatomy: `InteractiveViewer` on `surfaceContainerLowest`, region overlays, a toolbar of icon-only
controls, and a region list rail.
States: default; hover shows the toolbar at full opacity, otherwise 70%; focus ring around the
viewer, with arrow keys panning and plus and minus zooming; pressed pan; disabled the pane dims
when source access has expired and shows `InlineError` with `Refresh source access`; loading a
centered indeterminate `ProgressRing` on the matte; error the existing "Preview unavailable"
message becomes an `EmptyState` with a retry action, replacing the bare `Text` at
`workbench.dart:456-459`; empty "No source image for this specimen"; selected not applicable.
Responsive: two thirds of the width at 1000 and above, full width above the content at 900 and
below, with a minimum height of 320.

### 7.4 Templates

`lib/src/ui/templates/`

| Template | Structure |
|---|---|
| `AppShell` | `NavigationBar` below 600, `NavigationRail` from 600 to 1199, extended `NavigationRail` at 1200 and above. Holds the app bar, the `EnvironmentBanner` and the collection selector. |
| `ListDetailTemplate` | Single pane below 900 with a route push; list at 400 wide plus detail at 900 and above. |
| `WorkbenchTemplate` | `SourceImagePane`, content pane, sticky `RecordActionBar`, and an optional supporting pane for history at 1400 and above. |
| `IntakeTemplate` | Capture affordances at the top, then the upload list, then a summary footer. |
| `FocusedTaskTemplate` | Centered, 560 maximum width, one action. Sign-in, verification, connection setup. |

### 7.5 Pages

| Page | Template | Route |
|---|---|---|
| Sign in | `FocusedTaskTemplate` | `/sign-in` |
| Email verification | `FocusedTaskTemplate` | `/verify` |
| Connection setup | `FocusedTaskTemplate` | `/setup` |
| Queue | `AppShell` + `ListDetailTemplate` | `/collections/:key` |
| Specimen review | `AppShell` + `WorkbenchTemplate` | `/collections/:key/specimens/:id` |
| Region editor | `WorkbenchTemplate` in edit mode | `/collections/:key/specimens/:id/regions` |
| Decision history | supporting pane, or its own route below 1400 | `/collections/:key/specimens/:id/history` |
| Historical record | `WorkbenchTemplate`, read-only | `/collections/:key/specimens/:id/revisions/:n` |
| Intake | `AppShell` + `IntakeTemplate` | `/collections/:key/intake` |
| Not authorized | `FocusedTaskTemplate` | any |

Every page has a URL. A reviewer can send a colleague a link to a specimen. This is new; today
routing is by widget state.

---

## 8. Flutter implementation plan

### 8.1 File layout

```
lib/src/theme/
  tokens.dart             // raw primitives: hex constants, spacing ints, radii, durations. No Flutter types beyond Color.
  color_schemes.dart      // lightColorScheme, darkColorScheme: fromSeed then .copyWith on every role
  semantic_colors.dart    // SpecimenColors extends ThemeExtension<SpecimenColors>
  typography.dart         // specimenTextTheme(Brightness) + SpecimenTypography extends ThemeExtension
  spacing.dart            // SpecimenSpacing + SpecimenShape extend ThemeExtension
  icons.dart              // SpecimenIconography: disposition/state/evidence -> (IconData, String label, double fill)
  component_themes.dart   // ChipThemeData, CardThemeData, InputDecorationTheme, ButtonThemes, NavigationRailThemeData, DialogThemeData, BottomSheetThemeData, MenuThemeData, DividerThemeData, IconThemeData, SnackBarThemeData, TooltipThemeData
  app_theme.dart          // AppTheme.light / AppTheme.dark, assembling all of the above
```

`tokens.dart` is the only file in the repository allowed to contain a `Color(0x...)` literal.

### 8.2 The product token extension

`ThemeExtension` requires `copyWith` and `lerp`, is registered through `ThemeData.extensions`, and
is read with `Theme.of(context).extension<T>()`
(<https://api.flutter.dev/flutter/material/ThemeExtension-class.html>).

```dart
@immutable
class SpecimenColors extends ThemeExtension<SpecimenColors> {
  const SpecimenColors({
    required this.clearedContent,
    required this.clearedFill,
    required this.clearedOnFill,
    required this.needsReviewContent,
    // ... one triple per product token in 3.4
    required this.focusRing,
    required this.disabledContent,
    required this.disabledOutline,
  });

  final Color clearedContent;
  final Color clearedFill;
  final Color clearedOnFill;
  // ...

  static const light = SpecimenColors(
    clearedContent: Color(0xFF1A6D4F),
    clearedFill: Color(0xFFD3EFE1),
    clearedOnFill: Color(0xFF063D2A),
    // ...
  );

  static const dark = SpecimenColors(/* ... */);

  @override
  SpecimenColors copyWith({Color? clearedContent, /* ... */}) => SpecimenColors(
    clearedContent: clearedContent ?? this.clearedContent,
    // ...
  );

  @override
  SpecimenColors lerp(SpecimenColors? other, double t) {
    if (other is! SpecimenColors) return this;
    return SpecimenColors(
      clearedContent: Color.lerp(clearedContent, other.clearedContent, t)!,
      // ...
    );
  }
}
```

A `DispositionStyle` record bundles the triple plus the icon and label so a call site cannot mix a
color from one status with a label from another:

```dart
typedef DispositionStyle = ({Color content, Color fill, Color onFill, IconData icon, double fill01, String label});

extension SpecimenColorsX on BuildContext {
  SpecimenColors get tokens => Theme.of(this).extension<SpecimenColors>()!;
  SpecimenSpacing get space => Theme.of(this).extension<SpecimenSpacing>()!;
  SpecimenTypography get mono => Theme.of(this).extension<SpecimenTypography>()!;
  DispositionStyle dispositionStyle(String key) => /* switch over the 3.5 table */;
}
```

`StatusChip` takes a status key, never a color. That is what makes "status is never color alone"
mechanical rather than aspirational: there is no constructor parameter for a bare color.

### 8.3 How components read tokens

Three rules, all enforceable.

1. **No widget outside `lib/src/theme/` contains a color, size, radius or duration literal.** Every
   value comes from `context.tokens`, `context.space`, `Theme.of(context).colorScheme` or
   `Theme.of(context).textTheme`.
2. **No widget reads a `Color` for a status.** It reads a `DispositionStyle` and renders all of it.
3. **Component themes carry the defaults; call sites do not restyle.** `ChipThemeData`,
   `CardThemeData` and the button themes are set once in `component_themes.dart`. A call site that
   needs a different look needs a new component in `lib/src/ui/`, reviewed as such.

CI gate, added to the existing analyze and test steps:

```bash
# fails if any widget file carries a literal color
! grep -rnE 'Color\(0x|Colors\.[a-z]' apps/specimen_digitization/lib \
  --include='*.dart' | grep -v '/theme/tokens.dart'
```

### 8.4 Testing contrast in a widget test

`test/theme/contrast_test.dart`. Two layers.

**Layer one: the token table.** Pure Dart, no widgets, fast, and it fails on the exact pair.

```dart
double _channel(double c) => c <= 0.04045 ? c / 12.92 : math.pow((c + 0.055) / 1.055, 2.4).toDouble();

double luminance(Color c) =>
    0.2126 * _channel(c.r) + 0.7152 * _channel(c.g) + 0.0722 * _channel(c.b);

double contrast(Color a, Color b) {
  final la = luminance(a), lb = luminance(b);
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

void main() {
  for (final (name, scheme, tokens) in [
    ('light', AppTheme.light.colorScheme, SpecimenColors.light),
    ('dark', AppTheme.dark.colorScheme, SpecimenColors.dark),
  ]) {
    final surfaces = <String, Color>{
      'surface': scheme.surface,
      'surfaceContainerLowest': scheme.surfaceContainerLowest,
      'surfaceContainerLow': scheme.surfaceContainerLow,
      'surfaceContainer': scheme.surfaceContainer,
      'surfaceContainerHigh': scheme.surfaceContainerHigh,
      'surfaceContainerHighest': scheme.surfaceContainerHighest,
      'surfaceDim': scheme.surfaceDim,
      'surfaceBright': scheme.surfaceBright,
    };

    group('$name scheme', () {
      test('text roles clear 4.5:1 on every surface', () {
        for (final text in {'onSurface': scheme.onSurface, 'onSurfaceVariant': scheme.onSurfaceVariant}.entries) {
          for (final s in surfaces.entries) {
            expect(contrast(text.value, s.value), greaterThanOrEqualTo(4.5),
                reason: '$name ${text.key} on ${s.key}');
          }
        }
      });

      test('outline clears 3:1 on every surface', () {
        for (final s in surfaces.entries) {
          expect(contrast(scheme.outline, s.value), greaterThanOrEqualTo(3.0),
              reason: '$name outline on ${s.key}');
        }
      });

      test('every product content token clears 4.5:1 on every surface', () {
        for (final t in tokens.allContentColors.entries) {
          for (final s in surfaces.entries) {
            expect(contrast(t.value, s.value), greaterThanOrEqualTo(4.5),
                reason: '$name ${t.key} on ${s.key}');
          }
        }
      });

      test('every on-fill clears 4.5:1 on its fill', () {
        for (final pair in tokens.fillPairs) {
          expect(contrast(pair.onFill, pair.fill), greaterThanOrEqualTo(4.5),
              reason: '$name ${pair.name}');
        }
      });

      test('focus ring clears 3:1 on every surface', () {
        for (final s in surfaces.entries) {
          expect(contrast(tokens.focusRing, s.value), greaterThanOrEqualTo(3.0));
        }
      });
    });
  }
}
```

**Layer two: rendered screens.** Flutter's own guideline matchers catch what the table cannot,
namely a widget that composed two token colors in a pair we did not anticipate.

```dart
testWidgets('queue meets contrast and target guidelines', (tester) async {
  for (final mode in [ThemeMode.light, ThemeMode.dark]) {
    await tester.pumpWidget(TestApp(themeMode: mode, child: const QueuePage()));
    await tester.pumpAndSettle();
    await expectLater(tester, meetsGuideline(textContrastGuideline));
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(iOSTapTargetGuideline));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  }
});
```

Run layer two against Queue, Specimen review, Intake, Region editor and History, in both modes.
`textContrastGuideline` checks 4.5:1 for normal text and 3:1 for large text, matching SC 1.4.3
(<https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html>).

### 8.5 Migration order

Each step keeps `flutter analyze` and `flutter test` green and is independently shippable.

| Step | Change | Files touched | Done when |
|---|---|---|---|
| 1 | Add `lib/src/theme/` with `tokens.dart`, `color_schemes.dart`, `semantic_colors.dart`. No screen changes. | new files | `contrast_test.dart` layer one passes |
| 2 | Wire `theme`, `darkTheme` and `themeMode: ThemeMode.system` in `MaterialApp`. Delete `scaffoldBackgroundColor: 0xfff4f6f3` (`main.dart:107`), the inline `ColorScheme.fromSeed` (`main.dart:108-111`) and `AppBarTheme.backgroundColor: 0xfff4f6f3` (`main.dart:122`). | `main.dart` | The app renders in both modes with no visual regression in light |
| 3 | Add the CI grep gate from 8.3, allowlisting the files not yet migrated, and shrink the allowlist in every later step. | CI config | Gate is green |
| 4 | Replace the four disposition literals in `_color()` (`workspace.dart:303-306`) with `context.dispositionStyle(...)`, and promote the leading icon at `workspace.dart:420-426` to a `StatusChip`. | `workspace.dart` | Deferred is clay, not lavender; status carries icon plus word |
| 5 | Replace `EnvironmentBanner` (`workspace.dart:600-612`), removing its em-dash. | `workspace.dart` | Banner reads from tokens, no dash characters |
| 6 | Replace the remaining literals: `workbench.dart:454` `0xffe7ebe7` matte, `:544` `Colors.amber`, `:551` `Colors.black87`, `:555` `Colors.white`, `:672` `0xffffe7a3`; `region_editor.dart:133` `Colors.amber`. `large_record.dart:114` already reads `colorScheme.error` and needs no change. | `workbench.dart`, `region_editor.dart` | Grep gate allowlist is empty for colors |
| 7 | Add `google_fonts`, bundle the font assets, register the OFL license, set `allowRuntimeFetching = false`, add `typography.dart` and wire `textTheme`. | `pubspec.yaml`, `main.dart`, new files | All text renders in IBM Plex Sans; `mono.*` roles available |
| 8 | Add `spacing.dart` and `component_themes.dart`. Replace literal `EdgeInsets` and `SizedBox` values file by file, starting with `workspace.dart` and `workbench.dart`. | all screens | Grep gate extended to `EdgeInsets.all(` with a numeric argument |
| 9 | Swap `Icons` for `Symbols` and add `icons.dart`. Set `IconThemeData` grade -25 in dark. | all screens, `pubspec.yaml` | No `Icons.` references remain |
| 10 | Build atoms and molecules. Replace the ad hoc status containers in `workspace.dart`, `workbench.dart`, `operational_panel.dart` and `review_context.dart` with `StatusChip`. | new files plus screens | One status chip implementation |
| 11 | Build organisms. `RiskMeter` first, because it changes `risk_assessment.dart`'s contract. Then `EvidenceDrawer`, which retires the JSON `ExpansionTile`s. | new files plus screens | `RiskMeter` asserts on empty components; no raw JSON in a primary surface |
| 12 | Templates and routing. | new files plus `main.dart` | Every page in 7.5 has a URL |

Steps 1 through 3 are sequential. Steps 4 through 6 can run in parallel with 7. Steps 10 through 12
depend on everything before them.

### 8.6 `pubspec.yaml` changes

```yaml
dependencies:
  google_fonts: ^8.2.1
  material_symbols_icons: ^4.2960.0

flutter:
  assets:
    - assets/google_fonts/
```

Verify the resolved versions against the Flutter 3.38.5 and Dart 3.10.4 constraints before merging;
this repository already carries a `dependency_overrides` entry for `firebase_core_web` because of a
toolchain mismatch, so version resolution is not assumed to be free.

---

## 9. Do and do not

| Do | Do not |
|---|---|
| Read every color from `Theme.of(context).colorScheme` or `context.tokens`. | Write `Color(0x...)` or `Colors.amber` in a widget. `workbench.dart:544` and `region_editor.dart:133` are the current violations. |
| Render a status as `StatusChip`, which takes a status key and produces icon plus word plus color. | Pass a bare `Color` to anything that displays state. |
| Give every abstention its own icon and word in the slot a value would occupy. | Render a missing value as an empty string, a dash, or a zero. |
| Show a risk total only inside `RiskMeter`, beside the components that produced it. | Print "Risk: 62 / 100" as text, as `risk_assessment.dart:30` does today. |
| Use `outline` for any border a user must be able to find. | Use `outlineVariant` for a boundary. It measures 1.26:1 to 2.13:1 and is decorative only. |
| Separate surfaces with a tone step plus a 1dp hairline. | Add a shadow, or let `surfaceTintColor` blend `primary` into a panel. |
| Draw the focus ring 2dp outside the component with a 2dp surface-colored gap. | Draw the ring flush against a filled button. It measures 1.42:1 against `primary` and fails SC 2.4.13. |
| Give every interactive element a 48x48 hit box regardless of its visual size. | Let a region overlay's tap target shrink to the label's true bounding box. |
| Set literal transcription in JetBrains Mono with `liga` and `calt` disabled. | Set a verbatim transcription in a proportional font, or leave code ligatures on. |
| Apply `FontFeature.tabularFigures()` to every identifier, count and coordinate. | Let digits reflow between rows so a changed digit moves position. |
| Keep `fill: 0` on Material Symbols and reserve `fill: 1` for a settled disposition and a selected nav destination. | Use fill as an emphasis knob, or animate it. |
| Put raw JSON behind `EvidenceDrawer` with a `View raw` trigger. | Make an `ExpansionTile` of `JsonEncoder.withIndent` output a primary way to read evidence, as `audit_history.dart:125` does today. |
| Show the change and the reason field in the same surface as the confirm control. | Open a confirmation dialog that restates the action in prose without showing the diff. |
| Let density change padding and row height. | Let density change a hit box. |
| Cap saturated elements in one viewport at three. | Color a card header, its border, its chip and its icon all in the same accent. |
| Give a disabled control `outline` color, a tooltip and a `Semantics(hint:)` naming the server reason. | Use Material's 38% disabled opacity on a control whose disabled state is information. |
| Use one icon for one meaning across the whole product. | Reuse `Symbols.refresh` for both "retry processing" and "reload the list". |
| Ship both light and dark from the same token table, tested by the same contrast test. | Treat dark mode as an inversion done later. |
| Keep the source image on screen while a field is edited. | Put the image behind a tab alongside Readings and Fields. |
| Write "Processing blocked" with `Symbols.block` in oxide. | Show an operational failure in the same visual language as a final queue. |
| Use a hyphen, comma, colon or period. | Use an em-dash or an en-dash anywhere, including in these tables. |
