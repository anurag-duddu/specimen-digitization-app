# Enterprise surface alignment

Status: **approved runtime direction, implemented 2026-09-23.** This document
supersedes the atmospheric field and default glass rules in 09 sections 1,
2.1, 2.2, 3.2, 3.3, 8 and 11. The underlying primitives remain available for
the component gallery and for a future explicitly reviewed use. Typography,
Phosphor icons, superellipse geometry, semantic status colours, density,
accessibility and reduced-motion requirements do not change.

## 1. Reference in words

The application is a formal collection-work instrument. Its canvas is a quiet
soft neutral. Working panes are white in light mode and use the established
neutral dark ramp in dark mode. Structure comes from spacing, thin hairlines
and small tonal steps. Evidence, collection metadata and decisions are the
visual hierarchy. The shell does not compete with them.

This rejects an atmospheric or consumer-product treatment in the runtime
application: no colourful backdrop, no decorative gradient, no glow, no
stacked translucent cards and no blur used merely to make chrome feel richer.

## 2. Fields

`UiFields` remains the only tokenized source for a radial field, and
`FieldPainter` remains the only gradient painter. Both runtime themes suppress
all `sky.home` and `sky.work` placements by default, so `FieldLayer` resolves
to the mode's solid `ground` colour.

An explicit `decorativeFields: true` is allowed only in the design-system
gallery or in a separately approved experiment. A product screen must not set
it locally. This keeps the former treatment inspectable without allowing an
ambient gradient to return by accident.

## 3. Glass and elevation

Both runtime themes default to `GlassQuality.off`. A `GlassSurface` therefore
draws as opaque `paper`, retains its thin edge, and omits blur, top-highlight
gradient and shadow. This is the normal form for shell chrome, action bars,
menus, sheets and dialogs.

Glass is an explicit hierarchy tool. A caller may opt a complete theme into
`full` or `reduced` quality only when blur explains a real overlay relationship
that solid paper and a scrim cannot. If enabled, floating and modal shadows use
the restrained 4 dp and 8 dp offsets in the token table. Repeated rows, cells
and chips remain ineligible.

## 4. Shell

The application shell uses the solid neutral `FieldLayer` result and the
monochrome product mark. Navigation, collection selection and account actions
retain their existing layout, keyboard, semantics and responsive behavior.
The shell adds no screen-specific component family.

## 5. Invariants

- `ground`, `paper` and `matte` stay mode-aware and tokenized.
- Semantic status triples are unchanged and remain the only data-bearing
  colour system.
- Geist, Geist Mono and Phosphor remain the shipped type and icon families.
- Spacing, touch targets and window-class changes continue to resolve from
  tokens. No local geometry is introduced by this alignment.
- Reduced motion remains authoritative. Removing the default field transition
  removes motion; it does not add a replacement transition.
- Text and meaningful edges keep the existing WCAG 2.2 contrast gates in both
  modes.

## 6. Evidence

The default-shell golden is captured at 390 by 844 and 1180 by 820, in light
and dark mode. The routed application test repeats the contract at 390 by 844
and 1440 by 900 and asserts that the runtime shell contains no `FieldPainter`
or `BackdropFilter`, uses `GlassQuality.off`, and draws the monochrome mark.
The primitive test separately proves that blur and decorative fields still
work only after an explicit opt-in.
