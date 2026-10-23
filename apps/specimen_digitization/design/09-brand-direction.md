# 09. Brand direction: Specimen Digitization

Status: active implementation guidance, updated 2026-10-22. The owner's
`SD_brand.png` is the visual authority. The current scope and acceptance
contract are in [15-design-system-standard.md](15-design-system-standard.md).
That reference and 15 supersede conflicting appearance guidance in older
versions of this document, 03 and 14. Historical screenshots and verification
reports are evidence of earlier builds, never a palette to restore.

Untitled UI supplies the reference standard for coverage, component anatomy,
variants and care. It does not supply this application's colours or identity.
Use the owned `specimen_ui` Flutter package on every supported platform.

## 0. Why a component system

A coherent interface needs more than repainting Material defaults. The owned
components share semantic roles, label and supporting-text slots, controlled
state, accessible focus, keyboard operation and predictable responsive fit.
[10-component-library.md](10-component-library.md) describes the inventory;
[11-fit-and-scale.md](11-fit-and-scale.md) governs available space and text.

## 1. The reference, in words

Obsidian typography on warm Paper. Mist separates quiet surfaces. Iris is the
secondary brand colour. The Amber-to-Iris gradient is the hero: a deliberate
brand region on an introduction, welcome or empty-state composition. The
working interface stays legible, with enough spacing to let photographic
evidence and the reviewer's next action lead.

The source image's icon-style suggestions are not the interface icon system.
Interface icons remain Phosphor. The existing launcher mark's geometry is
retained while its palette follows this contract.

## 2. Principles that decide arguments

1. Evidence stays neutral. No coloured overlay, gradient, blur or decorative
   field changes a photograph or label crop. A tint on evidence changes data.
2. The gradient has a named role. Use `UiBrandHero` or `UiBrandAccent`; copy and
   actions sit on a separate solid surface. Never put body text directly over
   a gradient or use a decorative colour to imply a record's status.
3. Iris provides secondary emphasis. Use `ui.brand.secondary.content` for text
   and meaningful glyphs, and its matching fill/on-fill pair for containers.
   The exact Iris seed alone is not a universal foreground on light paper.
4. Labels and icons carry state meaning. Classification does not earn a new
   colour. Processing and external references use Iris; model observations
   and deferred work use neutrals. Success, attention and blocking outcomes
   retain functional green, warm amber and red.
5. Behaviour adapts while identity stays consistent. Safe areas, input methods,
   navigation gestures and text selection follow the platform. Colour, type,
   icons, component anatomy and interaction states come from shared tokens.

## 3. Colour

`packages/specimen_ui/lib/src/foundation/palette.dart` is the only Flutter
colour-value table. `UiColor` supplies functional roles; `UiBrandColors`
supplies brand roles through `context.ui.brand`. The asset generator reads
BrandPalette from that same file, so it cannot carry a second stale palette.

### 3.1 Ground and ink

| Role | Light | Dark |
| --- | --- | --- |
| Ground | Paper `#FAF9F6` | Obsidian `#0E0E11` |
| Solid paper | `#FFFFFF` | `#19191E` |
| Photograph matte | `#FFFFFF` | `#25252B` |
| Principal ink | Obsidian `#0E0E11` | Paper `#FAF9F6` |
| Supporting ink | `#494950` | `#C4C4CC` |
| Tertiary and disabled content | `#64646E` | `#AEAEB8` |
| Decorative hairline | Mist `#E6E6EA` | `#36363E` |
| Actionable boundary | `#82828C` | `#858590` |

A hairline is decorative separation. A control that needs a findable edge
uses `boundary`. Disabled reasons remain readable; they are not faded text.

### 3.2 Brand regions and compatibility fields

Exact seeds: Obsidian `#0E0E11`, Paper `#FAF9F6`, Amber `#F5A45B`, Iris
`#7B61FF`, Mist `#E6E6EA`. The hero gradient runs from Amber to Iris.
`UiBrandHero` places a decorative region above a solid text/action panel;
`UiBrandAccent` has no content slot. Neither encodes application data.

Runtime themes suppress decorative sky placements. The legacy field API is
source compatible, but every slot now resolves to Amber, Iris or Mist at low
opacity. New callers and the catalog use `ui.field.brandFields`, with the
canonical names `amber`, `iris` and `mist`. Historical names are aliases,
not additional hues or an invitation to revive former backdrops.

### 3.3 Surfaces and glass

Working surfaces use solid `paper`. `GlassSurface` and `FieldLayer` retain
compatibility APIs, but the standard theme has `GlassQuality.off` and no sky
placements. Repeated rows, chips and cells are solid. Evidence receives no
blur or brand wash. See [14-enterprise-surface-alignment.md](14-enterprise-surface-alignment.md).

### 3.4 Secondary emphasis and the mark

The exact Iris seed is `ui.color.accent`; Obsidian is `onAccent`. Their pair
clears 4.5:1. Accessible secondary text uses derived Iris content:
`#5B46C4` in light mode and `#B7A8FF` in dark mode. `ui.brand.secondary`
binds each content role to the correct container fill and on-fill role.

### 3.5 Functional states

| Family | Meaning |
| --- | --- |
| Green | Cleared, human affirmation, low risk, added-value marker |
| Warm amber | Needs review, attention, medium risk, changed-value marker, synthetic-environment notice |
| Red | Blocking or destructive outcome, high risk |
| Iris | Processing and external-reference emphasis |
| Neutral | Model observation, deferred work, unchanged content |

Never remove the label and Phosphor icon because two states share a colour.
An authority match does not imply human approval. A process colour does not
change Queue membership or final disposition. Risk indicators retain their
uncalibrated caveat. Image-region strokes keep their two-tone casing so they
remain visible against arbitrary photographs.

### 3.6 Focus and selection

Focus uses a mode-aware monochrome ring, with a two dp stroke and two dp gap.
Text selection is a neutral tint. Focus, selected, hover, pressed and disabled
states remain distinct without relying only on hue.

### 3.7 Contrast and regression checks

Normal text, disabled reasons and meaningful glyphs clear 4.5:1. Findable
edges and focus rings clear 3:1. Status text is checked on its own fill and on
all supported surfaces. The composite test also checks the retained field and
glass compatibility recipes. Decorative hairlines remain below the edge floor.

`test/foundation/brand_test.dart` checks the exact identity seeds, derived
secondary contrast and the small family count. It rejects the removed
fluorescent yellow-green hue family in the palette and its old source values.
Application asset checks cover generated launcher, splash and browser artwork.
Old screenshot goldens are not silently regenerated as proof of acceptance.

## 4. Typography

### 4.1 The family and how it ships

The brand reference names Söhne. No licensed Söhne font is bundled. Geist is
the explicit implementation fallback; it is not presented as Söhne. Geist and
Geist Mono are bundled package assets with their SIL OFL licences. No runtime
font fetching is permitted. The Google sign-in button retains its separately
scoped provider-prescribed face and colours.

### 4.2 The scale

`UiType.standard` owns the scale. Display roles are 40/32/24 dp; headings
24/20/16 dp; reading text 17/15/13 dp; labels 13/12 dp. Hierarchy uses weight,
spacing and size. Text uses the user's scaler and grows its container.
Identifiers and code use Geist Mono; verbatim roles disable ligatures.
Counts and changing measurements use tabular figures. Do not shrink text to
force it into a control.

### 4.3 The Material bridge

`UiThemeData.toTextTheme()` and `toColorScheme()` derive Material's carrier
values from owned tokens. Product components read `context.ui`; the bridge
exists for infrastructure such as editable text and selection. `UiTheme`
publishes the default text style for widgets and overlays.

## 5. Shape

Use shared shape tokens: sheets/dialogs 16 dp; cards, fields and inner
surfaces 8 dp; table cells, evidence regions and structural planes 0 dp.
Capsules belong to intrinsically rounded forms such as switches and radios.
Superellipse helpers own rounded geometry. Evidence pixels are never hidden
under a decorative corner. Hairline/boundary strokes are 1 dp, emphasis and
focus 2 dp, and the diff/selection bar 3 dp.

## 6. Spacing and density

Structural spacing follows an eight dp grid with a four dp optical half step.
Density follows input modality, not an operating-system check. Touch controls
are 48 dp high; pointer controls may look 40 dp high while retaining 48 dp
hit targets. Standard gutters and internal padding are 16 dp. A change in
text size can grow a control beyond its resting height.

## 7. Iconography: Phosphor

All interface glyphs come through `UiIcons`. Regular weight is the default;
fill identifies settled disposition and the current navigation destination.
Decorative glyphs may use light weight at display size. Standard sizes are
16, 20, 24 and 40 dp. A glyph inherits its adjacent text colour unless a
semantic role requires otherwise. One meaning has one registered icon.
The reference sheet's icon experiments do not replace Phosphor.

## 8. Motion

Use `MotionTokens` and [04-motion-and-microinteractions.md](04-motion-and-microinteractions.md).
Reduced motion remains authoritative. Essential state changes remain visible
without motion. Brand gradients are static; no drifting field, animated blur,
parallax or decorative pulse is added. Primary actions cannot submit twice
while busy.

## 9. The retained mark and app icon

The existing pin geometry remains: 24 dp disc, 16 dp pin, 2 dp shaft, 5 dp
head, with the whole pin one dp above the geometric centre. The pin's box is
y=3 through y=19, head centre y=5.5 and shaft end y=18 before its round cap.
The disc is Iris; the pin is Obsidian. The monochrome version reads the
mode's paper/ink roles in Flutter.

The app icon is a superellipse at exponent five. The pin is 44 percent of
the visible icon frame: the central 66 percent of Android adaptive art and
80 percent of maskable web art. Android 12 splash art places the disc inside
the central two thirds so the platform mask preserves its head and tip.
These are compatibility geometries, not a reinterpretation of the supplied
brand logo. The mark does not animate or rotate.

`assets/brand/pin.svg`, `foundation/mark.dart` and
`tool/brand/render_mark.py` describe the same geometry.
[The brand asset README](../assets/brand/README.md) documents regeneration and
its platform checks. Native/browser backgrounds use the same Paper and
Obsidian seeds as Flutter.

## 10. Dark mode

Dark mode has explicit semantic roles. It is not an inverted screenshot.
Obsidian is the canvas; elevated surfaces remain neutral; text and secondary
Iris emphasis use lighter accessible relatives. The hero gradient keeps the
same identity endpoints. Both modes receive the same behavioural, fit and
contrast checks.

## 11. Rejected treatments

- The former fluorescent yellow-green palette, including in optional fields,
  launcher artwork, splash screens or browser icons.
- Additional decorative blue, teal, clay, rose or mint families to distinguish
  classifications that already have labels and icons.
- Body text on gradients, tinted evidence, decorative blur or stacked glass.
- New raw colour or geometry literals in screens.
- Platform icon substitutions, runtime fonts or an unlicensed Söhne asset.
- Screenshot replacement used to conceal an unexamined visual regression.

## 12. Implementation checklist

Use semantic tokens and real controls, document the state/size/slot axes,
exercise keyboard and screen-reader behaviour, and test at 320/390, 768 and
1180/1440 dp with 100/200 percent text and RTL. Preserve data, authentication,
upload and Queue semantics while improving presentation. Local catalog and
synthetic evidence do not establish production acceptance.
