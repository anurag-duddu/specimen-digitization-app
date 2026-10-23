# Enterprise surface alignment

Status: active surface guidance, updated 2026-10-22. The owner's `SD_brand.png`
and [15-design-system-standard.md](15-design-system-standard.md) govern brand
identity. [09-brand-direction.md](09-brand-direction.md) records the current
colour, type, icon and component application rules. This document governs
working surfaces; it does not prohibit the approved hero gradient.

## 1. Working surfaces

The application is a collection-work instrument. Its working canvas uses warm
Paper in light mode and Obsidian in dark mode. Panes, fields and tables use
solid neutral surfaces. Spacing, restrained edges and tonal steps establish
structure. Photographs, label crops, collection metadata and review decisions
remain the visual hierarchy.

The Amber-to-Iris gradient is a deliberate brand region on welcome,
introduction and empty-state compositions. Use `UiBrandHero` or
`UiBrandAccent`; readable copy and actions have a separate solid surface.
The gradient never tints evidence or communicates record state.

## 2. Fields

Runtime themes suppress `sky.home` and `sky.work`. `FieldLayer` therefore
resolves to the solid mode-aware ground. The legacy `decorativeFields` theme
argument remains accepted for source compatibility and does not reactivate
runtime placements.

The retained field recipes now contain only Amber, Iris and Mist. New catalog
code reads the canonical `ui.field.brandFields`; old field names are aliases,
not a second palette. No former backdrop may return by toggling a preference.

## 3. Glass and elevation

Standard themes use `GlassQuality.off`. Structural surfaces remain opaque;
menus, sheets, dialogs and action bars retain their edges without decorative
blur, highlight gradients or shadows. Retained quality preferences do not
make the standard recipes transparent. Repeated rows, cells and chips are
solid. Scrims explain modal relationships. Evidence is never blurred.

## 4. Shell

The shell uses neutral ground and the monochrome product mark. Navigation,
collection selection and account actions retain shared keyboard, semantics
and responsive behaviour. Compact headers use the workspace form of
`UiTopBar`, with solid paper and matching safe-inset treatment. The compact
tab bar covers the lower safe inset. Wider layouts adapt to available space
without changing component identity.

Brand regions can be composed within a screen when they help orientation;
never reintroduce a colourful atmosphere behind the whole working shell.

## 5. Invariants

- Ground, paper and photograph mattes are mode-aware neutral tokens.
- Status meanings are unchanged. Their colour families are consolidated as
  defined in 09 and 15; labels and Phosphor icons preserve distinctions.
- Geist and Geist Mono remain the bundled implementation faces. Söhne is
  identified as the unbundled brand reference, not silently substituted.
- Shared geometry, 48 dp targets, focus behaviour, density and text scaling
  apply across all supported platforms.
- Reduced motion remains authoritative; brand regions are static.
- Text and meaningful edges meet the existing WCAG contrast gates in both
  modes, including the retained compatibility recipes.

## 6. Evidence

Tests distinguish the neutral working shell from explicit hero components.
Routed application checks cover responsive navigation and inspect runtime
surfaces. Component tests exercise readable hero copy and operable actions at
narrow widths, larger text, RTL and both themes. Source and generated-asset
checks prevent the rejected palette returning outside Flutter. Historical
screenshots remain historical; new local renders are not live acceptance.
