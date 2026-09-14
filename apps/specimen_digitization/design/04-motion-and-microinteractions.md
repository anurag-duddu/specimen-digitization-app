# 04. Motion and microinteractions

Scope: every animation, transition, progress indicator and haptic in the Specimen
Digitization Flutter client. Toolchain assumed throughout: Flutter 3.38.5 stable,
Dart 3.10.4, Material 3.

## 0. Where we are starting from

The app currently authors no motion at all. A grep across `lib/` for `Curves.`,
`AnimatedSwitcher`, `AnimatedContainer`, `Hero(`, `PageRouteBuilder`,
`RefreshIndicator` and `MaterialPageRoute` returns nothing. The only `Duration`
literals in the client are:

| Location | Value | What it is |
| --- | --- | --- |
| `lib/src/workspace.dart:335` | 350 ms | search debounce |
| `lib/src/workspace.dart:60` | 20 s | quiet queue poll |
| `lib/src/workbench.dart:302`, `:1098`, `lib/src/evidence_panel.dart:151`, `lib/src/operational_panel.dart:72` | 250 ms | hard-coded sleep before disposing `TextEditingController`s, so a dialog exit transition does not read a disposed controller |

Everything visible today is Material's own default motion: `InkWell` ripples,
`ExpansionTile` at 200 ms (`_kExpand` in `flutter/src/material/expansion_tile.dart:26`),
`showDialog` at 150 ms (`flutter/src/material/dialog.dart:1681`), and the
`NavigationBar` / `NavigationRail` indicator.

There is also no `Navigator` route for a specimen. `workspace.dart:483-556` swaps
the body with `setState` on `_page` and `_selected`, so opening a record is a
rebuild with no transition, no back gesture and no deep link. Several
recommendations below depend on that changing; each one says so.

Three defects that motion work must fix rather than decorate:

1. `workspace.dart:676-679` inserts a `LinearProgressIndicator` into a `Column`
   whenever `_loading || _mutating`. The whole page below it jumps 4 px down and
   back on every poll-triggered load and every save.
2. `intake.dart:623` renders the upload bar only while `e.state == 'Uploading'`.
   The bar disappears at the instant it reaches 1.0, so the operator never sees
   an upload finish, only sees it vanish.
3. `workbench.dart:512-567` draws the region overlays inside the
   `InteractiveViewer` child, so `Border.all(width: 3)` at `maxScale: 12`
   (`workbench.dart:464`) renders a 36 px border over the label the reviewer is
   trying to read.

---

## 1. Motion principles

Seven principles. Each is a test an engineer can apply during review.

### 1.1 Motion states a fact about the system, never an opinion about the brand

Every animation answers one of exactly four questions: what changed, where did it
come from, is it still working, did my action land. If a proposed animation
answers none of those, it does not ship. Apple's Motion guidance puts the same
rule as "Don't add motion for the sake of adding motion. Gratuitous or excessive
animation can distract people" (https://developer.apple.com/design/human-interface-guidelines/motion).

### 1.2 The source pixels are the reference; they do not move unless the reviewer moves them

The whole product is a claim about what a photograph shows. Anything that
translates, scales, fades or re-crops the specimen image without the reviewer
asking is a change to the evidence as presented. The image subtree is animated
only by pan, pinch, the zoom controls, rotate, region selection and view reset.
Panel changes beside it never move it, and never slide far enough to make it look
like it moved.

### 1.3 A reviewer sees each of these hundreds of times a day, so the budget is measured in a workday, not a moment

A reviewer works one record for minutes, then repeats for hours. NN/g: "the more
frequent the animation, the more subtle and shorter you'll want it to be"
(https://www.nngroup.com/articles/animation-duration/). Concretely: nothing on the
critical review path exceeds 350 ms, most is 100 to 200 ms, and no animation ever
blocks input. Apple: "Don't make people wait for an animation to complete before
they can do anything, especially if they have to experience the animation more
than once" (https://developer.apple.com/design/human-interface-guidelines/motion).

### 1.4 One thing moves at a time

One user action produces at most one element that changes position or size.
Opacity and colour may change on other elements at the same time. M3 says the same
in different words: "Elements are grouped and move along a primary axis instead of
moving in independent directions"
(https://m3.material.io/styles/motion/transitions/applying-transitions).

### 1.5 Progress is a measurement, not an animation

A progress indicator reports a number the server or the byte stream gave us. It is
monotonic. It never resets, never runs backwards, never fills to 90 percent and
waits, never fakes a rate. Determinate only when a real fraction exists;
indeterminate otherwise. This is the product's "never invent a value to make a
record complete" rule applied to pixels.

### 1.6 Motion is never the only channel

Anything communicated by movement is also communicated in text and in semantics.
Apple: "avoid using it as the only way to communicate important information"
(https://developer.apple.com/design/human-interface-guidelines/motion). The
existing `Semantics(liveRegion: true)` wrappers at `workspace.dart:667`,
`intake.dart:528`, `intake.dart:563` and `evidence_panel.dart:63` are the model.
Extend that pattern; do not replace it with animation.

### 1.7 Reduced motion is a supported configuration, not a degraded one

Reduced motion is tested on every screen, in CI. Travel and scale collapse to
zero. Information that only motion carries, which is exactly progress, stays.

### 1.8 How we avoid animating everything

The AI-slop failure mode is: every list staggers in, every card lifts on hover,
every number counts up, every success throws confetti, every route cross-fades.
Four mechanisms stop it here.

**An allowlist, not a style.** Section 4 is the complete list of animated
interactions. Anything not in that table is not animated. Adding a row to the
table is a design review, the same as adding a colour token.

**A one-sentence justification, written down.** Every row in section 4 has a
"what it explains" note. If the sentence needs an "and it feels nice" clause, the
animation is cut.

**A named blocklist.** These are banned outright, with no case-by-case exception:

- Entrance animations on list items that already existed before the rebuild.
- Stagger on any list that polls, paginates or refreshes. `workspace.dart:60-70`
  polls every 20 seconds, so a staggered queue would replay three times a minute.
- Hover scale, hover elevation, hover translate on rows, cards or chips.
- Parallax, blur-up image loading, Ken Burns pans, shape morphing on containers.
- Idle loops: pulsing, breathing, shimmering anything that is not a skeleton.
- Number roll-ups. The risk score (`workspace.dart:433`) is an uncalibrated
  measurement; animating it from 0 to 62 makes it look like an achievement bar.
- Bouncy, elastic and overshoot curves. M3 agrees for this class of product:
  "Common transitions should not use overt style effects like bouncy springs"
  (https://m3.material.io/styles/motion/transitions/applying-transitions).
- Confetti, sparkles, checkmark bursts, sound.
- Any animation longer than 500 ms anywhere in the app.

**A budget.** At most two concurrent authored animations on screen at any moment,
excluding the global progress bar. If a change would require a third, the
interaction is wrong, not the timing.

---

## 2. Motion tokens

### 2.1 Which Material system we are building on

Material 3 replaced easing and duration with a spring-based physics system in
M3 Expressive. That page lists platform availability and states **Flutter:
Unavailable** (https://m3.material.io/styles/motion/overview). M3 also notes the
easing and duration system "is still used for transitions and can be used by
teams that haven't yet updated to GM3 Expressive, but is no longer maintained."

So: we build on the M3 easing and duration tokens, because they are the only M3
motion system Flutter implements. Flutter ships them as generated constants in
`package:flutter/material.dart`: `Durations` and `Easing`, generated from the
Material Design token database (`flutter/src/material/motion.dart`, exported at
`flutter/lib/material.dart:126`). We use those constants directly rather than
retyping millisecond literals.

### 2.2 Duration tokens

| Product name | ms | Flutter constant | M3 token | Used for |
| --- | --- | --- | --- | --- |
| `instant` | 0 | `Duration.zero` | none | Direct manipulation: pinch, pan, drag, typing into a coordinate field, focus rings. |
| `quick` | 100 | `Durations.short2` | `md.sys.motion.duration.short2` | State swaps inside one component: chip check, status glyph, button label, hover and selected fills, exit of a small element. |
| `standard` | 200 | `Durations.short4` | `md.sys.motion.duration.short4` | The default. Cross-fades between panel contents, expand and collapse, banner enter, skeleton to content, progress value catch-up. |
| `emphasized` | 350 | `Durations.medium3` | `md.sys.motion.duration.medium3` | Changes that move the reviewer's attention across a large area: image zoom-to-region, rotate, view reset, bottom sheet enter. |
| `slow` | 500 | `Durations.long2` | `md.sys.motion.duration.long2` | Reserved. Nothing in section 4 uses it today. It exists so that a future full-screen container transform has a token instead of inventing one. |

M3's own duration groups line up: short is "small utility-focused transitions",
medium is "traverse a medium area of the screen", long is "large expressive
transitions", and extra long is "rare"
(https://m3.material.io/styles/motion/easing-and-duration/tokens-specs). We use
nothing from the extra-long group.

Independent sanity check on the ceiling: NN/g puts UI animation at 100 to 500 ms
and says "At 500ms, animations start to feel like a real drag for users"
(https://www.nngroup.com/articles/animation-duration/). Our practical ceiling of
350 ms on the review path is deliberately tighter than that, per principle 1.3.

### 2.3 Easing tokens

| Product name | Flutter constant | Cubic | M3 token | Used for |
| --- | --- | --- | --- | --- |
| `standard` | `Easing.standard` | `(0.2, 0, 0, 1)` | `md.sys.motion.easing.standard` | Default for anything that begins and ends on screen. Pairs with `quick` or `standard`. |
| `enter` | `Easing.standardDecelerate` | `(0, 0, 0, 1)` | `...standard.decelerate` | Something arriving on screen: banner, sheet, newly loaded evidence block. |
| `exit` | `Easing.standardAccelerate` | `(0.3, 0, 1, 1)` | `...standard.accelerate` | Something leaving permanently: dismissed banner, deleted region, collapsed panel. |
| `emphasized` | `Curves.easeInOutCubicEmphasized` | two-part path curve, not a single cubic | `md.sys.motion.easing.emphasized` | Large moves that begin and end on screen: zoom to region, view reset, rotate. |
| `emphasizedEnter` | `Easing.emphasizedDecelerate` | `(0.05, 0.7, 0.1, 1)` | `...emphasized.decelerate` | Bottom sheet and dialog enter. |
| `emphasizedExit` | `Easing.emphasizedAccelerate` | `(0.3, 0, 0.8, 0.15)` | `...emphasized.accelerate` | Bottom sheet and dialog dismiss. |
| `progress` | `Curves.linear` | `(0, 0, 1, 1)` | `md.sys.motion.easing.linear` | Progress bars only. A progress value must not ease; easing misreports rate. |

Two facts an engineer needs before writing this:

- `md.sys.motion.easing.emphasized` is a **two-part path curve**, not a cubic
  bezier. M3's token table prints its Android path as
  `M 0,0 C 0.05, 0, 0.133333, 0.06, 0.166666, 0.4 C 0.208333, 0.82, 0.25, 1, 1, 1`
  and lists CSS and iOS as "N/A (Use Standard as a fallback)". Flutter is the one
  platform with a native implementation, and M3 names it: `easeInOutCubicEmphasized`
  (https://m3.material.io/styles/motion/easing-and-duration/tokens-specs). In the
  installed SDK it is a `ThreePointCubic` with control points
  `(0.05,0)`, `(0.133333,0.06)`, midpoint `(0.166666,0.4)`, `(0.208333,0.82)`,
  `(0.25,1)` (`flutter/src/animation/curves.dart:1777`).
- **There is no `Easing.emphasized` constant in Flutter.** `Easing` provides
  `emphasizedAccelerate` and `emphasizedDecelerate` only. For the full emphasized
  curve you must reach for `Curves.easeInOutCubicEmphasized`. Getting this wrong
  is the most common way a Flutter M3 motion spec drifts from the tokens.

### 2.4 Which pair goes with what

M3 publishes a suggested pairs table
(https://m3.material.io/styles/motion/easing-and-duration/applying-easing-and-duration):
emphasized with 500 ms for begin-and-end-on-screen, emphasized decelerate with
400 ms to enter, emphasized accelerate with 200 ms to exit, standard with 300 ms,
standard decelerate with 250 ms, standard accelerate with 200 ms.

We shorten the emphasized pairs, and we say why: M3's pairs are tuned for consumer
apps where a transition is seen a handful of times per session. Our reviewer sees
the panel swap and the region zoom hundreds of times a day. Our table:

| Situation | Duration | Curve |
| --- | --- | --- |
| Begins and ends on screen, small (chip, glyph, label) | `quick` 100 | `standard` |
| Begins and ends on screen, medium (panel content swap, expand) | `standard` 200 | `standard` |
| Begins and ends on screen, large (image zoom to region, rotate, view reset) | `emphasized` 350 | `Curves.easeInOutCubicEmphasized` |
| Enters the screen (banner, sheet, newly loaded evidence) | `standard` 200, or `emphasized` 350 for a full-width sheet | `enter`, or `emphasizedEnter` for a sheet |
| Exits permanently (dismissed banner, deleted region, collapsed panel) | `quick` 100 | `exit` |
| Exits temporarily and can be recalled (a dialog the user may reopen) | `standard` 200 | `standard` |
| Progress value catch-up | `standard` 200 | `progress` (linear) |

M3's own asymmetry rule is preserved: "Transitions that exit, dismiss, or collapse
an element use shorter durations."

### 2.5 Reduced motion policy

**How the signal reaches Flutter 3.38.5. This is not symmetric and the asymmetry
is the whole problem.**

| Platform | User setting | Reaches Flutter 3.38.5 as | Reaches `MediaQuery.disableAnimationsOf`? |
| --- | --- | --- | --- |
| Android | Accessibility, Color and motion, "Remove animations" (https://support.google.com/accessibility/android/answer/11183305), which zeroes `Settings.Global.ANIMATOR_DURATION_SCALE` / `TRANSITION_ANIMATION_SCALE` / `WINDOW_ANIMATION_SCALE` (https://developer.android.com/reference/android/provider/Settings.Global) | `AccessibilityFeatures.disableAnimations` | Yes |
| iOS and iPadOS | Accessibility, Motion, Reduce Motion | `AccessibilityFeatures.reduceMotion` only | **No** |
| Web | `prefers-reduced-motion: reduce` | **Nothing** | **No** |

All three rows verified against the installed SDK, not inferred.

**iOS.** `dart:ui` defines both flags, and the doc comment on `reduceMotion` reads
"Only supported on iOS" (`bin/cache/pkg/sky_engine/lib/ui/window.dart:945` and
`:956`). `MediaQueryData` carries `disableAnimations` and nothing else: it is
populated from `view.platformDispatcher.accessibilityFeatures.disableAnimations`
(`flutter/src/widgets/media_query.dart:298-300`), and `reduceMotion` appears
nowhere in `media_query.dart`. So on an iPad with Reduce Motion on,
`MediaQuery.disableAnimationsOf(context)` is `false`. An iPad is our primary
review surface. Reading only `MediaQuery` would ship a spec that is silently
broken for the users most likely to need it.

**Web.** Worse: nothing reaches Flutter at all. The web engine's
`EnginePlatformDispatcher.computeAccessibilityFeatures()` sets exactly one flag,
`highContrast`, and returns
(`bin/cache/flutter_web_sdk/lib/_engine/engine/platform_dispatcher.dart:66-72`).
`prefers-reduced-motion` is never read. Reduced-motion support on the web landed
in Flutter 3.44, per its release notes, which is after our toolchain. Until we
upgrade, web reduced motion is ours to implement (section 6.2).

**Therefore the app must read three sources**: `MediaQuery.disableAnimationsOf`
for Android, `AccessibilityFeatures.reduceMotion` for iOS, and our own
`matchMedia` bridge plus a stored user preference for web. Section 6.2 gives the
helper.

**What Flutter already does for free, and what it does not.** When
`SemanticsBinding.instance.disableAnimations` is true, every `AnimationController`
with the default `AnimationBehavior.normal` runs at 5 percent of its duration
(`flutter/src/animation/animation_controller.dart:651`). Implicitly animated
widgets create their controller with the default behavior
(`flutter/src/widgets/implicit_animations.dart:362-366`), so they inherit it.
That covers Android only, and only for one-shot animations. Three gaps we own:

- **iOS**, because `disableAnimations` is never set there.
- **Web**, because nothing is set there in 3.38.5.
- **Repeating animations anywhere.** `AnimationBehavior.preserve` exists
  specifically so a `repeat()` loop is not compressed into a strobe, and the enum
  documents it as the default for repeating animations
  (`flutter/src/animation/animation_controller.dart:59-69`). So a skeleton
  shimmer and an indeterminate spinner are **not** auto-shortened and must be
  gated by hand. That is why section 6.5 disables the shimmer explicitly.

Our token layer therefore returns `Duration.zero`, which the controller handles as
a synchronous jump without starting a ticker
(`animation_controller.dart:673-684`).

**What collapses to instant under reduced motion:**

- All translation, scale, rotation and clip changes. Region zoom becomes an
  instant re-crop. Rotate becomes an instant quarter turn. Sheets and dialogs
  appear without travel.
- All shared-axis slides. Panel and tab changes become a `quick` 100 ms cross-fade
  with no offset, which matches Apple's Accessibility guidance to replace
  "transitions in x-, y-, and z-axes with fades to avoid motion"
  (https://developer.apple.com/design/human-interface-guidelines/accessibility)
  and M3's "Use subtle fades instead of intense sliding or scaling animations"
  (https://m3.material.io/styles/motion/transitions/applying-transitions).
- Skeleton shimmer. The skeleton stays, as a static grey block. The sweep stops.
- The save-succeeded check draw. The check appears at full size immediately.
- Ripples and hover fills drop to instant colour changes.

**What keeps its motion, because the motion is the information:**

- **Determinate progress bars.** Upload progress is a number, and the bar is the
  rendering of that number. Removing it removes data. It keeps the `standard`
  200 ms linear catch-up so byte-callback jitter does not strobe.
- **Indeterminate progress indicators**, with a limit. WCAG 2.2 SC 2.2.2
  Pause, Stop, Hide (Level A) applies to moving content that starts
  automatically, lasts more than five seconds, and runs in parallel with other
  content, "unless the movement ... is part of an activity where it is essential"
  (https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html). A spinner
  that says "the server has not answered" is essential. A spinner that has been
  turning for 30 seconds is not informative, it is just moving. Rule: after
  10 seconds, replace the indeterminate indicator with static text that names the
  elapsed time and offers an action ("Still waiting on the server. Started 34
  seconds ago." plus Retry). Ten seconds is Nielsen's attention limit
  (https://www.nngroup.com/articles/response-times-3-important-limits/).
- **Countdown text** for a scheduled retry. It is text updating once per second,
  not motion, and it is outside 2.2.2's moving-content clause.

Note for the accessibility statement: WCAG 2.2 SC 2.3.3 Animation from
Interactions, which requires interaction-triggered motion animation to be
disableable, is **Level AAA**, not AA
(https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html).
We implement it anyway, but we should not claim it as an AA conformance item.

**Two honest limitations, to write into the accessibility statement rather than
paper over.**

1. Android's setting is a float multiplier, not a boolean. A user can set 0.5x or
   2x through Developer Options, and Battery Saver also zeroes it
   (https://developer.android.com/reference/android/animation/ValueAnimator).
   Flutter exposes only a boolean, so a 0.5x preference is invisible to us and we
   cannot honour it. Our reduced-motion mode is all or nothing.
2. Because Battery Saver zeroes the same scales, `disableAnimations` being true is
   not proof of motion sensitivity. That is fine here: the reduced-motion mode
   loses no information, so switching into it on a low battery costs the user
   nothing.

---

## 3. Tooling decision

### 3.1 What actually resolves on Flutter 3.38.5

Three of the obvious candidates shipped a release in the last month that requires
Flutter 3.44 or newer. Version data from the pub.dev API on 2026-09-13.

| Package | Latest | Latest constraint | Resolves on 3.38.5? | Highest version that does |
| --- | --- | --- | --- | --- |
| `animations` | 3.0.0 (2026-08-19) | Dart `^3.12.0`, Flutter `>=3.44.0` | No | **2.2.0** (2026-04-23, Dart `^3.9.0`, Flutter `>=3.35.0`) |
| `flutter_animate` | 4.5.2 (2024-11-25) | Dart `>=2.17.0 <4.0.0`, Flutter `>=2.0.0` | Yes | 4.5.2 |
| `rive` | 0.14.11 (2026-08-03) | Dart `>=3.6.0 <4.0.0`, Flutter `>=3.28.0` | Yes | 0.14.11 (pulls `rive_native` 0.1.11) |
| `lottie` | 3.5.1 (2026-07-08) | Dart `^3.12.0`, Flutter `>=3.44.0` | No | 3.3.3 (2026-04-10) |
| `skeletonizer` | 3.0.0 (2026-09-11) | Dart `>=3.7.0 <4.0.0`, Flutter `>=3.32.0` | Yes | 3.0.0 |
| `shimmer` | 4.0.0 (2026-08-21) | Dart `^3.12.0`, Flutter `>=3.44.0` | No | 3.0.0, published 2023-05-21 |

### 3.2 Comparison

| | Built-in Flutter | `animations` 2.2.0 | `flutter_animate` 4.5.2 | `skeletonizer` 3.0.0 | Rive 0.14.11 | Lottie 3.3.3 |
| --- | --- | --- | --- | --- | --- | --- |
| Use case fit | Everything in section 4 except container transform and skeletons | Container transform, shared axis, fade through, as ready-made Material patterns | Chained effect syntax over widgets; nothing we need that built-ins lack | Skeleton loading derived from the real widget tree | Interactive vector with state machines, driven from app state | Pre-rendered vector playback from After Effects |
| Runtime cost | Lowest. No extra widgets, no extra layer | Low. Thin wrappers over `AnimatedSwitcher` and `PageRoute` | Low, but its shader effects (`flutter_shaders`) are the part most likely to interact with Impeller | Low. Pure Dart, paints over the existing tree | Highest. C++ runtime via `rive_native`; the pub page warns of "rendering and performance discrepencies" with Impeller on iOS and suggests testing with `--no-enable-impeller` | Medium. `renderCache` added in 3.0 specifically to fix "excessive energy consumption" on repeat loops |
| Authoring cost | Dart only, reviewable in a normal diff | Dart only | Dart only | One widget wrap plus per-widget skeleton hints | A separate editor, a separate skill, a binary `.riv` asset that no diff can review | After Effects plus the Bodymovin exporter, then a JSON blob that no diff can review |
| Accessibility | Best. Honours `disableAnimations` at the controller level automatically | Same, built on the same controllers | Same | Shimmer sweep must be disabled manually under reduced motion | Playback is opaque to Flutter's accessibility layer; you must gate it yourself and provide a static fallback | Same as Rive |
| Offline / air-gapped build | Yes | Yes, pure Dart | Yes | Yes | **No.** `rive_native` downloads prebuilt native libraries at build time; the fallback is `dart run rive_native:setup`. This breaks a hermetic CI or a museum build machine without egress | Yes, pure Dart |
| License | BSD-3-Clause (part of the SDK) | BSD-3-Clause, publisher flutter.dev | BSD-3-Clause, publisher gskinner.com, Flutter Favorite | MIT, publisher codeness.ly | MIT runtime; the **editor** is a paid subscription | MIT |
| Maintenance signal | Flutter team | Flutter team | Last published 2024-11-25, 21 months ago | Last published 2026-09-11 | Active | Active |

### 3.3 Recommendation

**Adopt, now:**

1. **Built-in Flutter animations for roughly 95 percent of section 4.** Nine
   widgets cover almost the whole catalog: `AnimatedSwitcher`, `AnimatedOpacity`,
   `AnimatedSize`, `AnimatedRotation`, `AnimatedContainer`, `AnimatedPositioned`,
   `AnimatedDefaultTextStyle`, `TweenAnimationBuilder`, and one
   `AnimationController` for the image transform. No dependency, no review
   surface, and reduced motion is handled at the controller layer for free.
2. **`skeletonizer: ^3.0.0`** for queue load and lazy evidence load. It is the
   only skeleton package whose current release fits the toolchain, it is pure
   Dart, and it derives skeletons from the real widget tree, which means the
   skeleton cannot drift from the row layout the way a hand-drawn one does. It
   also makes `shimmer` redundant. Configure it with the shimmer sweep disabled
   under reduced motion (section 6.5).

**Adopt only if we introduce routes:**

3. **`animations: ^2.2.0`**, pinned below 3.0.0 until the app moves to Flutter
   3.44. Two uses, and only two: `PageTransitionSwitcher` with
   `SharedAxisTransition` for the workbench tab change, and `OpenContainer` for
   the intake manifest row (which has a real shared element, the capture
   thumbnail from `CaptureQualityView`). `OpenContainer` needs a `Navigator`
   route; `workspace.dart:483-556` has none. Until routes exist, build the tab
   change with a plain `AnimatedSwitcher` and a `SlideTransition`, which is about
   fifteen lines, and skip the dependency entirely. Do not add `animations` for
   the queue-to-workbench transition: the queue row and the workbench header
   share no visual element, so a container transform would have nothing to
   transform.

**Decline:**

4. **`flutter_animate`.** It is a good package and the wrong one for us. It
   optimises for authoring long effect chains quickly, which is exactly the
   pressure we are trying to remove from this codebase. `.animate().fade().slide().shimmer()`
   makes adding an animation cheaper than justifying it. Everything we need is
   three widgets. It has also not shipped in 21 months.
5. **Lottie.** It plays a timeline. Nothing in section 4 is a timeline; every
   candidate is state-driven. If we wanted state-driven vector, Rive is the right
   tool, not Lottie. Declining Lottie is not a close call.
6. **Rive, for now.** See 3.4.

### 3.4 Rive: what it would buy, and what it costs

Rive is a GPU-accelerated vector engine with state machines, so a designer can
build a graphic whose states map to app states and the app just sets an input
(https://rive.app). That is genuinely the right shape for three moments here:

| Candidate | Why Rive would fit | Verdict |
| --- | --- | --- |
| **Processing-stage indicator.** A run moves through parse, plan, lookup, resolve, normalize, validate, finalize (`evidence_panel.dart:250-258`) and can also enter Processing blocked. | Eight states with defined transitions is exactly a state machine. | Build it as a Flutter stepper first. If reviewers still cannot tell at a glance which stage a run is in, revisit. |
| **Upload accepted mark.** One check, drawn once per accepted item. | A hand-drawn check path is 30 lines of `CustomPainter`. | No. Not worth a native runtime. |
| **Empty-state illustration that responds to state** (`workspace.dart:386-412`, two variants: no records yet, versus no records match these filters). | A single illustration that morphs between the two states. | No. The two states differ by one sentence of copy. An illustration that morphs is decoration wearing a state machine as a costume. |

**Cost of adopting Rive, stated plainly:**

- **Editor seats.** Free tier: 3 collaborative files, 1 project, 1 workspace,
  10 MB asset imports. Cadet $9 per seat per month (3 seats max, exports `.riv`).
  Voyager $32 per seat per month. Enterprise $120 per seat per month
  (https://rive.app/pricing). Exporting a `.riv` at all requires a paid tier.
  For a museum project that is a recurring line item and a procurement
  conversation.
- **Runtime license.** The `rive` and `rive_native` packages are MIT on pub.dev.
  The pricing page lists runtimes as a feature checklist and says nothing about
  runtime fees, so treat "the runtime is free" as unconfirmed rather than
  confirmed before signing anything.
- **Build pipeline.** `rive` 0.14+ is a rewrite: "The core runtime code is now in
  rive_native" and the Dart runtime was replaced with a C++ one. Prebuilt native
  libraries download during the build, with `dart run rive_native:setup` as the
  manual fallback (https://pub.dev/packages/rive). Our CI and any offline build
  machine must be able to reach that host, or must vendor the binaries.
- **Impeller.** The `rive` page warns of rendering and performance discrepancies
  with Impeller on iOS and suggests reproducing with `--no-enable-impeller`
  before filing. Impeller is the default renderer on our primary review device.
- **Review.** A `.riv` is a binary blob. Nobody can review it in a pull request,
  nobody can grep it, and if the person who authored it leaves, it is frozen.
  For a scientific tool with a long maintenance horizon and a small team, that is
  the real cost, not the $9.
- **App size and platform parity.** Native binaries per architecture on Android
  and iOS, plus a WASM payload on web, for animations that are otherwise a few
  hundred lines of Dart.

**Decision: no Rive in v1.** Revisit only if, after the processing-stage stepper
ships and is measured, reviewers still misread run state. If it is ever adopted,
it is adopted for exactly one asset, with a static fallback, behind a feature
flag, and with the `.riv` source `.rev` file committed alongside it.

---

## 4. Interaction catalog

Legend for duration and curve: token names from section 2. "RM" is the reduced
motion behaviour. Haptics: `HapticFeedback` from `package:flutter/services.dart`,
which is a no-op on web and desktop, so every haptic below is implicitly mobile
only; the platform note says what the call actually does. Verified mappings from
`flutter/src/services/haptic_feedback.dart`:

| Flutter call | iOS | Android |
| --- | --- | --- |
| `lightImpact()` | `UIImpactFeedbackGenerator`, style light | `HapticFeedbackConstants.VIRTUAL_KEY` |
| `mediumImpact()` | `UIImpactFeedbackGenerator`, style medium | `HapticFeedbackConstants.KEYBOARD_TAP` |
| `heavyImpact()` | `UIImpactFeedbackGenerator`, style heavy | `HapticFeedbackConstants.CONTEXT_CLICK`, API 23+ |
| `selectionClick()` | `UISelectionFeedbackGenerator` | `HapticFeedbackConstants.CLOCK_TICK` |
| `vibrate()` | `kSystemSoundID_Vibrate` | `HapticFeedbackConstants.LONG_PRESS` |
| `Feedback.forLongPress(context)` | no-op | platform long-press feedback, respects the system haptics setting |

Those five are the **entire** haptic surface in Flutter 3.38.5
(`flutter/src/services/haptic_feedback.dart`). The notification trio
(`successNotification`, `warningNotification`, `errorNotification`, which map to
`UINotificationFeedbackGenerator` on iOS) is newer and **not available on this
toolchain**. That constrains row 51 below: we could not express "this failed" as a
distinct notification haptic even if we wanted to, and faking it with
`heavyImpact()` would say "something heavy happened", not "this failed".

Apple's rules that shape the list: use system patterns "according to their
documented meanings"; "match the intensity and sharpness of a haptic with the
intensity and sharpness of the animation it accompanies"; "Avoid overusing
haptics ... a haptic can feel just right when it happens occasionally, but become
tiresome when it plays frequently"; and, directly relevant to a camera-based
capture app, "Ensure that haptic vibrations don't disrupt experiences involving
device features like the camera, gyroscope, or microphone"
(https://developer.apple.com/design/human-interface-guidelines/playing-haptics).

Android's guidance agrees and adds the frequency rule: "Haptic effects applied to
very frequent events, like scrolling or moving a text handle, should be very
subtle ... More important events, like refreshing a page or submitting a form,
should be stronger", and "Prioritize predefined haptic constants and effects ...
This ensures a consistent user interaction experience, which is particularly
valuable as an accessibility consideration"
(https://developer.android.com/develop/ui/views/haptics/haptics-principles).
Sticking to `HapticFeedback` is exactly that, since every method maps onto a
`HapticFeedbackConstants` value.

Our house rule on top of both: **a haptic fires only when the user cannot be
assumed to be looking at the screen, or when the action is irreversible.** Two
haptics in the whole app pass that test (rows 50 and 67), plus the platform's own
selection clicks. An operator uploading 200 images must not feel 200 buzzes, and
must not feel a buzz while the device is held over a copy stand steadying a shot.

### 4.1 Session and shell

| # | Interaction, trigger | What moves | Duration, curve | RM | Haptic | Flutter approach |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | App launch, cold start | Nothing. Native launch screen holds until the first Flutter frame | n/a | n/a | none | Set the Android `LaunchTheme` windowBackground and the iOS launch storyboard background to `0xfff4f6f3`, matching `scaffoldBackgroundColor` at `main.dart:107`, so there is no flash between the launch screen and the first frame. |
| 2 | Connection setup screen appears (`main.dart:194`) | opacity | `standard` 200, `standard` | instant | none | `AnimatedSwitcher` at the `MaterialApp.home` level, keyed by screen identity. |
| 3 | Sign-in screen first paint | Nothing | n/a | n/a | none | No entrance animation on a first paint the user did not trigger. |
| 4 | Send sign-in link pressed, request in flight (`magic_link_screen.dart:189-200`) | Button label cross-fades to the busy label; button width is held | `quick` 100, `standard` | instant | none | `AnimatedSwitcher` around the label `Text`, wrapped in a `SizedBox` sized to the widest label so the button does not resize. |
| 5 | Magic link sent, "Check your email" state (`magic_link_screen.dart:145-176`) | The heading, body and button label cross-fade. The product icon and title do not move | `standard` 200, `standard` | instant | none | One `AnimatedSwitcher` around the changing text block, keyed by `confirm`/`sent`. Keep the existing `Semantics(liveRegion: true)` at `:172-177`; the announcement, not the fade, is what tells a screen reader user. |
| 6 | Resend cooldown ticking (`magic_link_screen.dart:79-85`) | Nothing. A number changes once per second | `instant` | n/a | none | Plain `Text`. Never animate a counting number: it turns a fact into a slot machine. |
| 7 | Sign-in succeeds, workspace appears | opacity | `emphasized` 350, `standard` | instant | none | Top-level `AnimatedSwitcher`. A context change with no shared element is a fade, which is M3's "top level" pattern: "The exiting screen quickly fades out and then the entering screen fades in" (https://m3.material.io/styles/motion/transitions/transition-patterns). |
| 8 | Sign out (`workspace.dart:570-582`) | opacity, back to sign-in | `standard` 200, `exit` | instant | none | Same switcher. Faster than sign-in, per the M3 exit asymmetry rule. |
| 9 | Environment banner (`workspace.dart:603-612`) | Nothing, ever | n/a | n/a | none | It states a permanent condition of the build, not an event. Animating it would imply it just happened. |
| 10 | Offline or server-unreachable banner (`workspace.dart:665-675`) | height and opacity; content below slides down | `standard` 200 `enter` in, `quick` 100 `exit` out | instant, banner appears and disappears without travel | none | Wrap the banner slot in `AnimatedSize` plus `AnimatedOpacity`. Today it is a bare conditional in a `Column`, so it snaps the layout. Never a snackbar: this message needs a Retry and must persist. |
| 11 | Global load or mutate indicator (`workspace.dart:676-679`) | opacity only | `quick` 100, `standard` | instant | none | Always occupy the 4 px row. Render `LinearProgressIndicator` inside an `Opacity`/`AnimatedOpacity` that goes to 0 rather than removing the widget, so the page never jumps. |
| 12 | Sign-out failure, nav destination change | See row 10 for the error; nav destination change is Material's own `NavigationBar` / `NavigationRail` indicator | Material default | Material default | `selectionClick()` on mobile | Leave `NavigationBar` alone. The destination indicator is already correct M3 motion. |

### 4.2 Queue

| # | Interaction, trigger | What moves | Duration, curve | RM | Haptic | Flutter approach |
| --- | --- | --- | --- | --- | --- | --- |
| 13 | Queue first load, no data yet | Skeleton rows to real rows: opacity | `standard` 200, `standard`. Skeleton shimmer sweep is `skeletonizer`'s own | Skeleton stays, sweep off, cross-fade instant | none | `Skeletonizer(enabled: _loading && _items.isEmpty)` wrapping the real `ListView`, five placeholder rows matching the real `ListTile` metrics. Never a centred `CircularProgressIndicator` over an empty list: it tells the user nothing about what is arriving. M3: "Use skeleton loaders ... Avoid content shifting positions or instantly popping in as it loads" (https://m3.material.io/styles/motion/transitions/applying-transitions). |
| 14 | Quiet poll every 20 s (`workspace.dart:60-70`) | **Nothing**, if the result set is unchanged. Only genuinely changed rows animate | `quick` 100, `standard`, per changed row | instant | none | Diff by `Specimen.id` and `revision` before `setState`. A poll that rebuilds an identical list must produce zero visible motion. This is the single highest-risk slop vector in the app. |
| 15 | Queue row press (`workspace.dart:437`) | Ink ripple only | Material default | Material default | none | `ListTile.onTap`. No scale, no elevation, no colour flash. A ripple is enough. |
| 16 | Queue row hover, desktop and web | Background colour | `quick` 100, `standard` | instant colour change | none | Material's own hover overlay. Do not add scale or shadow. |
| 17 | Queue to workbench, tablet and desktop (list-detail) | Detail pane content: opacity. The list does not move; the selected row gains a persistent selected background | `standard` 200, `standard` | instant | none | Two-pane layout, `AnimatedSwitcher` on the detail pane keyed by specimen id. Do not use a container transform in a two-pane layout: nothing travels between panes, so there is nothing to transform. |
| 18 | Queue to workbench, phone | Platform page transition | Platform default | Platform default | none | Requires a real route (see section 0). Then Flutter 3.38.5's defaults are already correct: `PredictiveBackPageTransitionsBuilder` on Android, `CupertinoPageTransitionsBuilder` on iOS and macOS (`flutter/src/material/page_transitions_theme.dart:1049-1055`). Do not override them. M3 agrees: for forward and backward, "Both Android and iOS should use platform defaults." |
| 19 | Predictive back, Android 13+ | The workbench peels back to reveal the queue, tracking the drag | Platform, 450 ms on release (`FadeForwardsPageTransitionsBuilder.kTransitionMilliseconds`) | Platform | none | Add `android:enableOnBackInvokedCallback="true"` to the `<application>` tag in `android/app/src/main/AndroidManifest.xml`. **It is absent today** (the tag at line 3 has `label`, `name` and `icon` only), so predictive back is currently off. See https://docs.flutter.dev/platform-integration/android/predictive-back. Guard it with `PopScope(canPop: !_mutating)` so a back gesture cannot abandon a save in flight. |
| 20 | Back from workbench, tablet | Detail pane content fades out, list keeps scroll offset | `quick` 100, `exit` | instant | none | Same switcher as row 17. Preserve the list `ScrollController` offset across the swap. |
| 21 | Pull to refresh, phone and tablet touch | Material refresh arc | Material default | Arc still turns; it is a direct response to a gesture in progress | `lightImpact()` at the moment the gesture passes the trigger threshold, iOS and Android | `RefreshIndicator` around the queue `ListView`. Gate on `!kIsWeb && (Android || iOS)`: on web it fights the browser's own pull to refresh. The list must not clear during refresh; existing rows stay in place. |
| 22 | Refresh action in the app bar (`workspace.dart:561-569`) | The global 4 px bar becomes visible | `quick` 100, `standard` | instant | none | Row 11's opacity approach. The icon does not spin. A spinning refresh icon is decoration; the progress bar is the status. |
| 23 | Filter chip toggle (`workspace.dart:352-359`) | The chip's own leading check and container colour | `quick` 100, `standard` | instant | `selectionClick()` on mobile | Leave `FilterChip`'s built-in selection animation. Then row 24 handles the result swap. |
| 24 | Result set changes after a filter, search or sort | Rows cross-fade in place. The list does **not** re-skeleton and does not stagger | `standard` 200, `standard` | instant | none | `AnimatedSwitcher` keyed by a filter generation counter, with `layoutBuilder` set to keep the incoming child aligned top-left so the scroll position does not lurch. The count line at `workspace.dart:381-384` updates with it. |
| 25 | Search typing (`workspace.dart:320-337`) | Nothing until the 350 ms debounce fires | `instant` | n/a | none | Never animate per keystroke. The debounce already exists; do not add a spinner inside the field, which would flicker on every character. |
| 26 | Filters dialog opens (`workspace.dart:368-378`) | Phone: sheet slides up. Tablet and desktop: dialog fades and scales | Phone `emphasized` 350 `emphasizedEnter` in, `standard` 200 `emphasizedExit` out. Desktop `standard` 200, `standard` | instant, no travel | none | `showModalBottomSheet` below 600 px logical width, `showDialog` above. Raise the dialog from Flutter's 150 ms default to `standard` 200 via `AnimationStyle(duration: ..., reverseDuration: ...)`. |
| 27 | Load more records (`workspace.dart:441-445`) | Button label swaps to an inline 16 px indeterminate indicator. Appended rows appear with no entrance animation | `quick` 100, `standard` for the label | instant | none | The new rows are below the fold; animating them animates something nobody can see. Keep the existing disabled state at `:443`. |
| 28 | Empty state (`workspace.dart:386-412`) | opacity, arriving with the rest of the list | `standard` 200, `standard` | instant | none | Static icon, static text. This is the place an animated illustration would go, and we are declining it (section 3.4). |
| 29 | Collection dropdown changed (`workspace.dart:643-654`) | The queue clears and reloads: skeleton, then rows | `standard` 200, `standard` | instant | none | Treat as a fresh load, row 13. The dropdown menu itself uses Material's default. |

### 4.3 Workbench: source image

This is where motion earns its place. Everything here exists to keep the reviewer
oriented in the photograph.

| # | Interaction, trigger | What moves | Duration, curve | RM | Haptic | Flutter approach |
| --- | --- | --- | --- | --- | --- | --- |
| 30 | Source preview bytes decode and paint (`workbench.dart:452-455`) | opacity 0 to 1 | `standard` 200, `enter` | instant | none | `AnimatedOpacity` keyed by `asset['asset_id']`. The `Container` already reserves the box, so nothing reflows. A 40 MP photograph appearing as a hard pop reads as a rendering glitch; a 200 ms fade reads as "it loaded". No blur-up, no progressive reveal. |
| 31 | Pinch and pan inside `InteractiveViewer` (`workbench.dart:462-465`) | The image, tracking the fingers | `instant` | `instant` | none | Untouched. Direct manipulation must be 1:1 with the input, always. Apple: "Strive for realistic feedback motion that follows people's gestures" (https://developer.apple.com/design/human-interface-guidelines/motion). |
| 32 | Zoom in button (`workbench.dart:430-437`) | The transform matrix, 1.0 to 1.3 about the viewport centre | `standard` 200, `standard` | instant jump to the new matrix | none | Today it assigns `_transform.value` directly, which teleports. Drive it with an `AnimationController` plus `Matrix4Tween` and write the interpolated matrix into the `TransformationController` on each tick. |
| 33 | Double-tap to zoom (proposed) | The transform, to 2x centred on the tap point | `emphasized` 350, `emphasized` | instant | none | Same controller as row 32, target matrix computed from the local tap offset. |
| 34 | Reset view (`workbench.dart:438-445`) | The transform to identity **and** the rotation to 0, together | `emphasized` 350, `emphasized` | instant | none | The one sanctioned exception to one-thing-at-a-time: both properties are the same conceptual action, "put the view back". Run them off one controller so they cannot desynchronise. |
| 35 | Rotate view 90 degrees (`workbench.dart:425-429`, `RotatedBox` at `:468`) | rotation, one quarter turn | `emphasized` 350, `emphasizedEnter` | instant quarter turn | none | Replace `RotatedBox(quarterTurns: _rotation)` with `AnimatedRotation(turns: _rotation / 4, ...)`. Justification in one sentence: without seeing the turn, the reviewer loses track of which edge of the label was the top, and label orientation is evidence. |
| 36 | Region chip selected (`workbench.dart:582-592`) | The visible rect of the image, from whole image to the region's bbox | `emphasized` 350, `emphasized` | instant re-crop | `selectionClick()` on mobile | **The most valuable animation in the app.** Today `:589` resets the transform to identity and the tree swaps between a whole-image branch and a crop branch (`:482-511`), so the image teleports. Instead, keep one image widget and animate the `TransformationController` from the current matrix to the matrix that frames the bbox. The reviewer keeps a spatial model of where on the specimen that label sits, which is the entire point of "source first". |
| 37 | Region overlay tapped on the image (`workbench.dart:536-561`) | Same as row 36 | `emphasized` 350, `emphasized` | instant | `selectionClick()` on mobile | Same code path. Tapping the box and tapping the chip must animate identically or the two controls will not feel like the same control. |
| 38 | Region overlay highlight, hover or keyboard focus | Stroke colour and stroke width, 2 px to 3 px | `quick` 100, `standard` | instant colour change, no width change | none | Repaint through the single overlay `CustomPainter` (section 6.6), not per-region widgets. Stroke width must be divided by the current scale so it stays 3 logical pixels at 12x zoom instead of 36. |
| 39 | Whole image button (`workbench.dart:446-449`) | The transform back to the full-frame matrix | `emphasized` 350, `emphasized` | instant | none | Row 36 in reverse. |
| 40 | Region chips reflow when the region list changes | Chip labels cross-fade; no reorder animation | `quick` 100, `standard` | instant | none | A `Wrap` cannot animate reordering, and building that is not worth it. The chips are numbered "Label 1..N" (`workbench.dart:583-586`), so a 100 ms label cross-fade carries the change. Say no here explicitly; this is a place where an animation would cost a week and buy nothing. |

### 4.4 Workbench: record, panels and decisions

| # | Interaction, trigger | What moves | Duration, curve | RM | Haptic | Flutter approach |
| --- | --- | --- | --- | --- | --- | --- |
| 41 | Tab change: Readings, Fields and evidence, History (`workbench.dart:1118-1130`) | Panel content: 30 px horizontal offset plus opacity. Forward, meaning left to right in the chip row, means the incoming panel enters from the right and the outgoing exits to the left, on LTR | `standard` 200, `standard` | fade only at `quick` 100, zero offset | `selectionClick()` on mobile | `AnimatedSwitcher` with a paired `SlideTransition` and `FadeTransition`, or `PageTransitionSwitcher` with `SharedAxisTransition(transitionType: horizontal)` if `animations` 2.2.0 is adopted. **30 px, not full width**: the panel sits beside a stationary photograph, and a full-width slide next to a still image makes the image look like it moved. Mirror the direction under `Directionality.of(context) == TextDirection.rtl`. |
| 42 | Chip selection state on the tab chips | The chip's own check and fill | `quick` 100, `standard` | instant | folded into row 41 | `ChoiceChip` built-in. |
| 43 | Expand an evidence or field `ExpansionTile` (`workbench.dart:742-749`, `:892-935`, `:941-948`) | height and the rotation of the trailing chevron | `standard` 200, `standard` | instant | none | `ExpansionTile` already animates at 200 ms. Override the curve to `Easing.standard` via `ExpansionTileTheme`. Do not enforce one-open-at-a-time: reviewers compare fields side by side. |
| 44 | Lazy evidence load, button pressed (`evidence_panel.dart:46-66`) | The button label swaps to an inline 16 px indeterminate indicator; the button stays in place | `quick` 100, `standard` | instant | none | Today the label just changes text. Keep the button footprint fixed so the layout does not move while the request is out. |
| 45 | Lazy evidence content arrives | The button collapses and the content expands: height plus opacity | `standard` 200, `enter`, **capped** | instant | none | `AnimatedSize` plus `AnimatedOpacity`. **Cap rule:** if the incoming content measures taller than 400 px, skip the size animation and fade only. These payloads are unbounded JSON dumps; animating a 3000 px expansion produces a two-second scroll lurch. |
| 46 | Lazy evidence load fails (`evidence_panel.dart:35-40`) | The error text appears in place of nothing: height plus opacity | `standard` 200, `enter` | instant | none | The existing `Semantics(liveRegion: true)` at `:63` stays and is the primary channel. No shake, no red flash. |
| 47 | Edit dialog or reason sheet opens (`workbench.dart:116-300`, `:334-381`, `evidence_panel.dart:88-150`, `region_editor.dart:61`) | Phone: sheet slides up. Tablet and desktop: dialog fades and scales | Phone `emphasized` 350 `emphasizedEnter`. Desktop `standard` 200, `standard` | instant, no travel | none | `showModalBottomSheet` under 600 px, `showDialog` above, with `AnimationStyle` to lift the dialog off Flutter's 150 ms default. Focus moves to the first field immediately; focus is never animated. |
| 48 | Edit dialog or sheet dismissed | Reverse of row 47 | `standard` 200, `emphasizedExit` | instant | none | Also: replace the four hard-coded `await Future.delayed(Duration(milliseconds: 250))` calls (`workbench.dart:302`, `:1098`, `evidence_panel.dart:151`, `operational_panel.dart:72`) with the token. Flutter's dialog reverse transition is 150 ms today (`flutter/src/material/dialog.dart:1681`), so the 250 ms sleep is a guess with 100 ms of slack. Better still: hoist the `TextEditingController`s into a `StatefulWidget` dialog and dispose them in `State.dispose`, which removes the timing dependency entirely. |
| 49 | Save in flight (`workspace.dart:265-300`, `widget.busy`) | The pressed button's label swaps to an inline indeterminate indicator; the button width is held. The global 4 px bar becomes visible | `quick` 100, `standard` | instant | none | Never a full-screen blocking overlay, and never dim the record: the reviewer must still be able to read the evidence they just judged while the request is out. Other actions disable through the existing `_blocked()` logic (`workbench.dart:56-60`). |
| 50 | **Save succeeded, disposition changes** (`workspace.dart:283-288`) | The disposition chip's fill colour and label cross-fade; a check glyph scales from 0.6 to 1.0 with opacity 0 to 1 | Colour and label `standard` 200, `standard`. Check `emphasized` 350, `emphasizedEnter` | Colour and label at `quick` 100; check appears at full size, no scale | `mediumImpact()`, iOS and Android mobile only | `AnimatedContainer` for the chip, `AnimatedSwitcher` for the label, `AnimatedScale` plus `AnimatedOpacity` for the check. Also fire `SemanticsService.announce` with the new disposition. **Delight moment 1**, justified in section 4.7. The revision number next to it (`workbench.dart:994`) changes with no animation: it is a fact, not an event. |
| 51 | Save conflict, stale revision (`workspace.dart:292-295`) | An inline error card appears above the actions: height plus opacity | `standard` 200, `enter` | instant | **none** | `AnimatedSize` plus `AnimatedOpacity`. Deliberately no haptic and deliberately no shake: the message is a paragraph the reviewer has to read and act on, and a buzz adds urgency without adding information. Deliberately not a snackbar: it must persist until dismissed. Keep the `liveRegion`. |
| 52 | Retry processing requested (`workbench.dart:1051-1107`) | Dialog or sheet per row 47; then row 49 | as rows 47 and 49 | as rows 47 and 49 | none | Unchanged flow, tokenised timings. |
| 53 | Retry scheduled countdown (`operational_panel.dart:118-119`) | Nothing. Text ticks once per second | `instant` | n/a | none | Render `next_retry_at` as a relative countdown in text. **No ring, no filling bar.** We do not know the retry will fire at that instant, and a determinate indicator would assert a certainty the server never gave us. If a ring is ever added, it must be driven from the server timestamp, never from a local animation start time. |
| 54 | Lease held, actions blocked (`operational_panel.dart:126`, `workbench.dart:61-70`) | Nothing | n/a | n/a | none | Disabled buttons plus text. A blocked state is a condition, not an event. |
| 55 | Processing stage indicator (proposed) | Completed connector lines fill left to right as a stage completes; the current stage carries a 2 px indeterminate bar | `standard` 200, `standard` per connector | Connectors fill instantly; the current-stage bar keeps moving (it is progress) | none | Seven-step stepper over the phases at `evidence_panel.dart:250-258`, plus a Processing blocked state that is visually distinct and never shown as a final queue. **On first paint, stages that were already complete are drawn already complete.** Never replay history as if it just happened. |
| 56 | Reading diff, character-level highlight (`workbench.dart:656-680`) | Nothing | `instant` | n/a | none | The highlight appears with the text. No typewriter, no sequential reveal, no fade-in per span. A diff is a static comparison and animating it implies a sequence that does not exist. |
| 57 | Historical revision opened (`audit_history.dart`) | Panel content: opacity | `standard` 200, `standard` | instant | none | `AnimatedSwitcher` keyed by revision. Never a shared axis here: moving back through time is not a peer relationship, and a slide would imply one. |
| 58 | Snackbar (`workbench.dart:317-323`) | Material default | Material default | Material default | none | Keep the one that exists. House rule: snackbars are for transient confirmations that need no decision. Anything that needs a Retry, a reason, or a re-read goes inline (row 51). |
| 59 | Keyboard focus traversal, any screen | Nothing | `instant` | n/a | none | A reviewer tabbing through forty fields must never wait 100 ms per stop. Focus rings are instant, always. |
| 60 | Scroll, any list | Platform physics | Platform | Platform | none | Untouched. No scroll-linked reveals, no parallax headers, no collapsing hero. |

### 4.5 Intake

| # | Interaction, trigger | What moves | Duration, curve | RM | Haptic | Flutter approach |
| --- | --- | --- | --- | --- | --- | --- |
| 61 | Choose files or Take photograph pressed (`intake.dart:491-501`) | Buttons disable | `quick` 100, `standard` | instant | none | The OS picker owns the transition. The app adds nothing on top of it. |
| 62 | Camera capture returns, new manifest card (`intake.dart:193-308`) | If the manifest was empty: no entrance animation. If it already had cards: the new card fades and expands | `standard` 200, `enter` | instant | none | `AnimatedList` or `SliverAnimatedList` `insertItem` with a `SizeTransition` plus `FadeTransition`. **Fade and size, not slide**: the card did not come from anywhere. |
| 63 | Interrupted capture recovered (`intake.dart:312-349`) | The recovery message appears: height plus opacity | `standard` 200, `enter` | instant | none | The existing `liveRegion` at `:528-534` is the real channel. |
| 64 | Manifest row state text changes: Ready, Checking manifest, Uploading, Accepted, Duplicate, Failed (`intake.dart:364-424`, rendered at `:563`) | The state text and a leading status glyph cross-fade. Row height does not change | `quick` 100, `standard` | instant | none | `AnimatedSwitcher` keyed by state string, with `layoutBuilder` pinning the child so the row does not resize. Keep the `Semantics(liveRegion: true)` wrapper. |
| 65 | Upload progress (`intake.dart:391-393`, rendered at `:623-627`) | The bar value | `standard` 200, `progress` (linear) | **Keeps animating.** This is data | none | Three fixes. (a) Render the bar for every state from Checking onward, not only while the state string equals `Uploading`; today it disappears at the moment it hits 1.0. (b) Use `value: null` for Checking manifest and a real value for Uploading. (c) Wrap the value in `TweenAnimationBuilder<double>` at `standard` 200 linear, and clamp to a monotonic maximum so a resumed upload that reports a lower server offset never runs the bar backwards. |
| 66 | Upload accepted, one item (`intake.dart:405-410`) | The bar holds at 1.0 for 400 ms, then the glyph cross-fades to a check | `quick` 100, `standard` for the glyph | instant | **none** | No per-item haptic. A 200-image batch would produce 200 buzzes. |
| 67 | **Upload batch complete, all selected items accepted** | One summary line appears at the top of the manifest: height plus opacity | `standard` 200, `enter` | instant | `lightImpact()`, iOS and Android mobile only, **once per batch** | **Delight moment 2**, justified in section 4.7. Fire it in the `finally` at `intake.dart:426` only when every entry in the batch reached Accepted or Duplicate. |
| 68 | Duplicate detected (`intake.dart:376-383`) | Glyph and text cross-fade | `quick` 100, `standard` | instant | none | A duplicate is a correct outcome, not an error. It gets the same motion as Accepted and a different glyph. No colour flash. |
| 69 | Upload failed or interrupted (`intake.dart:413-424`) | Error text and a retry affordance appear: height plus opacity | `standard` 200, `enter` | instant | none | No shake, no colour pulse. The `Upload / resume` button at `:636` is already the retry. |
| 70 | Server preflight (`intake.dart:586-596`) | Button label swaps to an inline indicator; the result block expands below | `quick` 100 for the label, `standard` 200 `enter` for the block, with the row 45 cap | instant | none | Same pattern as lazy evidence. |
| 71 | Sensitivity dropdown changed (`intake.dart:460-476`) | Material's dropdown menu | Material default | Material default | none | Untouched. |
| 72 | Quality checkbox toggled (`intake.dart:515-522`) | Checkbox mark | Material default | Material default | `selectionClick()` on mobile | Untouched. Then the Upload button's enabled state changes with a `quick` 100 colour transition (Material default). |

### 4.6 Region editor (`region_editor.dart`)

| # | Interaction, trigger | What moves | Duration, curve | RM | Haptic | Flutter approach |
| --- | --- | --- | --- | --- | --- | --- |
| 73 | Label chip selected (`region_editor.dart:84-89`) | The preview rectangle travels from the old bbox to the new one | `standard` 200, `standard` | instant | `selectionClick()` on mobile | `AnimatedPositioned` inside the existing `LayoutBuilder` `Stack` at `:102-144`. Justification: it is the only cue that connects the abstract label "Label 3" to a physical place on the specimen. |
| 74 | Coordinate field edited (`region_editor.dart:164-186`) | The rectangle follows the number, with **zero** animation | `instant` | `instant` | none | Set the duration to zero here deliberately, and comment why: typing a number and watching the box lag 200 ms behind makes the reviewer distrust the coordinate. Direct manipulation is 1:1. |
| 75 | Rotate label reading (`region_editor.dart:149-156`) | The preview rotation, one quarter turn | `emphasized` 350, `emphasizedEnter` | instant | none | `AnimatedRotation` on the preview only. Source coordinates do not change, and the copy at `:146-148` already says so. |
| 76 | Merge with next (`region_editor.dart:223-242`) | The selected rectangle grows to the union of the two; one chip disappears | `standard` 200, `standard` | instant | none | `AnimatedPositioned`. This is the one place in the editor where a shape change is the literal explanation of a data change, so it is worth animating. |
| 77 | Add label region (`region_editor.dart:246-253`) | New rectangle appears at full image bounds: opacity | `standard` 200, `enter` | instant | none | `AnimatedOpacity`. It appears at the whole-image bbox (`:45-52`), which is deliberately unmissable. |
| 78 | Delete region (`region_editor.dart:194-204`) | Rectangle disappears: opacity | `quick` 100, `exit` | instant | none | Faster out than in, per section 2.4. |
| 79 | Move earlier or later (`region_editor.dart:205-222`) | Chip labels cross-fade as the numbering changes | `quick` 100, `standard` | instant | none | See row 40: no reorder animation in a `Wrap`. |
| 80 | Invalid coordinate, save attempted (`region_editor.dart:263-267`, `:278-304`) | Error text appears: height plus opacity | `standard` 200, `enter` | instant | none | No shake. The message names the fix; the motion just gets it on screen without a jump. |

### 4.7 Delight moments

Three were considered. Two are approved. The third is deliberately banked.

**Approved 1: save succeeded, the disposition chip changes (row 50).** This is the
only moment in the product where a human commits an attributable, versioned,
consequential decision about a museum record. Confirmation that it landed, and
landed as the disposition they expected, is worth 350 ms and one medium impact
haptic. The reviewer is looking at the screen, so the haptic is redundancy rather
than the primary channel, which is exactly what Apple recommends for supplementing
information that must not be motion-only.

**Approved 2: upload batch complete (row 67).** The operator is at a copy stand,
possibly gloved, and is not watching the screen while a batch of 200 uploads. One
light impact and one summary line is the smallest possible signal that the batch
is done and they can move the next drawer. Per-item feedback is banned for exactly
the same reason: 200 buzzes is not feedback, it is noise.

**Declined and banked: the empty state, and the processing-stage indicator.** The
empty state (`workspace.dart:386-412`) is the classic place a product puts an
animated illustration, and here it would be pure decoration: the two variants
differ by one sentence of copy. The processing-stage indicator (row 55) is a
better candidate but must first be proven necessary as a plain stepper. We are
spending two of three and saying so, rather than filling the slot.

---

## 5. Choreography rules

### 5.1 Stagger

Default: **no stagger anywhere.** Where a stagger is proposed, all four conditions
must hold, and if any fails, it is cut:

1. At most four items stagger. The fifth and beyond appear with the fourth.
2. Offset is 30 ms. Total added latency is therefore at most 120 ms.
3. It runs only on the **first** paint of a data set, keyed by a load generation
   counter, never on refresh, poll, pagination or filter change.
4. The list is not one that auto-updates.

Applied to this app, condition 3 and 4 rule out the queue (`workspace.dart:60-70`
polls every 20 s) and the intake manifest (rows append during a batch). Nothing in
section 4 staggers. The rule exists so that the next person who wants one has to
argue against it, not for it.

### 5.2 One thing at a time

One user action animates at most one element's position or size. Colour and
opacity changes may run concurrently on other elements. The two sanctioned
composites, both because they are one conceptual action:

- Reset view (row 34): transform and rotation, off a single controller.
- Region select (row 36): the crop change and the chip check, where the chip check
  is a colour change and therefore does not count against the budget.

Global ceiling: two concurrent authored animations on screen, excluding the 4 px
progress bar.

### 5.3 Direction

- **Peer content at the same level** uses a horizontal shared axis: the workbench
  tabs (row 41), and nothing else. Forward, meaning left to right in the chip row
  on LTR, sends the incoming panel in from the right and the outgoing one out to
  the left. Read the direction from `Directionality.of(context)` and mirror under
  RTL; do not hard-code positive offsets.
- **Hierarchy** uses the platform page transition, not a shared axis. Going into a
  record on a phone is a route push (row 18). M3 is explicit that a lateral
  pattern for hierarchical navigation "implies an equal peer relationship which
  isn't accurate" (https://m3.material.io/styles/motion/transitions/applying-transitions).
- **Top-level destination changes** (Queue and Intake, `workspace.dart:585-600`
  and `:684-698`) use a fade, never a slide. M3's top-level pattern is a fade
  precisely because a slide implies swipeability, and these destinations are not
  swipeable.
- **Travel distance is capped at 30 px** for any in-page slide. Full-width slides
  are reserved for route transitions, which the platform owns.

### 5.4 Keeping the source image stable

Four rules, because this is the one thing a reviewer must be able to trust:

1. The source image subtree is owned by a widget **above** the tab and panel
   switchers, keyed by asset id only. A tab change must not rebuild it. In the
   wide layout (`workbench.dart:1181-1189`) it is already a sibling of `content`;
   keep it that way when the panel switcher is introduced.
2. The `TransformationController` (`workbench.dart:74`) survives every panel
   change. It resets only on the events already handled at
   `workbench.dart:76-86`: a new `active_run_id`, or the selected region
   disappearing.
3. Panel transitions offset by 30 px, not full width (row 41). A large horizontal
   slide immediately adjacent to a static photograph produces induced motion: the
   photograph appears to drift the other way.
4. Region selection animates the transform rather than swapping the widget tree
   (row 36). Two different subtrees cross-fading is a cut; one transform
   animating is a camera move, and only the second preserves the reviewer's
   spatial model.

### 5.5 Progress

- **Monotonic.** Clamp every reported value to the maximum seen for that entry.
  `intake.dart:391-393` writes the raw callback value; a resumed upload can report
  a lower server offset and would run the bar backwards.
- **Never reset.** A retry that starts a new attempt gets a new row or an
  explicit "Attempt 2" label. It does not reuse the same bar from zero without
  saying so.
- **Never switch determinate to indeterminate mid-operation.** Hold the last value
  and change the label instead. Dropping from 74 percent to a spinning circle
  reads as data loss.
- **Never fill on completion of an unrelated event.** The bar reaches 1.0 because
  the bytes are there, not because the request returned.
- **Never animate faster than the truth.** The 200 ms linear catch-up smooths
  jitter between real values; it never runs ahead of the last reported value.
- **Already-complete is drawn already complete.** A stage indicator opened on a
  half-finished run draws the finished stages as finished, with no fill animation.
  Replaying history as if it were happening now is a lie about when it happened,
  in a product whose entire premise is a traceable history.

---

## 6. Implementation notes

### 6.1 `PageTransitionsTheme`

Flutter 3.38 is the release that changed the Android default from
`ZoomPageTransitionsBuilder` to `PredictiveBackPageTransitionsBuilder`, falling
back to `FadeForwardsPageTransitionsBuilder` when predictive back is unavailable
(https://docs.flutter.dev/release/breaking-changes/default-android-page-transition).
The side effect that matters here: **the Android page transition duration went
from 300 ms to 450 ms.** Any widget test that pumps a hard-coded 300 ms past a
route push is now wrong; see section 6.3.

The defaults are already right for mobile
(`flutter/src/material/page_transitions_theme.dart:1049-1055`):
`PredictiveBackPageTransitionsBuilder` on Android,
`CupertinoPageTransitionsBuilder` on iOS and macOS,
`ZoomPageTransitionsBuilder` on Windows and Linux. Override only the desktop and
web entries, to the Material 3 forward transition:

```dart
// main.dart, inside ThemeData(...)
pageTransitionsTheme: const PageTransitionsTheme(
  builders: <TargetPlatform, PageTransitionsBuilder>{
    // Platform defaults, restated so a future SDK change is a visible diff.
    TargetPlatform.android: PredictiveBackPageTransitionsBuilder(),
    TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
    TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
    // Desktop and web: the Material 3 forward transition.
    TargetPlatform.windows: FadeForwardsPageTransitionsBuilder(),
    TargetPlatform.linux: FadeForwardsPageTransitionsBuilder(),
    TargetPlatform.fuchsia: FadeForwardsPageTransitionsBuilder(),
  },
),
```

`FadeForwardsPageTransitionsBuilder` runs 450 ms
(`kTransitionMilliseconds`, `page_transitions_theme.dart:713`) on
`Curves.easeInOutCubicEmphasized`, slides the outgoing page 25 percent, and fades
the incoming page over the first 75 percent of the animation. Its own dartdoc
notes 450 ms is an approximation of native Android's 800 ms spring, "because
native Android is using Material 3 Expressive springs that are not currently
supported by Flutter", which is the same gap section 2.1 describes.

Predictive back also needs a manifest change that is **not present today**:

```xml
<!-- android/app/src/main/AndroidManifest.xml -->
<application
    android:label="Specimen Digitization"
    android:name="${applicationName}"
    android:icon="@mipmap/ic_launcher"
    android:enableOnBackInvokedCallback="true">
```

See https://docs.flutter.dev/platform-integration/android/predictive-back.
Pair it with `PopScope(canPop: !_mutating, ...)` around the workbench so a back
gesture cannot abandon an in-flight save (`workspace.dart:265-300`).

### 6.2 `MotionTokens` as a `ThemeExtension`

One file, one source of truth. Every duration in the app goes through it.

```dart
// lib/src/design/motion_tokens.dart
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

/// Motion tokens for the app. Durations and curves come from Flutter's
/// generated Material 3 token constants (`Durations`, `Easing`); this class
/// names them for product use and folds in the reduced-motion policy.
@immutable
class MotionTokens extends ThemeExtension<MotionTokens> {
  const MotionTokens({this.reduced = false});

  /// True when the platform asks for reduced motion. Set by [of].
  final bool reduced;

  // Raw tokens. Do not read these directly from widgets; call [d].
  static const Duration instantRaw = Duration.zero;
  static const Duration quickRaw = Durations.short2; // 100 ms
  static const Duration standardRaw = Durations.short4; // 200 ms
  static const Duration emphasizedRaw = Durations.medium3; // 350 ms
  static const Duration slowRaw = Durations.long2; // 500 ms

  // Curves are compile-time constants and are not affected by [reduced];
  // a zero-duration animation never samples them.
  static const Curve standardCurve = Easing.standard; // (0.2, 0, 0, 1)
  static const Curve enterCurve = Easing.standardDecelerate; // (0, 0, 0, 1)
  static const Curve exitCurve = Easing.standardAccelerate; // (0.3, 0, 1, 1)
  // Note: there is no `Easing.emphasized`. The full emphasized curve is a
  // ThreePointCubic and only exists on Curves.
  static const Curve emphasizedCurve = Curves.easeInOutCubicEmphasized;
  static const Curve emphasizedEnterCurve = Easing.emphasizedDecelerate;
  static const Curve emphasizedExitCurve = Easing.emphasizedAccelerate;
  static const Curve progressCurve = Curves.linear;

  Duration get instant => Duration.zero;
  Duration get quick => d(quickRaw);
  Duration get standard => d(standardRaw);
  Duration get emphasized => d(emphasizedRaw);
  Duration get slow => d(slowRaw);

  /// Collapses a decorative duration to zero under reduced motion.
  Duration d(Duration token) => reduced ? Duration.zero : token;

  /// Motion that carries information (progress) keeps its duration.
  /// Call this explicitly so every exception is visible in the diff.
  Duration meaningful(Duration token) => token;

  /// Reads the tokens and the live reduced-motion state.
  ///
  /// Four sources, because no single one covers our platforms on Flutter 3.38:
  ///   Android  -> MediaQueryData.disableAnimations
  ///   iOS      -> AccessibilityFeatures.reduceMotion (MediaQuery omits it)
  ///   Web      -> our own matchMedia bridge (the engine reports nothing)
  ///   Any      -> an explicit in-app preference, so a user on any platform
  ///               can force it without changing an OS setting.
  static MotionTokens of(BuildContext context) {
    final base =
        Theme.of(context).extension<MotionTokens>() ?? const MotionTokens();
    return base.copyWith(reduced: prefersReducedMotion(context));
  }

  static bool prefersReducedMotion(BuildContext context) =>
      MotionPreference.of(context).forceReducedMotion ||
      MediaQuery.disableAnimationsOf(context) ||
      SemanticsBinding.instance.accessibilityFeatures.reduceMotion ||
      platformPrefersReducedMotion(); // web bridge; false elsewhere

  @override
  MotionTokens copyWith({bool? reduced}) =>
      MotionTokens(reduced: reduced ?? this.reduced);

  /// Durations are discrete tokens; interpolating them is meaningless.
  @override
  MotionTokens lerp(MotionTokens? other, double t) =>
      t < 0.5 ? this : (other ?? this);
}
```

Register it once:

```dart
// main.dart
theme: ThemeData(
  useMaterial3: true,
  // ... existing theme ...
  extensions: const <ThemeExtension<dynamic>>[MotionTokens()],
),
```

`AccessibilityFeatures` is not an inherited widget, so a change to iOS Reduce
Motion while the app is running will not rebuild anything by itself. Wrap the app
once:

```dart
// lib/src/design/motion_scope.dart
class MotionScope extends StatefulWidget {
  const MotionScope({super.key, required this.child});
  final Widget child;
  @override
  State<MotionScope> createState() => _MotionScopeState();
}

class _MotionScopeState extends State<MotionScope>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAccessibilityFeatures() => setState(() {});

  @override
  Widget build(BuildContext context) => widget.child;
}
```

### 6.2b The web bridge and the in-app preference

Because the 3.38.5 web engine never reports `prefers-reduced-motion`
(section 2.5), web needs its own reader. Use the conditional-import pattern the
repo already uses for `email_link_browser.dart`:

```dart
// lib/src/design/reduced_motion_platform.dart
export 'reduced_motion_platform_stub.dart'
    if (dart.library.js_interop) 'reduced_motion_platform_web.dart';

// lib/src/design/reduced_motion_platform_stub.dart
bool platformPrefersReducedMotion() => false;

// lib/src/design/reduced_motion_platform_web.dart
import 'package:web/web.dart' as web;

bool platformPrefersReducedMotion() =>
    web.window.matchMedia('(prefers-reduced-motion: reduce)').matches;
```

`package:web` is not currently a dependency; it is a small, first-party
(dart.dev) package and is the supported way to reach `matchMedia` from Dart. To
react to a change while the tab is open, add a listener on the same
`MediaQueryList` and rebuild `MotionScope`. **Delete this bridge when the app
moves to Flutter 3.44 or later**, where the engine reports it, and leave a TODO
saying so next to the `dependency_overrides` block in `pubspec.yaml` that already
tracks the 3.44 upgrade.

Alongside it, ship a real setting. `shared_preferences` is already a dependency
(`pubspec.yaml`), so a `MotionPreference` inherited widget backed by a
`reduce-motion-v1` bool costs almost nothing and is the only way a reviewer on a
managed desktop, who cannot change OS accessibility settings, can turn motion off.
Surface it next to sign out, labelled "Reduce motion", with the helper text
"Removes sliding and zooming. Progress bars keep moving."

Use at the call site:

```dart
final motion = MotionTokens.of(context);
return AnimatedRotation(
  turns: _rotation / 4,
  duration: motion.emphasized,
  curve: MotionTokens.emphasizedEnterCurve,
  child: child,
);
```

Two supporting facts, both verified against the installed SDK:

- Passing `Duration.zero` is safe. `AnimationController._animateToInternal`
  short-circuits a zero simulation duration: it sets the value, fires the status
  change and returns a completed `TickerFuture` without starting a ticker
  (`flutter/src/animation/animation_controller.dart:673-684`).
- On Android and web the framework is already helping: when
  `SemanticsBinding.instance.disableAnimations` is true, any controller with the
  default `AnimationBehavior.normal` runs at 5 percent duration
  (`animation_controller.dart:651`), and implicit animation widgets use the
  default behaviour (`flutter/src/widgets/implicit_animations.dart:362-366`).
  `MotionTokens` exists to cover iOS, where that flag is never set, and to make
  the intent explicit rather than emergent.

Lint the rule: add a repo check (a `dart analyze` custom lint, or a CI grep) that
fails on `Duration(milliseconds:` inside `lib/src/**` outside
`lib/src/design/motion_tokens.dart`, with an allowlist for the debounce and poll
timers in `workspace.dart`.

### 6.3 Testing animations

Three test shapes. All use the existing `flutter_test` conventions in `test/`
(plain `MaterialApp` wrappers, no extra harness).

**A. Assert an animation runs and settles.** `pump()` with no argument starts the
ticker; `pump(Duration)` then advances the clock by exactly that amount and
produces **one** frame, not a frame per 16 ms. Both steps are needed.

```dart
testWidgets('region selection animates the crop over 350 ms', (tester) async {
  await tester.pumpWidget(_workbench());
  await tester.tap(find.text('Label 2'));
  await tester.pump(); // start the ticker; without this nothing animates
  await tester.pump(const Duration(milliseconds: 175)); // midpoint
  expect(_currentScale(tester), greaterThan(1.0));
  expect(_currentScale(tester), lessThan(_targetScale));
  await tester.pump(const Duration(milliseconds: 175)); // end
  expect(_currentScale(tester), closeTo(_targetScale, 0.001));
});
```

Do not reach for `pumpAndSettle` on any screen that shows a
`CircularProgressIndicator` or `LinearProgressIndicator` with `value: null`. It
loops on `binding.hasScheduledFrame`, an indeterminate indicator never clears
that flag, and it throws after its ten-minute default timeout. Use explicit
`pump(Duration)` steps, or `pumpFrames(widget, maxDuration)` when you need a
bounded number of real frames out of an infinite animation.

Route transitions: after Flutter 3.38's Android default change (section 6.1), a
hard-coded `pump(Duration(milliseconds: 300))` past a push no longer clears the
transition. Use `TransitionDurationObserver` from `flutter_test`
(`flutter_test/lib/src/navigator.dart:19`) in `navigatorObservers` and
`await observer.pumpPastTransition(tester)` instead of any literal.

**B. Assert reduced motion collapses to a single frame.** The important trap:
**wrapping a test in `MediaQuery(data: MediaQueryData(disableAnimations: true))`
does not disable framework animations.** `AnimationController` reads
`SemanticsBinding.instance.disableAnimations`
(`flutter/src/animation/animation_controller.dart:651`), not `MediaQuery`. A
`MediaQuery` override only affects widgets that literally call
`MediaQuery.disableAnimationsOf`, which in our case means `MotionTokens` and
nothing else. Test both layers, and test the iOS path explicitly, because that is
the one production will actually hit on an iPad:

```dart
// The real mechanism: fake the platform's accessibility features. This drives
// the whole chain, including AnimationController's own 5 percent scaling.
testWidgets('Android Remove animations collapses the crop animation',
    (tester) async {
  tester.platformDispatcher.accessibilityFeaturesTestValue =
      const FakeAccessibilityFeatures(disableAnimations: true);
  addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);

  await tester.pumpWidget(_workbench());
  await tester.tap(find.text('Label 2'));
  await tester.pump(); // one frame, no clock advance
  expect(_currentScale(tester), closeTo(_targetScale, 0.001));
  expect(tester.hasRunningAnimations, isFalse);
});

// The iPad case. reduceMotion never sets disableAnimations, so this test fails
// against any implementation that only reads MediaQuery.
testWidgets('iOS Reduce Motion collapses the crop animation', (tester) async {
  tester.platformDispatcher.accessibilityFeaturesTestValue =
      const FakeAccessibilityFeatures(reduceMotion: true);
  addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);

  await tester.pumpWidget(_workbench());
  await tester.tap(find.text('Label 2'));
  await tester.pump();
  expect(_currentScale(tester), closeTo(_targetScale, 0.001));
  expect(tester.hasRunningAnimations, isFalse);
});
```

`FakeAccessibilityFeatures` and `accessibilityFeaturesTestValue` both exist in
3.38.5 (`flutter_test/lib/src/window.dart:23-43` and `:527-537`), and the fake
carries `reduceMotion`. `debugSemanticsDisableAnimations`
(`flutter/src/semantics/debug.dart:12`, read at
`flutter/src/semantics/binding.dart:225-231`) is the lighter alternative for the
Android path only; it is ignored in non-debug builds and does not set
`reduceMotion`.

Make this a shared helper and run it over every screen, not just the workbench:

```dart
void expectNoRunningAnimations(WidgetTester tester) =>
    expect(tester.hasRunningAnimations, isFalse,
        reason: 'A motion token was bypassed. All durations must go through '
            'MotionTokens.d().');
```

**C. Assert progress is monotonic.** A plain unit test over the clamping helper,
no widgets: feed it 0.1, 0.4, 0.9, 0.3, 1.0 and assert the emitted series is
0.1, 0.4, 0.9, 0.9, 1.0.

**D. Assert the haptic budget.** One test per delight moment asserting the haptic
fired exactly once, by installing a mock handler on `SystemChannels.platform` via
`TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
.setMockMethodCallHandler` and counting `HapticFeedback.vibrate` calls (all five
Flutter haptics arrive as that one method name, distinguished by the argument).
Add the inverse test too: a simulated 20-item upload batch must produce exactly
one call, not twenty. That is the only way to catch a per-item haptic regression
before an operator feels it 200 times.

### 6.4 Performance checklist: `InteractiveViewer` with overlays

Current code, for reference: `workbench.dart:452-575`. Six items, in priority
order.

1. **Move the overlays out of the transformed subtree.** They are inside the
   `InteractiveViewer` child today (`:512-567`), so `Border.all(width: 3)`
   (`:543-546`) renders at 36 logical pixels at `maxScale: 12` (`:464`), directly
   over the label. Draw them in a sibling `Stack` layer above the viewer, and
   compute their screen rects from the `TransformationController`'s matrix, so
   stroke width stays constant regardless of scale.
2. **One `CustomPainter` for all regions, not one widget per region.** Today each
   region builds its own `LayoutBuilder` wrapping a `Stack` wrapping a
   `Positioned` (`:518-566`). A specimen with twelve labels builds twelve
   `LayoutBuilder`s that all resolve to the same constraints. Replace with a
   single `CustomPaint` whose painter takes the region list, the matrix and the
   hovered/selected ids, and whose `shouldRepaint` compares those three.
3. **`RepaintBoundary` around the image.** Wrap `SourcePixels` in a
   `RepaintBoundary` so overlay repaints, which happen on every hover and every
   selection change, do not force the decoded photograph to re-rasterise.
4. **Drop the redundant `ClipRect`.** `workbench.dart:461` wraps the viewer in a
   `ClipRect`, but `InteractiveViewer` already defaults to
   `clipBehavior: Clip.hardEdge` (`flutter/src/widgets/interactive_viewer.dart:71`).
   Two clips means an extra layer for no benefit.
5. **Do not animate a raw `Opacity` over the image.** Flutter's own rule is
   "Avoid using the `Opacity` widget, and particularly avoid it in an animation.
   Use `AnimatedOpacity` or `FadeInImage` instead"
   (https://docs.flutter.dev/perf/best-practices). Row 30's fade-in is an
   `AnimatedOpacity` on the image itself, which is fine because it runs once for
   200 ms. Never put an animated `Opacity`, `ShaderMask` or `ColorFilter` above a
   transformed photograph on a repeating basis: each is a documented `saveLayer`
   trigger, and `saveLayer` "allocates an offscreen buffer and drawing content
   into the offscreen buffer might trigger a render target switch ... On mobile
   GPUs this is particularly disruptive to rendering throughput." Check for
   accidental ones with `checkerboardOffscreenLayers` in the DevTools performance
   view.
6. **Trackpad behaviour on desktop and web.** `InteractiveViewer` defaults
   `trackpadScrollCausesScale: false`
   (`interactive_viewer.dart:88`), so a two-finger trackpad scroll pans rather
   than zooms. Verify that against reviewer expectation on a MacBook before
   shipping; a reviewer who expects pinch-to-zoom semantics and gets pan will
   report it as a bug.

Five general rules that apply app-wide, all from
https://docs.flutter.dev/perf/best-practices:

- **Pass a pre-built `child`** into `AnimatedBuilder` and `TweenAnimationBuilder`.
  Flutter's wording: "avoid putting a subtree in the builder function that builds
  widgets that don't depend on the animation. This subtree is rebuilt for every
  tick of the animation."
- **Avoid clipping in an animation.** "If possible, pre-clip the image before
  animating it." This is another reason row 36 animates the transform rather than
  animating a clip rect.
- **Prefer `borderRadius` over a clipping widget** for rounded corners, and never
  use `Clip.antiAliasWithSaveLayer`, which is the one clip mode that does call
  `saveLayer`.
- **Be lazy in long lists.** The queue must stay on `ListView.builder`, not a
  concrete children list, once it holds more than a screenful.
- **Budget.** 16 ms per frame at 60 Hz, split roughly 8 ms build and 8 ms raster;
  8 ms total on a 120 Hz iPad Pro. Measure in **profile mode on a real iPad**,
  never in debug.

Renderer status, which matters for the Rive caveat in section 3.2 and for web:
Impeller has been the default on iOS and Android API 29+ since Flutter 3.27, and
on iOS it is the only option with no fallback to Skia; older Android or
non-Vulkan devices fall back to the legacy OpenGL renderer; **web still uses
Skia** (https://docs.flutter.dev/perf/impeller). So a rendering behaviour verified
on the iPad is not automatically verified in Chrome, and both are first-class
targets here.

### 6.5 `skeletonizer` configuration

```dart
Skeletonizer(
  enabled: _loading && _items.isEmpty,
  // The sweep is decorative; the grey blocks are the information. The shimmer
  // is a repeat() loop, which AnimationBehavior.preserve does NOT shorten
  // under reduced motion (section 2.5), so it must be swapped out by hand.
  effect: MotionTokens.prefersReducedMotion(context)
      ? const SolidColorEffect(color: Color(0xffe7ebe7))
      : const ShimmerEffect(duration: Duration(milliseconds: 1200)),
  child: _queueList(),
)
```

Two rules: skeletons render the **real** row widgets with placeholder data, so
the skeleton cannot drift from the layout; and the skeleton is used only for a
first load with no data, never for a refresh of a list that already has rows
(row 24).

### 6.6 Where the code changes land

| File | Change |
| --- | --- |
| `lib/src/design/motion_tokens.dart` | New. Section 6.2. |
| `lib/src/design/motion_scope.dart` | New. Section 6.2. |
| `lib/src/design/motion_preference.dart` | New. The stored "Reduce motion" setting, section 6.2b. |
| `lib/src/design/reduced_motion_platform{,_stub,_web}.dart` | New. Web `matchMedia` bridge, section 6.2b. Delete on the 3.44 upgrade. |
| `pubspec.yaml` | Add `skeletonizer: ^3.0.0` and `web: ^1.1.0`. Add `animations: ^2.2.0` only when routes land, pinned below 3.0.0 until Flutter 3.44. |
| `lib/main.dart` | `pageTransitionsTheme`, register `MotionTokens`, wrap in `MotionScope` and `MotionPreference`, top-level `AnimatedSwitcher` for rows 2, 7, 8. |
| `android/app/src/main/AndroidManifest.xml` | `android:enableOnBackInvokedCallback="true"`. |
| `lib/src/workspace.dart` | Rows 10, 11, 13, 14, 21, 24, 27. Reserve the progress row; diff before `setState` in the poll. |
| `lib/src/workbench.dart` | Rows 30, 32, 34, 35, 36, 41, 45, 49, 50, 51. Extract the source viewer into its own widget with an `AnimationController` for the matrix. |
| `lib/src/intake.dart` | Rows 62, 64, 65, 66, 67. Fix the progress bar visibility condition at `:623`. |
| `lib/src/region_editor.dart` | Rows 73 to 80. |
| `lib/src/evidence_panel.dart` | Rows 44, 45, 46. |
| `test/motion_tokens_test.dart` | New. Section 6.3 B and C. |

---

## 7. Do and do not

| Do | Do not |
| --- | --- |
| Write the one-sentence justification before writing the animation. | Add an animation because the screen "feels static". |
| Use `Durations` and `Easing` from `package:flutter/material.dart`. | Type `Duration(milliseconds: 250)` into a widget. |
| Use `Curves.easeInOutCubicEmphasized` for the M3 emphasized curve. | Reach for `Easing.emphasized`. It does not exist. |
| Use `Easing.legacy` if you deliberately want the M2 curve, and say so. | Use `Curves.fastOutSlowIn` thinking it is "the Material curve". Flutter documents it as the name for `Easing.legacy`, which is M2. |
| Pass an explicit `curve:` to every implicitly animated widget. | Omit it. `ImplicitlyAnimatedWidget` defaults to `Curves.linear`, not `easeInOut`. |
| Give `AnimatedSwitcher` children distinct `ValueKey`s. | Rely on it to transition between two children of the same type and key. It will not; it treats them as the same widget. |
| Read `MediaQuery.disableAnimationsOf`, `AccessibilityFeatures.reduceMotion`, and a web bridge. | Assume `MediaQuery` covers iOS or web. It covers neither, in 3.38.5. |
| Override reduced motion in tests with `FakeAccessibilityFeatures`. | Wrap a test in `MediaQuery(disableAnimations: true)` and expect framework animations to stop. `AnimationController` never reads `MediaQuery`. |
| Animate the image transform when a region is selected. | Cross-fade between a whole-image widget and a crop widget. |
| Keep in-page slides to 30 px. | Slide a panel full-width next to a stationary photograph. |
| Reserve space for the progress bar and animate its opacity. | Insert and remove a `LinearProgressIndicator` from a `Column`. |
| Clamp progress to a monotonic maximum. | Write the raw upload callback value straight into the bar. |
| Draw already-complete stages as already complete on first paint. | Replay a run's history as if it were happening now. |
| Show an inline, persistent error for a save conflict. | Put a decision-requiring error in a snackbar. |
| Fire one haptic per batch. | Fire one haptic per uploaded item. |
| Keep the `Semantics(liveRegion: true)` wrappers and add `SemanticsService.announce` for the disposition change. | Let an animation be the only signal that a save landed. |
| Let the platform own route transitions. | Hand-roll a page transition to make Android look like iOS. |
| Use skeletons for a first load with no data. | Re-skeleton a list that already has rows during a refresh. |
| Cap `AnimatedSize` on unbounded evidence payloads at 400 px. | Animate a 3000 px JSON expansion. |
| Test that reduced motion collapses to a single frame. | Ship a motion spec with no reduced-motion test. |
| Say no to an animation and write down why. | Add a package so that adding animations is easier. |

---

## Sources

Material 3:
- https://m3.material.io/styles/motion/overview
- https://m3.material.io/styles/motion/easing-and-duration/tokens-specs
- https://m3.material.io/styles/motion/easing-and-duration/applying-easing-and-duration
- https://m3.material.io/styles/motion/transitions/transition-patterns
- https://m3.material.io/styles/motion/transitions/applying-transitions
- https://m2.material.io/design/motion/the-motion-system.html

Apple:
- https://developer.apple.com/design/human-interface-guidelines/motion
- https://developer.apple.com/design/human-interface-guidelines/accessibility
- https://developer.apple.com/design/human-interface-guidelines/playing-haptics
- https://developer.android.com/develop/ui/views/haptics/haptics-principles

Flutter:
- https://docs.flutter.dev/ui/animations
- https://docs.flutter.dev/ui/animations/tutorial
- https://docs.flutter.dev/platform-integration/android/predictive-back
- https://docs.flutter.dev/release/breaking-changes/default-android-page-transition
- https://docs.flutter.dev/release/breaking-changes/android-predictive-back
- https://docs.flutter.dev/perf/best-practices
- https://docs.flutter.dev/perf/impeller
- https://docs.flutter.dev/perf/rendering-performance
- https://docs.flutter.dev/cookbook/testing/widget/introduction
- https://api.flutter.dev/flutter/dart-ui/AccessibilityFeatures-class.html
- https://api.flutter.dev/flutter/dart-ui/AccessibilityFeatures/reduceMotion.html
- https://api.flutter.dev/flutter/widgets/MediaQueryData/disableAnimations.html
- https://api.flutter.dev/flutter/material/Durations-class.html
- https://api.flutter.dev/flutter/material/Easing-class.html
- https://api.flutter.dev/flutter/animation/Curves/easeInOutCubicEmphasized-constant.html
- https://api.flutter.dev/flutter/animation/Curves/fastOutSlowIn-constant.html
- https://api.flutter.dev/flutter/animation/AnimationBehavior.html
- https://api.flutter.dev/flutter/widgets/AnimatedSwitcher-class.html
- https://api.flutter.dev/flutter/widgets/TweenAnimationBuilder-class.html
- https://api.flutter.dev/flutter/widgets/AnimatedBuilder-class.html
- https://api.flutter.dev/flutter/widgets/ImplicitlyAnimatedWidget-class.html
- https://api.flutter.dev/flutter/widgets/RepaintBoundary-class.html
- https://api.flutter.dev/flutter/material/PredictiveBackPageTransitionsBuilder-class.html
- https://api.flutter.dev/flutter/material/FadeForwardsPageTransitionsBuilder-class.html
- https://api.flutter.dev/flutter/flutter_test/WidgetTester/pump.html
- https://api.flutter.dev/flutter/flutter_test/WidgetTester/pumpAndSettle.html
- https://api.flutter.dev/flutter/flutter_test/FakeAccessibilityFeatures-class.html
- https://api.flutter.dev/flutter/widgets/PopScope-class.html
- Installed SDK source, Flutter 3.38.5 (revision f6ff1529fd), read directly for
  every token value, default duration and platform mapping cited above:
  `packages/flutter/lib/src/material/motion.dart`,
  `.../material/page_transitions_theme.dart`,
  `.../material/predictive_back_page_transitions_builder.dart`,
  `.../material/dialog.dart`, `.../material/expansion_tile.dart`,
  `.../animation/curves.dart`, `.../animation/animation_controller.dart`,
  `.../widgets/media_query.dart`, `.../widgets/implicit_animations.dart`,
  `.../widgets/animated_switcher.dart`, `.../widgets/interactive_viewer.dart`,
  `.../widgets/feedback.dart`, `.../services/haptic_feedback.dart`,
  `.../semantics/binding.dart`, `.../semantics/debug.dart`,
  `bin/cache/pkg/sky_engine/lib/ui/window.dart`.

Packages (pub.dev pages and the pub.dev API, read 2026-09-13):
- https://pub.dev/packages/animations
- https://pub.dev/packages/flutter_animate
- https://pub.dev/packages/skeletonizer
- https://pub.dev/packages/shimmer
- https://pub.dev/packages/rive
- https://pub.dev/packages/rive_native
- https://pub.dev/packages/lottie
- https://rive.app
- https://rive.app/pricing

Accessibility and research:
- https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html
- https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html
- https://support.google.com/accessibility/android/answer/11183305
- https://developer.android.com/reference/android/provider/Settings.Global
- https://developer.android.com/reference/android/animation/ValueAnimator
- https://www.nngroup.com/articles/animation-duration/
- https://www.nngroup.com/articles/response-times-3-important-limits/
</content>
</invoke>
