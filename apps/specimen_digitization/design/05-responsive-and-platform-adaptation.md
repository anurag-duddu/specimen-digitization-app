# Responsive and platform adaptation

This document specifies how the client adapts to window size, input device and
platform. It covers breakpoints, navigation, a screen-by-screen layout spec,
input modalities and shortcuts, platform conventions, web specifics, camera
capture, and the test matrix. Every value is a number an engineer can put in
code today.

Today the codebase already branches on width in three places, each with its
own ad hoc cutoff: `lib/src/workspace.dart:451` (`constraints.maxWidth >= 800`
switches `NavigationRail` vs `NavigationBar`), `lib/src/workbench.dart:988`
(`constraints.maxWidth >= 1000` switches source-image-beside-content vs
stacked), and `lib/src/workbench.dart:780` (`c.maxWidth >= 520` switches a
reading card to two columns). All three correctly key off `LayoutBuilder`
constraints rather than `Platform.isIOS`/`Platform.isAndroid` or a device
guess, which is the right foundation
([docs.flutter.dev/ui/adaptive-responsive/general](https://docs.flutter.dev/ui/adaptive-responsive/general),
["Choose UI based on available window size, not device type"]). The problem is
that 800, 1000 and 520 do not correspond to any named size class, so three
different parts of the same screen disagree about where "wide" starts. This
document replaces all three with one shared scale.

## 1. Size classes and breakpoints

Adopt Material 3's five width-based window size classes
([m3.material.io/foundations/layout/applying-layout/window-size-classes](https://m3.material.io/foundations/layout/applying-layout/window-size-classes)).
Width is always logical pixels (`MediaQuery.sizeOf(context).width` for a
whole-screen decision, or `LayoutBuilder`'s `constraints.maxWidth` for a
widget-scoped one), read at the moment of build, never cached, never derived
from `Platform.isIOS`, `defaultTargetPlatform` or a hardcoded phone/tablet
list.

| Class | Width (logical px) | Typical window | Rail/nav default |
|---|---|---|---|
| Compact | 0 to 599 | Phone portrait, iPad Slide Over, split view at 1/3 | Bottom `NavigationBar` |
| Medium | 600 to 839 | Phone landscape, small tablet portrait, iPad Split View 1/2 | Collapsed `NavigationRail` |
| Expanded | 840 to 1199 | Tablet landscape, foldable unfolded, iPad Split View 2/3 | Extended `NavigationRail` |
| Large | 1200 to 1599 | Small desktop window, iPad Pro landscape | Extended `NavigationRail` or `NavigationDrawer` |
| Extra-large | 1600+ | Wide desktop monitor, ultrawide | `NavigationDrawer` |

Add a single source of truth and use it everywhere the three ad hoc checks
above currently live:

```dart
// lib/src/layout/breakpoints.dart
enum WindowClass { compact, medium, expanded, large, extraLarge }

WindowClass windowClassOf(double width) {
  if (width < 600) return WindowClass.compact;
  if (width < 840) return WindowClass.medium;
  if (width < 1200) return WindowClass.expanded;
  if (width < 1600) return WindowClass.large;
  return WindowClass.extraLarge;
}

extension WindowClassQueries on WindowClass {
  bool get isCompact => this == WindowClass.compact;
  bool get isAtLeastMedium => index >= WindowClass.medium.index;
  bool get isAtLeastExpanded => index >= WindowClass.expanded.index;
  bool get isAtLeastLarge => index >= WindowClass.large.index;
}
```

Replace `workspace.dart:451`'s `wide = constraints.maxWidth >= 800` with
`windowClassOf(constraints.maxWidth).isAtLeastMedium` (600, not 800: with only
two navigation destinations there is no reason to wait for 800px to give the
rail its own column). Replace `workbench.dart:988`'s `wide =
constraints.maxWidth >= 1000` with `.isAtLeastExpanded` (840) as the pane
threshold; keep 1000 in mind only as the point where a 50/50 split stops being
cramped (see 3.5). Replace `workbench.dart:780`'s bespoke `c.maxWidth >= 520`
with a named constant (`_readingCardTwoColumnWidth = 520`) since it is a
within-card content decision, not a window size decision, and 520 is
deliberately below the compact/medium boundary; leave it as-is but name it so
the next reader does not mistake it for a fourth breakpoint system.

### Rule: window size, never device type

Flutter's own guidance states this as the central adaptive-design principle
([docs.flutter.dev/ui/adaptive-responsive/best-practices](https://docs.flutter.dev/ui/adaptive-responsive/best-practices),
"Avoid Hardware Type Checking": don't write `if (isTablet)`, write `if
(screenWidth > 600)`). The one legitimate device check in the codebase is
`intake.dart:431-434`, which gates the "Take photograph" button on `!kIsWeb &&
(defaultTargetPlatform == TargetPlatform.android || ... iOS)`. That is a
**capability** check (does this platform expose a camera through
`image_picker`), not a **layout** check, so it is the right kind of branch,
just not formalized. Flutter's adaptive docs recommend wrapping this kind of
decision in a named `Capability`/`Policy` type rather than an inline platform
test
([docs.flutter.dev/ui/adaptive-responsive/capabilities](https://docs.flutter.dev/ui/adaptive-responsive/capabilities)):

```dart
class DeviceCapabilities {
  const DeviceCapabilities();
  bool get hasSystemCamera =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);
}
```

This makes the check testable (inject a fake `DeviceCapabilities` in widget
tests instead of faking `defaultTargetPlatform`) and documents *why* the
branch exists, separate from any future width-based branch in the same
screen.

### Foldables

Don't lock orientation (both Android's large-screen guidelines and Flutter's
docs call this out;
[developer.android.com/docs/quality-guidelines/large-screen-app-quality](https://developer.android.com/docs/quality-guidelines/large-screen-app-quality)
requires apps to run full screen without letterboxing on every posture, and
`main.dart` and every screen file already omit any `SystemChrome.setPreferredOrientations`
call, so there is nothing to undo). A foldable in the half-opened state
exposes its hinge to Flutter as a `DisplayFeature` on
`MediaQuery.of(context).displayFeatures`
(`api.flutter.dev/flutter/widgets/MediaQueryData/displayFeatures.html`). Two
postures matter here:

- **Book posture** (vertical hinge, phone held like a book): treat the hinge
  as a wide gutter. In the queue's list-detail layout (3.2), if
  `displayFeatures` reports a vertical hinge, set the list-pane width to end
  exactly at the hinge's left edge and start the detail pane at the hinge's
  right edge, instead of using the fixed 360dp list width from 3.2.
- **Tabletop posture** (horizontal hinge, device half-folded like a tent): the
  workbench's sticky action bar (3.5) must not sit on top of the hinge. Read
  `displayFeature.bounds` and, when a horizontal `DisplayFeatureType.hinge` is
  present, pin the sticky action bar to the bottom of the *upper* half rather
  than the bottom of the full window.

Both behaviors are additive on top of the width-based layout in section 3;
nothing here changes what layout a given width gets, only where a hinge-aware
screen avoids placing controls. Source:
[developer.android.com/design/ui/mobile/guides/layout-and-content/postures-and-orientation](https://developer.android.com/design/ui/mobile/guides/layout-and-content/postures-and-orientation)
("don't place UI controls too close to a fold or hinge... allow for a wider
gutter"), applied through Flutter's own `displayFeatures` API rather than a
platform channel.

### iPad Split View, Slide Over and Stage Manager

None of these are device types; each just hands the app a narrower window.
iPad Slide Over and the narrowest Split View split are compact width; Split
View's wider split and a mid-size Stage Manager window are medium or
expanded; a maximized Stage Manager window on an iPad Pro is large. Apple's
multitasking guidance confirms the app should keep working at any width it is
given rather than assuming a minimum
([developer.apple.com/design/human-interface-guidelines/layout](https://developer.apple.com/design/human-interface-guidelines/layout)).
Because our breakpoints in section 1 already cover 0 to 1600+ continuously,
no iPad-specific branch is needed: the same `windowClassOf` call that handles
a resized desktop Chrome window handles a resized Stage Manager window. Verify
this at build time by resizing the app in the simulator across the Split View
snap points; do not special-case `TargetPlatform.iOS` in `windowClassOf` or
any layout that consumes it.

## 2. Navigation pattern per size class

| Class | Primary nav | App bar contents | Collection switcher | Account menu |
|---|---|---|---|---|
| Compact | Bottom `NavigationBar`, 2 destinations (Queue, Intake) | Title, refresh icon, sign-out icon | Tap the app bar title area to open a modal bottom sheet listing collections | Sign-out `IconButton` stays in the app bar (already true) |
| Medium | Collapsed `NavigationRail` (icon only, `labelType: NavigationRailLabelType.none`) | Same, plus the collection name shown as text next to the title | Same dropdown as today (`workspace.dart:629`), narrower | Sign-out icon in app bar |
| Expanded | Extended `NavigationRail` (`labelType: NavigationRailLabelType.all`, current behavior) | Collection dropdown moves out of its own full-width row into the app bar itself | `DropdownButtonFormField` inline in the app bar's `actions`, max width 280 | Replace the bare sign-out icon with a `PopupMenuButton` showing the display name and a "Sign out" item |
| Large / extra-large | `NavigationDrawer` (Material 3 standard, permanent, not modal: `api.flutter.dev/flutter/material/NavigationDrawer-class.html`) with the collection switcher as the drawer's header | Title only; everything else lives in the drawer header | Drawer header: collection name plus a `DropdownButtonFormField` below it | Drawer header: display name plus "Sign out" as a drawer footer item |

Material's own component guidance splits this the same way: compact windows
pair a navigation bar with a modal drawer only when there are more
destinations than a bar can hold; medium windows get a rail; large and
extra-large windows get the standard (permanent) drawer
(`m3.material.io/components/navigation-bar/specs`,
`m3.material.io/components/navigation-rail/guidelines`,
`m3.material.io/components/navigation-drawer/guidelines`). With exactly two
destinations we never need the modal drawer variant at compact: a bottom bar
alone is sufficient at every width below medium, and the two-destination
`NavigationBar` at `workspace.dart:587-600` does not need to change shape,
only its trigger width (600, not 800, per section 1).

`NavigationRail`'s collapsed and extended states are both already available
as constructor parameters; Flutter's own default `minWidth` is 72 and default
`minExtendedWidth` is 256
(`api.flutter.dev/flutter/material/NavigationRail-class.html`), so use those
defaults rather than inventing new rail widths. At the large/extra-large
switch to `NavigationDrawer` (fixed 360dp wide per its Material spec
default), because a permanent rail wastes horizontal space once the window is
wide enough to show the workbench's three panes (3.5) plus a rail plus an app
bar.

Today the collection switcher and the signed-in user's name are treated as a
single row that is always full width regardless of size class
(`workspace.dart:620-664`); the display name is only shown "`if (wide)`" at
the 800px cutoff (`workspace.dart:657-661`) and otherwise disappears with no
alternate placement, which means a signed-in operator on a phone has no way
to see which account they are using. Moving the display name into the
sign-out control (a labeled menu button, not a bare icon) at every size class
fixes that without new chrome.

## 3. Screen-by-screen layout spec

### 3.0 Shared primitives

Two structural inconsistencies recur across every dialog in the app and
should be fixed once, here, rather than per screen.

**Dialog width is inconsistent.** Four dialogs hardcode a `SizedBox` width
inside their `AlertDialog` content (`region_editor.dart:64` uses 680,
`evidence_panel.dart:93` uses 560, `review_context.dart:198` uses 560,
`search_filters.dart:59` uses 520), one form dialog uses 520
(`workbench.dart:124`, the field-correction/transcription-adjudication
dialog), and two more use no width constraint at all and simply size to
content (`workbench.dart:336-370`, the coverage/approval reason dialog, and
`workbench.dart:1058-1085`, the retry-reason dialog). The two unconstrained
dialogs will render at whatever width their content naturally wants, which
looks inconsistent next to the five sibling dialogs that are all
pixel-specific but mutually different. Replace all seven with three named
tokens:

```dart
class DialogWidths {
  const DialogWidths._();
  static const double narrow = 400;   // one or two fields, a single reason
  static const double standard = 480; // 3-6 fields, a picker plus a reason
  static const double wide = 640;     // multi-section forms (region editor)
}
```

Mapping: coverage/approval reason and retry reason both become `narrow` (400,
replacing "no constraint"); search filters, authority candidate selection and
the classification dialog become `standard` (480, replacing 520/560/560); the
field-correction/transcription-adjudication dialog becomes `standard` (480,
replacing 520); the region editor becomes `wide` (640, replacing 680). These
numbers are ours, not a Material 3 mandate; Material does not publish a fixed
dialog max-width table for Flutter, so pick the smallest width that avoids
wrapping the longest label in each dialog and hold every dialog in the app to
one of the three.

**Dialog vs. bottom sheet by size class.** At compact width, an `AlertDialog`
constrained to any of the widths above (400 to 640) will overflow a
360-to-599-logical-pixel-wide phone screen, forcing Flutter to shrink it and
leaving little room for the on-screen keyboard when a `TextFormField` is
focused. Below 600, every dialog in this document becomes a bottom sheet
instead:

```dart
Future<T?> showAdaptiveForm<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  required double width, // one of DialogWidths.*
}) {
  final compact = MediaQuery.sizeOf(context).width < 600;
  return compact
      ? showModalBottomSheet<T>(
          context: context,
          isScrollControlled: true,
          useSafeArea: true,
          builder: builder,
        )
      : showDialog<T>(
          context: context,
          builder: (context) => Dialog(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: width),
              child: builder(context),
            ),
          ),
        );
}
```

The region editor is the one exception: at compact it becomes a full-screen
route (`Navigator.push`, not a sheet), because direct manipulation of a
bounding box needs the whole screen (see 3.6).

### 3.1 Sign-in

`main.dart`'s `_ConnectionSetup` (maxWidth 560), `magic_link_screen.dart`
(maxWidth 440) and `email_verification.dart` (maxWidth 480) are three
different widths for what is functionally one flow (connect, sign in,
verify). This is a low-frequency, low-density screen; it does not need a
size-class branch. Unify all three to a single centered column, maxWidth 400
(`DialogWidths.narrow`), vertically centered inside a `SafeArea`, at every
window size from compact through extra-large. Do not add a second pane at
wide sizes: a marketing-style split screen would read as consumer chrome on
what the brief calls a scientific, evidentiary tool, and there is no
supporting content to put in a second pane.

### 3.2 Queue: list vs. list-detail

This is Material's list-detail canonical layout
([developer.android.com/develop/adaptive-apps/guides/canonical-layouts](https://developer.android.com/develop/adaptive-apps/guides/canonical-layouts)):
at compact and medium, show either the list or the detail, never both,
because the workbench itself needs at least 840dp to show its own two panes
(3.5) and there is no room left for a list beside it below that. At expanded,
the workbench can fit beside a list only if the workbench's internal split
also has room, so list-detail proper (list and workbench visible together)
starts at large (1200), where a 360dp list pane plus an 840dp expanded-class
workbench fit side by side.

| Class | Behavior |
|---|---|
| Compact, medium, expanded | Single pane. Tapping a `Card` in the queue (`workspace.dart:413-440`) pushes a full-screen route showing `ReviewWorkbench`; a `Back to queue` control returns. This is close to what `workspace.dart:491-556` already does today, except today it swaps `Column` children in place rather than pushing a route, so there is no back gesture, no browser URL change, and no way to deep link to a specimen (see section 6). Convert this to an actual pushed route. |
| Large, extra-large | List-detail. Left pane: the existing queue `ListView` content (`workspace.dart:308-447`) constrained to a fixed 360dp width. Right pane: `Expanded(child: ReviewWorkbench(...))`, no navigation push; selecting a different `Card` swaps the workbench's `specimen` in place (same `ValueKey` pattern already used at `workspace.dart:505`, so `ReviewWorkbench`'s internal state, like the open tab and zoom level, correctly resets per specimen). |

At every class, when the list is empty the existing empty-state card
(`workspace.dart:386-412`) is unchanged.

### 3.3 Filters

`SearchFilters` (`search_filters.dart`) is presently always an `AlertDialog`,
width 520, at every size (`search_filters.dart:56-106`). Split by class:

- **Compact:** modal bottom sheet, full width, `isScrollControlled: true`, so
  the fourteen fields in `searchFields` (`search_filters.dart:3-17`) scroll
  inside a sheet that can grow to near-full height rather than a dialog that
  has to shrink to fit a 360dp-wide phone.
- **Medium and above:** keep the `AlertDialog`, width updated to
  `DialogWidths.standard` (480, replacing 520).

There is no side-sheet variant here: Flutter's Material library has no
first-party side-sheet widget as of Flutter 3.38 (confirmed against
`api.flutter.dev`'s material library index; the closest built-ins are
`Drawer`/`NavigationDrawer`, which carry navigation semantics filters do not
need), so do not build one just for this dialog. A dialog is already the
right pattern once there is room for a modal to be legible; reserve custom
side-sheet construction for a future screen that actually needs a persistent
side panel, which the workbench does (3.5) and filters do not.

### 3.4 Intake

`intake.dart` has no `LayoutBuilder` anywhere: it is the one primary screen
that does not branch on width at all (confirmed: `grep -L LayoutBuilder`
across `lib/src/*.dart` lists `intake.dart`). Its single `ListView`
(`intake.dart:435-655`) stacks the capture card above the upload manifest at
every width, so on a tablet at a copy stand, an operator working through a
batch of dozens of photographs has to scroll away from the capture button to
check manifest status.

- **Compact:** unchanged, single column (capture card, then manifest list).
- **Medium and above:** two columns inside a `Row`. Left column, fixed 420dp:
  the capture card (`intake.dart:447-526`, sensitivity dropdown, "Choose
  files"/"Take photograph" buttons, the quality-confirmation checkbox).
  Right column, `Expanded`: the upload manifest (`intake.dart:550-632`) in
  its own scrollable list, so the manifest visibly fills up next to the
  button an operator is repeatedly pressing.

Camera capture itself becomes the custom full-screen flow in section 7 on
phone and tablet; see that section for what replaces the direct
`ImagePicker().pickImage(source: ImageSource.camera)` call at
`intake.dart:149-152`.

### 3.5 Workbench

This is the screen reviewers spend hours in, so get the pane math right
before anything else. `ReviewWorkbench.build` (`workbench.dart:953-1199`)
currently has one branch: `wide = constraints.maxWidth >= 1000` picks between
a `Row` of two `Expanded` children (source image, content) and a stacked
`Column` (`workbench.dart:1182-1188`). Replace the single cutoff with three
regimes:

| Class | Layout |
|---|---|
| Compact, medium | Stacked column (current `else` branch, unchanged): source image section (`_source()`, `workbench.dart:403-604`), then the record-status/context/tabs content (`workbench.dart:989-1146`). |
| Expanded (840-1199) | Two-pane `Row`: source image pane and content pane, each `Expanded` with `flex: 1` (50/50), matching current behavior but now triggered at 840 instead of 1000. The "Readings / Fields & evidence / History" selector (`workbench.dart:1156-1166`) stays as a three-way control above the content pane; convert it from `ChoiceChip`s in a `Wrap` to a single `SegmentedButton<int>` (Material 3's purpose-built widget for mutually-exclusive selection among 2-5 options, `api.flutter.dev/flutter/material/SegmentedButton-class.html`), which reads as one control instead of three separate chips that happen to be mutually exclusive. |
| Large, extra-large (1200+) | Three-pane `Row`: source image pane (`flex: 5`), content pane showing only Readings/Fields & evidence as a two-way `SegmentedButton` (`flex: 4`), and a persistent History pane (fixed 320dp, no `flex`) built from the same `AuditHistoryPanel` that today only appears when `_tab == 2` (`workbench.dart:1140-1146`). History stops being a tab at this size and becomes an always-visible supporting pane, because a reviewer resolving a disagreement between two model readings frequently wants to check "has this field been corrected before" without losing their place in Fields & evidence. |

**Sticky action bar.** The two primary actions, "Confirm label coverage" and
"Record review approval" (`workbench.dart:1005-1023`), sit inside the
scrolling "Record status" section today, meaning a reviewer who has scrolled
down into a long Fields & evidence tab must scroll back up to act. Pin both
buttons to a bar that never scrolls, at every size class:

- **Compact, medium:** a `Container` anchored above the bottom `NavigationBar`
  (a second, thin bar, not `Scaffold.bottomNavigationBar` itself, since that
  slot is already the Queue/Intake switcher) holding both buttons full-width,
  stacked if needed.
- **Expanded and above:** a `Container` anchored to the bottom of the content
  pane only (not the source-image pane), holding both buttons right-aligned,
  since desktop and tablet-landscape reviewers act with a pointer near their
  last click, not a thumb near the bottom edge.

Everything else in `_section('Record status', [...])`
(`workbench.dart:989-1041`: status text, stage, reason codes, "Correct
classification", "Retry processing") stays in the scrolling content; only the
two review-decision buttons are promoted to the sticky bar, because those are
the two actions the brief's "human authority is explicit" principle treats as
consequential on every visit, while "Correct classification" and "Retry
processing" are occasional and can stay in-line.

**ASCII wireframe, compact (< 600dp, e.g. 390 wide):**

```
+--------------------------------------+
| <- Back        SD-2026-00123      C  |  AppBar: back, id, refresh
+--------------------------------------+
| +------------------------------+     |
| |                              |     |
| |        source image          |     |  scrolls
| |     (pinch/pan/rotate)       |     |
| |                              |     |
| +------------------------------+     |
| [Label 1] [Label 2] [Label 3]        |
| Asset ... / SHA-256 ...              |
|---------------------------------------|
| Needs human review                   |
| Profile insects-v3 . Revision 4      |
| [Correct classification] [Retry]     |
|---------------------------------------|
| [ Readings | Fields & evidence | Hist]|  SegmentedButton
|---------------------------------------|
|  ... selected tab content, scrolls ..|
+--------------------------------------+
| [Confirm label coverage]             |  sticky bar,
| [Record review approval]             |  does not scroll
+--------------------------------------+
|   Queue            Intake            |  bottom NavigationBar
+--------------------------------------+
```

**ASCII wireframe, expanded/large (>= 1200dp):**

```
+------------------------------------------------------------------------------+
| Specimen Digitization   [Insects v]                    A. Duddu v      C     |
+------+--------------------------------+---------------------------+---------+
| Rail |     Source image pane          |      Content pane          | History |
| [Q]  | +----------------------------+ | Needs human review         | (persi- |
| [I]  | |                            | | Profile insects-v3 . Rev 4 | stent,  |
|      | |      source pixels,        | | [Correct classif.][Retry]  |  >=1200 |
|      | |   regions overlaid, pan/   | |-----------------------------| only)   |
|      | |   zoom/rotate controls     | | [ Readings | Fields&evid ] |         |
|      | |                            | |-----------------------------| revision|
|      | +----------------------------+ | ... selected content ...   |  list,  |
|      | [1][2][3] label chips         | |                             |  read-  |
|      | Asset ... SHA-256 ...          | |                             |  only   |
|      |                                |------------------------------| detail  |
+------+--------------------------------+---------------------------+---------+
|                        [Confirm label coverage]  [Record review approval]     |
+------------------------------------------------------------------------------+
```

### 3.6 Region editor

`RegionEditor` (`region_editor.dart`) is an `AlertDialog`, width 680, whose
only way to resize a label region is four `TextFormField`s for left/top/
right/bottom pixel coordinates (`region_editor.dart:157-189`). That is
precise but has no relationship to what the reviewer sees: they must read
pixel numbers off a 180dp preview (`region_editor.dart:94-145`) and type
corrected numbers by hand. On a phone, a 680-wide dialog cannot render at all
without heavy scaling.

- **Compact, medium:** full-screen route (`Navigator.push`, `Dialog.fullscreen`
  or a plain route, not `showDialog`), so the specimen preview can be as
  large as the screen. Add direct manipulation: render each region's bounding
  box with a `GestureDetector`-driven corner handle (four small draggable
  squares, one per corner, each updating `box[i]` on pan) over the preview
  image, in addition to keeping the four numeric fields below the image as a
  secondary, precise-entry fallback (needed for exact pixel input and for
  anyone using a switch-access or keyboard-only input method who cannot drag
  a handle).
- **Expanded and above:** same direct-manipulation preview, now large enough
  to be comfortable with a mouse or trackpad; keep it as a dialog
  (`DialogWidths.wide`, 640, replacing 680) since desktop and tablet-landscape
  windows have room to spare beside it, but the corner-handle interaction
  should be identical code to the full-screen version, not a separate
  implementation, so behavior does not diverge between touch and pointer.

Keep the reason field, add/delete/reorder/merge controls
(`region_editor.dart:191-253`) and validation
(`region_editor.dart:277-304`) unchanged at every size; only the drag surface
and the container (route vs. dialog) change.

### 3.7 Edit dialogs

Covered by the shared rule in 3.0: below 600, every edit dialog in the app
(field correction, transcription adjudication, authority candidate
selection, classification, coverage/approval reason, retry reason, search
filters) becomes a bottom sheet; at 600 and above, each becomes a
`DialogWidths`-constrained `Dialog`. No dialog keeps a bespoke pixel width.

### 3.8 Audit history

`AuditHistoryPanel` (`audit_history.dart`) has no `LayoutBuilder` and today
only ever appears as one of the three workbench tabs. Per 3.5, at large and
extra-large it becomes a persistent pane instead of a tab. At every class,
opening a historical revision (`loadHistoricalRevision`,
`workbench.dart:42-49`) currently swaps content in place inside whatever
container hosts `AuditHistoryPanel`; keep that in the persistent pane at
large+, but at compact and medium, opening a historical revision from the
full-screen History destination should push a second full-screen route (a
"You are viewing revision N, read only" banner pinned to its top, matching
the code comment at `audit_history.dart:5`: "Historical snapshots are
read-only and never replace the active review model"), so the reviewer's
place in the live record is preserved on the route stack underneath.

### 3.9 Large-record fallback

When `specimen.data['artifact_receipt']` is present, `ReviewWorkbench.build`
takes a completely different, single-column path
(`workbench.dart:955-985`: title, refresh, `LargeRecordEvidence`,
`OperationalPanel`, `AuditHistoryPanel`, all in one `ListView`, no
`LayoutBuilder`). A reviewer who hits this fallback on a large window loses
the two/three-pane mental model they had a moment ago on a normal record.
Give it the same expanded-and-above split as 3.5: `LargeRecordEvidence`
(the paginated JSON viewer, `large_record.dart`) in a left pane at `flex: 3`,
`OperationalPanel` stacked above `AuditHistoryPanel` in a right pane at
`flex: 2`. At compact and medium, keep the current single `ListView`.

## 4. Input modalities

Nothing in the codebase currently uses `MouseRegion`, `onHover`,
`SystemMouseCursors`, `Shortcuts`, `CallbackShortcuts`, a dedicated
`FocusNode`, or `HardwareKeyboard` (confirmed by grep across every file in
`lib/`); this section is greenfield, not a fix to existing behavior.

**Touch targets.** `main.dart:115-120` already sets a 48x48 `minimumSize` on
`FilledButtonThemeData` and `OutlinedButtonThemeData`, and Material 3's
`IconButton` and `ChoiceChip` both carry a 48dp minimum interactive area by
default even when their visible size is smaller, so no change is needed
there. Verify the new `SegmentedButton` (3.5) and the region-editor corner
handles (3.6) independently: a corner-handle hit target must be at least
48x48 logical pixels even though its visible square is much smaller, by
wrapping each handle in a `GestureDetector` with a padded, transparent hit
area rather than sizing the handle itself to 48dp (which would obscure the
image underneath it).

**Hover states on web and desktop.** Because every interactive element in
the app is a standard Material widget (`FilledButton`, `OutlinedButton`,
`IconButton`, `ChoiceChip`/`SegmentedButton`, `Card`+`InkWell` via
`ListTile`), Material already supplies default hover and cursor behavior
with no extra code
([docs.flutter.dev/ui/adaptive-responsive/large-screens](https://docs.flutter.dev/ui/adaptive-responsive/large-screens),
"Material 3 provides built-in support for mouse, stylus, and touch inputs in
standard buttons and selectors"). The one custom interactive element, the
region-overlay tap target inside `_source()`
(`workbench.dart:544-575`, an `InkWell` inside a `Positioned` `Stack` child),
also gets a default pointer cursor and ripple for free because it uses
`InkWell` rather than a raw `GestureDetector`. No action needed here beyond
verifying it in Chrome once the layout changes in 3.5 land.

**Pointer on iPad.** A connected trackpad or mouse on iPad automatically gets
the same Material hover behavior as web/desktop once Flutter detects a
non-touch pointer; iPadOS additionally renders its own system pointer
"hover" effect (a soft highlight that previews the target before it is
clicked) around any control that reports itself as interactive, which is a
platform-level behavior, not something Flutter or this app draws
([developer.apple.com/design/human-interface-guidelines/inputs/pointing-devices/](https://developer.apple.com/design/human-interface-guidelines/inputs/pointing-devices/):
iPadOS defines highlight, lift and hover pointer effects and "automatically
adapt[s] the pointer to the current context"). No custom `MouseRegion` work
is needed to get this; it falls out of using standard Material controls, same
as the previous point.

**Keyboard navigation and the review workbench shortcut map.** Wrap the
workbench body (everything inside the `Scaffold` body but outside any
`showDialog`/`showModalBottomSheet` route, so shortcuts are naturally
inert while a dialog's own focus scope is active) in `Shortcuts` and
`Actions`, not the simpler `CallbackShortcuts`, because several of these
intents need to be blocked based on state (`_blocked('approve')`,
`_retryBlocked`) rather than always invoking a callback
(`api.flutter.dev/flutter/widgets/Shortcuts-class.html`: `Shortcuts`
separates key bindings from their implementation, which is what lets the
same `ApproveIntent` no-op or show a disabled-state message depending on
`_blocked`, versus `CallbackShortcuts`, which always runs its callback).

| Action | Shortcut | Notes |
|---|---|---|
| Previous specimen in queue | `[` | Requires `ReviewWorkbench` to receive `onPrevious`/`onNext` callbacks from `CollectionWorkspace`, which it does not today; add them alongside the existing `onChange`/`onRetry`/`onRefresh` callbacks at `workbench.dart:19-21`. |
| Next specimen in queue | `]` | Same as above. |
| Select label region N | `1`-`9` (no modifier) | Maps to the Nth `ChoiceChip` at `workbench.dart:576-591`; a specimen with more than 9 regions has no shortcut for regions past 9, which is acceptable since the brief only asks for 1-9. |
| Deselect region (whole image) | `0` | Mirrors the existing "Whole image" `TextButton` at `workbench.dart:441-444`. |
| Readings tab | `R` | Only active when `_tab` selector is visible (expanded+ hides this in favor of the persistent History pane and a two-way selector; see 3.5). |
| Fields & evidence tab | `F` | |
| History tab | `H` | Compact/medium/expanded only; at large+, History is already visible and this shortcut instead moves focus into the History pane. |
| Zoom in | `+` / `=` (no modifier) | Calls the same handler as the zoom-in `IconButton` (`workbench.dart:412-418`). Do not bind `Ctrl`/`Cmd` +/-: those are the browser's own page-zoom shortcuts and Flutter web cannot intercept them. |
| Zoom out | `-` (no modifier) | Same caveat. |
| Rotate view 90 degrees | `Shift+R` | Distinguished from the unmodified `R` used for the Readings tab. |
| Record review approval | `Ctrl+Enter` (`Cmd+Enter` on macOS) | Opens the same reason dialog as the "Record review approval" button (`workbench.dart:1017-1023`, which calls `_confirm`); the dialog still requires typing a reason and pressing "Record review", so the shortcut only saves the trip to the button, not the reason requirement. |
| Open retry/reason dialog | `Ctrl+Shift+Enter` | Opens the "Retry processing" dialog (`workbench.dart:1058-1085`). Deliberately not `Ctrl+R`, which is the browser's page-reload shortcut. |

Digit and letter shortcuts are unmodified by design, which is only safe
because Flutter's `EditableText` (the base of every `TextField`/
`TextFormField`) consumes character-producing key events itself before they
can bubble to an ancestor `Shortcuts` widget; as long as the workbench's
`Shortcuts` widget wraps only the read-only canvas and tab content, and every
form lives inside its own `showDialog`/`showModalBottomSheet` route (a
separate overlay entry, not a descendant of the workbench's widget subtree),
typing a reason into any dialog's `TextFormField` cannot trigger a region
selection or tab switch. Do not also wrap the dialogs themselves in the same
`Shortcuts` instance, or this guarantee breaks.

**Browser shortcut conflicts to avoid entirely**, because the browser
intercepts these before a web page ever receives the key event: `Ctrl+W`
(close tab), `Ctrl+T` (new tab), `Ctrl+N` (new window), `Ctrl+D` (bookmark),
`Ctrl+P` (print), `Ctrl+S` (save page), `Ctrl+R`/`F5` (reload),
`Ctrl+Shift+R` (hard reload), `Ctrl+F` (browser find), and `Ctrl`/`Cmd` combined
with `+`/`-`/`0` (browser page zoom). None of the shortcuts above use any of
these combinations.

## 5. Platform conventions

| Concern | iOS | Android | Web | Flutter API | Cupertino warranted? |
|---|---|---|---|---|---|
| Back navigation | Edge swipe from left; `Navigator`'s default iOS transition already provides this | Predictive back gesture (Android 14+, preview from 13): the OS previews the destination screen before the pop commits | Browser back button (currently a no-op here; see section 6) | `PopScope` with `onPopInvokedWithResult` (`docs.flutter.dev/platform-integration/android/predictive-back`); requires `android:enableOnBackInvokedCallback="true"` in `AndroidManifest.xml` for the Android side | No; `PopScope` is already platform-adaptive |
| Date pickers | Wheel-style picker matches iOS conventions | Material calendar grid matches Android conventions | Either; a text input with validation is also acceptable | `showDatePicker` (Material) vs `showCupertinoModalPopup` + `CupertinoDatePicker` | Yes, on iOS, if a date field is added (the current filter fields for `created_from`/`created_before`, `search_filters.dart:13-14`, are raw ISO-8601 text fields with no picker at all; add one) |
| Share sheet | `UIActivityViewController` via the system share sheet | Android's `Intent.ACTION_SEND` chooser | Web Share API where available, else a copy-link fallback | `share_plus` package wraps all three; not currently a dependency (`pubspec.yaml` has no `share_plus`) | No; the plugin already adapts |
| File picker | Files app / Photos picker | Storage Access Framework / Photo Picker | `<input type=file>` | Already `file_selector` (`intake.dart:155-172`) | No |
| Text selection | Tap places cursor at the nearest word edge, no drag handles on single tap; long press places cursor, shows toolbar on release | Tap places cursor with a draggable handle; long press selects the word, shows toolbar on release | Standard browser selection plus native right-click context menu | Flutter's `SelectionArea`/`SelectableText` (already used at `workbench.dart:397-399` and `evidence_panel.dart`) automatically adapt these gestures per platform (`docs.flutter.dev/ui/adaptive-responsive/platform-adaptations`) | No |
| Scroll physics | Bouncing overscroll with resistance, snaps back | Glowing overscroll indicator, abrupt stop | Follows the host OS physics under Material by default; can feel foreign to desktop mouse-wheel users | `BouncingScrollPhysics` vs `ClampingScrollPhysics`, chosen automatically by `ScrollConfiguration` per platform | No |
| Status bar / safe areas | Notch, Dynamic Island, home indicator | Punch-hole camera, gesture nav bar | Not applicable | `SafeArea` should wrap each screen's `Scaffold` body (currently absent everywhere in `lib/`; confirmed by grep, `SafeArea` appears zero times in `lib/src/*.dart`); wrap the sticky action bar in 3.5 specifically, since it sits at the bottom edge where the home indicator lives | No |
| System font scaling | `Dynamic Type` / accessibility text size | Font scale in Android display settings | Browser zoom / OS font scale | `MediaQuery.textScalerOf(context)` is respected automatically by `Text` unless overridden; verify no screen wraps its `Text` widgets in a fixed-size `Container` that would clip scaled text (the region-overlay label at `workbench.dart:559-568` uses a plain `Text` inside an unconstrained `Container`, which is safe) | No |
| App icons and splash | `Assets.xcassets` app icon set, `LaunchScreen` storyboard | Adaptive icon (`mipmap-anydpi-v26`), splash via Android 12+ Splash Screen API | Favicon, manifest.json | `flutter_launcher_icons`/`flutter_native_splash` packages are not yet dependencies; add them rather than hand-editing per-platform assets | No |

## 6. Web specifics

**Routing.** `main.dart` sets `initialRoute: '/'` but defines no `routes` map
and no `onGenerateRoute` (`main.dart:101-137`); every screen transition is a
Dart-level state change (`_page`, `_selected` in `workspace.dart`), so the
browser's URL never changes, the browser back button does nothing useful,
refreshing the page always returns to the queue root, and there is no way to
deep link to a specimen. Adopt `go_router` (`pub.dev/packages/go_router`,
current major 18.x, Flutter-team-maintained, "Flutter Favorite," explicitly
supports path/query parameters, deep links and web) rather than hand-rolling
`onGenerateRoute`. Proposed route table:

| Route | Screen | Notes |
|---|---|---|
| `/sign-in` | Magic link / email verification | |
| `/collections/:collectionKey/queue` | Queue | Query params `q`, `disposition`, `state`, and one param per `searchFields` key (`search_filters.dart:3-17`) mirror the current in-memory `_filters`/`_query` state (`workspace.dart:28-29`) so a filtered URL is shareable |
| `/collections/:collectionKey/queue/:specimenId` | Workbench | Pushed from the queue at compact/medium/expanded (3.2); at large+, updates the detail pane without changing the visible route stack depth, using `go_router`'s `StatefulShellRoute` so the list pane persists across specimen selection |
| `/collections/:collectionKey/queue/:specimenId/history` | Audit history (compact/medium full-screen destination, 3.8) | |
| `/collections/:collectionKey/queue/:specimenId/history/:revision` | Historical revision detail | |
| `/collections/:collectionKey/intake` | Intake | |

**Browser back and deep links.** With `go_router` in place, the browser back
button pops the `go_router` stack, which for the workbench route means
returning to the queue at whatever filter state was in the URL; a
bookmarked or shared `/collections/insects/queue/SD-2026-00123` link opens
directly to that specimen after sign-in, gated by the existing
`EmailVerificationGate` (`main.dart:143`).

**Text selection and right-click.** `SelectionArea` (used already, see
section 5) provides the browser-native right-click "Copy" context menu
automatically on web; no custom context menu is needed. Do not intercept
right-click globally (there is currently no `Listener` or `GestureDetector`
doing so; keep it that way).

**Keyboard focus rings.** Flutter draws its own focus indicator for
Material widgets on web/desktop (a highlight ring around the focused
control) with no extra code required; verify it is visible against the
`0xfff4f6f3` scaffold background used throughout (`main.dart:107`) once the
design system's token doc (03) sets a focus-ring color, since Material's
default focus color may be too low-contrast against this specific
off-white.

**Web renderer and Wasm.** For an image-heavy app (every workbench view
loads and pans/zooms a full-resolution specimen photograph via
`InteractiveViewer`, `workbench.dart:462-556`), prefer the WebAssembly
build (`flutter build web --wasm`) over the legacy HTML renderer: Skia
compiled to Wasm (Skwasm) offloads paint work to a worker thread and avoids
the HTML renderer's per-image DOM overhead, and as of early 2026 the
required WasmGC support covers the large majority of desktop browser
traffic (Chrome 119+, Firefox 120+, Edge 119+, Safari 18.2+). Do not use the
plain `--web-renderer html` target for this app; it exists for compatibility
with older browsers this app does not need to support, and it is
particularly weak at exactly the large-image, pan-and-zoom workload the
workbench needs.

## 7. Camera capture

`intake.dart:148-153` calls `ImagePicker().pickImage(source:
ImageSource.camera, requestFullMetadata: false)`, which hands off entirely
to the OS's own camera app and returns one photograph. `image_picker`
(current version 1.2.3) provides no in-app preview overlay, no framing
guide, no exposure or glare feedback, no level indicator, and no way to stay
in-app across a batch (`pub.dev/packages/image_picker`: the plugin
"delegates camera functionality to native system intents," and on desktop
platforms states outright that "there is no system-provided UI for taking
photos," i.e. it always defers to something outside the plugin's control).
For a workflow that is explicitly batches of dozens to hundreds of
specimens, leaving the app once per photograph is the wrong default.

**What a first-class capture screen needs**, built on the `camera` package
(the lower-level Flutter-team plugin that exposes the live preview
`CameraController`, as opposed to `image_picker`'s single-shot intent) or a
platform channel to `AVFoundation`/`CameraX` directly:

- **Framing guide:** an overlay rectangle (or two nested rectangles: one for
  the whole specimen, one for its labels) drawn over the live
  `CameraPreview`, sized from the collection profile's expected aspect ratio
  where known, otherwise a generic centered guide. This is a drawn overlay,
  not a detection feature; it does not verify the specimen is inside it.
- **Exposure and glare hints:** a short, honest text hint ("Frame may be
  uneven; check for glare before capturing") triggered by a coarse
  brightness histogram read from preview frames, explicitly not a pass/fail
  gate, matching the PRD's "never invent a value to make a record complete"
  principle and the existing client-side honesty pattern already used for
  quality measurement (`capture_quality.dart`, whose measurements the app
  already treats as advisory, never a submission blocker: see
  `intake.dart:513`, "this client does not certify image quality"). Do not
  present a computed score as a pass/fail signal; a copy stand's fixed
  lighting and a field photograph's variable lighting produce very different
  baselines, and the client cannot calibrate for either.
- **Level indicator:** read `accelerometerEventStream` (from the
  `sensors_plus` package, not currently a dependency) and render a simple
  two-line spirit-level graphic, since a tilted copy stand shot distorts
  bounding-box coordinates that downstream region correction assumes are
  axis-aligned to the source pixels.
  Android's own document-scanning UX guidance uses the same tap-to-lock
  focus/exposure convention worth matching here: "tap and hold... to lock
  focus and exposure," shown as a lock indicator, so the operator can
  photograph a specimen with a plain background without the camera
  re-metering mid-batch.
- **Review and retake:** after each capture, show the still frame full
  screen with "Retake" and "Use photo" actions before it is added to the
  intake manifest (`ManifestEntry`, `intake.dart:13-31`), rather than
  `image_picker`'s current behavior of accepting the OS camera's own result
  unconditionally.
- **Batch mode:** after "Use photo," return directly to the live preview for
  the next specimen instead of returning to the intake screen, with a
  persistent counter ("14 captured this session") and a "Done" action that
  returns to `IntakeScreen` with all captured frames queued as
  `ManifestEntry` items in one pass (reusing `_acceptFiles`,
  `intake.dart:193-308`, unchanged).

Apple's own document-scanning system component,
`VNDocumentCameraViewController`
(`developer.apple.com/documentation/visionkit/scanning-data-with-the-camera`),
already implements automatic edge detection and multi-page capture for flat
paper documents; it is not a fit here because pinned insect specimens are
not flat documents and edge detection tuned for a printed page will not
track a three-dimensional pinned specimen or its small paper labels. Do not
adopt `VNDocumentCameraViewController` or an Android
"Documents mode" camera intent as a shortcut; build the custom flow above
instead, and treat VisionKit's UX only as a reference for how review/retake
and multi-item batching should feel, not as a component to embed.

## 8. Testing

**Widget tests per size class.** Set the test surface directly rather than
faking a device name:

```dart
testWidgets('workbench shows two panes at expanded width', (tester) async {
  tester.view.physicalSize = const Size(900, 700); // 900 logical @ 1.0 dpr
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(/* ... */);
  expect(find.byType(SegmentedButton<int>), findsOneWidget);
});
```

Write one test per breakpoint boundary, not per device: 599 and 600 (compact
vs. medium), 839 and 840 (medium vs. expanded), 1199 and 1200 (expanded vs.
large), 1599 and 1600 (large vs. extra-large), for every screen in section 3
that branches. Always reset both `physicalSize` and `devicePixelRatio` in
`addTearDown`, or a later test in the same file inherits the previous test's
surface.

**Golden tests per size class.** For the workbench's ASCII-wireframed
layouts (3.5), add one golden per class (compact, expanded, large) rather
than one golden per device, using the same `tester.view.physicalSize`
technique above with a fixed `devicePixelRatio` (2.0 is a reasonable
default) so the golden is deterministic across machines.

**Device matrix.** Use these as the logical (point/dp) sizes to plug into
`tester.view.physicalSize`, and as the physical devices or simulators to
spot-check manually before a release:

| Device | Logical size (portrait) | Class (portrait) | Class (landscape) |
|---|---|---|---|
| iPhone 16e | 390 x 844 | Compact | Compact |
| iPhone 17 Pro Max | 440 x 956 | Compact | Medium |
| iPad mini (6th gen) | 744 x 1133 | Medium | Expanded |
| iPad Pro 13" (M4) | 1032 x 1376 | Expanded | Large |
| iPad Pro 13", Split View 1/2 | ~516 x 1376 | Compact | n/a (already landscape-shaped) |
| Pixel-class phone (Pixel 9) | 412 x 915 | Compact | Compact |
| 10" Android tablet (e.g. Pixel Tablet, ~927 x 1484 computed from 1600x2560px @ ~276ppi) | 927 x 1484 | Medium | Large |
| Chrome desktop | 1280 x 800 | n/a | Large |
| Chrome desktop | 1920 x 1080 | n/a | Extra-large |

For the iPad Pro 13" row, also test the app at the narrowest Split View width
(roughly 320-375 logical points per Apple's historical minimum multitasking
width) to confirm the compact layout in section 3 renders correctly there
too, since that is the practical minimum width any iPad user can hand the
app regardless of the device's own screen size.

## Sources

- [m3.material.io/foundations/layout/applying-layout/window-size-classes](https://m3.material.io/foundations/layout/applying-layout/window-size-classes)
- [m3.material.io/components/navigation-bar/specs](https://m3.material.io/components/navigation-bar/specs)
- [m3.material.io/components/navigation-rail/guidelines](https://m3.material.io/components/navigation-rail/guidelines)
- [m3.material.io/components/navigation-drawer/guidelines](https://m3.material.io/components/navigation-drawer/guidelines)
- [developer.android.com/develop/adaptive-apps/guides/canonical-layouts](https://developer.android.com/develop/adaptive-apps/guides/canonical-layouts)
- [developer.android.com/docs/quality-guidelines/large-screen-app-quality](https://developer.android.com/docs/quality-guidelines/large-screen-app-quality)
- [developer.android.com/design/ui/mobile/guides/layout-and-content/postures-and-orientation](https://developer.android.com/design/ui/mobile/guides/layout-and-content/postures-and-orientation)
- [developer.android.com/guide/topics/large-screens/foldables](https://developer.android.com/guide/topics/large-screens/foldables)
- [docs.flutter.dev/ui/adaptive-responsive](https://docs.flutter.dev/ui/adaptive-responsive)
- [docs.flutter.dev/ui/adaptive-responsive/general](https://docs.flutter.dev/ui/adaptive-responsive/general)
- [docs.flutter.dev/ui/adaptive-responsive/large-screens](https://docs.flutter.dev/ui/adaptive-responsive/large-screens)
- [docs.flutter.dev/ui/adaptive-responsive/best-practices](https://docs.flutter.dev/ui/adaptive-responsive/best-practices)
- [docs.flutter.dev/ui/adaptive-responsive/safearea-mediaquery](https://docs.flutter.dev/ui/adaptive-responsive/safearea-mediaquery)
- [docs.flutter.dev/ui/adaptive-responsive/input](https://docs.flutter.dev/ui/adaptive-responsive/input)
- [docs.flutter.dev/ui/adaptive-responsive/capabilities](https://docs.flutter.dev/ui/adaptive-responsive/capabilities)
- [docs.flutter.dev/ui/adaptive-responsive/platform-adaptations](https://docs.flutter.dev/ui/adaptive-responsive/platform-adaptations)
- [docs.flutter.dev/platform-integration/android/predictive-back](https://docs.flutter.dev/platform-integration/android/predictive-back)
- [developer.apple.com/design/human-interface-guidelines/layout](https://developer.apple.com/design/human-interface-guidelines/layout)
- [developer.apple.com/design/human-interface-guidelines/inputs/pointing-devices/](https://developer.apple.com/design/human-interface-guidelines/inputs/pointing-devices/)
- [developer.apple.com/documentation/visionkit/scanning-data-with-the-camera](https://developer.apple.com/documentation/visionkit/scanning-data-with-the-camera)
- [api.flutter.dev/flutter/material/NavigationRail-class.html](https://api.flutter.dev/flutter/material/NavigationRail-class.html)
- [api.flutter.dev/flutter/material/NavigationDrawer-class.html](https://api.flutter.dev/flutter/material/NavigationDrawer-class.html)
- [api.flutter.dev/flutter/material/SegmentedButton-class.html](https://api.flutter.dev/flutter/material/SegmentedButton-class.html)
- [api.flutter.dev/flutter/widgets/Shortcuts-class.html](https://api.flutter.dev/flutter/widgets/Shortcuts-class.html)
- [api.flutter.dev/flutter/widgets/MediaQueryData/displayFeatures.html](https://api.flutter.dev/flutter/widgets/MediaQueryData/displayFeatures.html)
- [pub.dev/packages/flutter_adaptive_scaffold](https://pub.dev/packages/flutter_adaptive_scaffold)
- [pub.dev/packages/go_router](https://pub.dev/packages/go_router)
- [pub.dev/packages/image_picker](https://pub.dev/packages/image_picker)

`flutter_adaptive_scaffold` is explicitly not recommended: it was discontinued
by the Flutter team in April 2025 ("planned to be discontinued,"
`github.com/flutter/flutter/issues/162965`) and its `pub.dev` listing
confirms it "has been discontinued and will not receive further updates."
Build the breakpoint and pane logic in sections 1 and 3 directly with
`LayoutBuilder`/`MediaQuery.sizeOf`, as specified above, rather than taking a
dependency on it or on one of its unofficial community forks.
