# Applying the design system to the application

The application and Widgetbook consume the same `specimen_ui` package. A
catalog component is not complete evidence of a usable screen: inspect its
actual application composition, including the shell, data state and available
space. Changes to source take effect in both on rebuild; production and native
installations still require their normal release.

## Brand and hierarchy

- Use the owned ribbon mark in the workspace navigation. Phosphor supplies
  interface icons, never a substitute product logo.
- The Amber-Iris gradient introduces a workspace or an empty intake. Paper,
  Mist and Obsidian support the working surfaces; Iris identifies secondary
  selection. Do not reintroduce acid yellow or add decorative status colours.
- A specimen photograph remains evidence. Do not place gradients over it or
  sacrifice its working area for introductory content.

## Screen responsibilities

| Surface | Composition | Preserved behaviour |
| --- | --- | --- |
| Queue | Scrolling review heading, search, Iris active view, ruled records with available issue and update context; a branded introduction in the unused wide detail pane | Retained list position, selection, keyboard traversal, filters and direct record routing |
| Intake | Clear source choices before acquisition; a compact saved-batch heading and lazy photo grid afterwards; persistent submission and reachable selection commands | Private drafts, provider browsing, original-file recovery, inspection, retake, retry and explicit submission |
| Workbench | Dominant source canvas with a bounded Paper inspector, real record status and structured field groups | Source transforms, region selection, provenance, editing, review guard, record navigation and decision actions |

Counts describe the response actually loaded. Missing scores, thumbnails and
timestamps remain missing; a page layout must not invent them. Existing roles,
errors, loading and recovery states remain visible and actionable.

## Review loop

Use the production screen widgets in Widgetbook with deterministic synthetic
repositories. Mock transport and device acquisition, not page layout. Keep
preview navigation and dialogs inside the selected viewport and keep production
configuration and museum data out of catalog assets.

For every composition change, inspect phone and desktop, light and dark, and
200% text. Verify the constraints in `13-screen-composition.md`: one vertical
scroll owner per content region, reachable actions, visible primary work,
bounded chrome and no nested surface clutter. Review changed golden pixels and
semantics before updating the expected files. Required automated checks and an
independent review precede the protected web release; a physical Android check
then verifies the installed build and retained user state.
