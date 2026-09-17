# What the front-end refactor taught

Between 2026-09-16 and 2026-09-17 the Specimen Digitization client's whole
presentation layer was replaced. Material 3 with product tokens on it became an
in-repo design system, `specimen_ui`, built on `package:flutter/widgets.dart`:
a foundation of tokens, fifteen primitives, thirty controls, a browsable
gallery, fifteen gates, and every screen in the application rebuilt on top of
it. Twenty two agent slots did it across eight waves, on one integration branch,
and it goes to `main` as a single pull request.

This document is what the work taught, distilled from the twenty two closeouts
in [`SESSION_LEARNINGS.md`](SESSION_LEARNINGS.md) and from the status log in
[`execution/FRONT_END_REFACTOR.md`](execution/FRONT_END_REFACTOR.md) section
13. It is written for whoever runs the next refactor of this size, in this
repository or another. Each lesson names the slot it came from, so the evidence
is one search away.

What moved, measured rather than described:

| | At the cut | At the pull request |
|---|---|---|
| Material component uses under `lib/` | 208 over 50 files | 0 |
| Files importing `material.dart` under `lib/` | 43 | 4, each named with its reason |
| Material glyphs | 161 over 43 files | 0 |
| Static sizes outside the foundation | not measured | package 0, application 10, all elapsed time |
| Package tests | 0 | 685 |
| Application tests | 1062 passed, 7 skipped | 1301 passed, 7 skipped |
| Checked-in goldens | 121 screen | 121 screen, 336 gallery, 8 semantics fixtures |
| Device captures | 0 for this client | 43 |

## 1. The protocol

**One integration branch, and no agent ever commits to it.**
`front-end-refactor` was cut from `main` at `f05d496` and every slot was cut
from its current head. A slot works in its own worktree, pushes its own branch,
and hands back; the integrator merges with `git merge --no-ff`, resolves,
reruns the gates, regenerates the checked-in binaries, pushes, and removes the
worktree. Twenty two slots became one reviewable pull request carrying one
verification report. The alternative, twenty two pull requests against `main`,
would have put a half-migrated client in production twenty two times. From the
plan, section 6.

**A slot owns files, not features, and the brief names every one of them.**
The five control families were built simultaneously by five agents who shared
exactly three files: their family barrel, `CHANGELOG.md` and the gallery shell.
The merge protocol named those three in advance as the only expected conflicts
and they were the only ones. Ownership is what makes parallelism safe; a brief
that names a feature instead of a file is a brief that will collide. From the
plan section 6 and the wave 1 closeouts.

**Two branches that reach the same answer must write the same text.** Slots C1
and C3 independently found that registering a gallery page in the list the
foundation goldens draw in their sidebar moves all twenty four of them, and
independently invented the same three-list fix. The second branch then rewrote
its version by hand to be byte identical to the first's, so the merge was a one
line addition rather than a conflict. `fe/inputs` and `fe/navigation` did the
same with `pressable.dart` and `state_layer.dart`, taken verbatim from
`fe/actions` `bdb0fbc` in a commit of their own. Two branches solving one
problem differently is a merge conflict; two branches solving it identically is
a merge. From the C3 correction and the C4 closeout.

**Every rule is a test, and a rule with exceptions carries a backlog that only
shrinks.** Fifteen gates hold this system: tokens only, no Material component,
no Material import, one glyph per meaning, fonts bundled, no dashes, composite
contrast, import direction, no stand-ins, no fallback text style, the glass
budget, the fifteen clause control contract, the string checklist, and two
static geometry censuses. Each gate that could not start at zero carries a
`Map<String, int>` of file to count that a test asserts may only shrink. That
one mechanism is what let five waves burn 208 Material uses down to zero
without anyone tracking it by hand. From 10 section 8 and every screen slot.

**Merge two backlog maps by intersection, never by union.** When two slots each
empty their own entries from the same map, the merged map must keep only what
both sides still list. Taking either side's file wholesale silently reinstates
the other's cleared entries, and the gate then passes against a tree that no
longer matches it. Every wave 3 merge resolved the four maps this way. From the
wave 3 entry in the status log.

**A gate that reaches zero is widened before it is believed.** A backlog map is
a claim about a scan, not about a tree. `no_material_imports` had been reporting
zero over three named directories, which is how an unused `material.dart`
import survived five waves in `workspace.dart`, a file the scan never looked
at. The cleanup slot dropped the directory list, scanned all of `lib/`, and
added a second test asserting that each of the four allowed importers still
imports it, so a file that stops needing the permission loses it. From the H1
cleanup closeout.

**Checked-in binaries are regenerated once per wave, by the integrator.** Two
branches that both regenerate a golden revert one another with no conflict and
no warning: Git sees a binary, takes one side, and nothing fails. So no slot
branch may contain a regenerated screen golden or semantics fixture. A slot
runs `--update-goldens` once to look at the result, records the set that moved,
and reverts with `git checkout --`. From the plan section 8, held by every slot
from wave 1 on.

**Predict the moved set before reading it, and treat the difference as a
finding.** Slot E5 expected twenty four screen goldens to move and twenty four
moved; the ninety seven that held byte for byte were the other half of the
check, because they proved that nothing the slot touched reached them. Wave 0
expected all 121 to move and all 121 did, because the faces had never been
bundled and every glyph before it was a filled box. The shell slot moved 111,
and the ten that held were exactly the windows in the set that draw no shell.
A moved set that matches the prediction is a stronger statement than a green
suite, because it names what did not change as well as what did. The case it
cannot cover is the one that appears only at the merge: three application tests
failed after the shell and the queue were merged together, because the shell
had turned the queue's static placeholder into a pulsing skeleton, which
neither slot's own suite could see. From the E5, E1 and wave 0 closeouts and
the wave 2 status log entry.

**A slot that needs a sibling's control builds a stand-in, marks it, and the
marker is a gate.** Six `TODO(fe/<family>)` stand-ins existed at the end of
wave 1 and all six were swapped for the real control in wave 1.5. A stand-in
that outlives its wave is a second implementation of a control, which is
exactly what one vocabulary exists to prevent, so `no_stand_ins` was added to
make it a rule rather than an intention. Where a coordination note is needed
that is not a stand-in, it is spelled `fe/<slot>:` rather than `TODO(fe/`,
because weakening a gate to carry a note is the worse trade. From the wave 1.5,
F1 and G2 closeouts.

**Decide rather than ask, and record the decision beside the measurement that
forced it.** No slot in this refactor stopped to ask a question. Where a
document was ambiguous, the slot chose, and wrote a paragraph naming the
reading it took and the evidence for it. Slot E6 could not read "the head sits
1 dp above geometric centre" literally, because a head whose centre sits
there leaves the pin's tip 12.5 dp below the centre of a disc whose radius is
12, so the pin leaves its own disc. It rendered both readings, measured them,
took the one that satisfies every other number in the specification, and
amended the document. That is faster than asking and it
leaves a record that asking would not. From the E6 closeout.

**Review by eye, on a real surface, after everything is green.** Both of the
two documents that reshaped this system came from a human looking at the built
client while every gate passed. Checkpoint 1 was a browsable gallery, and the
three defects seen in it produced `11-fit-and-scale.md`. The morning emulator
review of the record screen at 390 by 844 produced `13-screen-composition.md`.
Neither set of defects had a test that could have caught it, because neither
had a rule yet. Build the review surface early; it is the only instrument that
finds the rules you have not written. From the status log for 2026-09-16 and
2026-09-17.

**The closeout is the deliverable that outlives the branch.** Every slot
appends task, branch, outcome, commits, the gates with their exit codes and
their numbers, the goldens it moved, durable learnings, failed approaches,
deviations with reasons, and what the next slot will need. `.gitattributes`
marks `docs/SESSION_LEARNINGS.md` `merge=union`, so two branches appending to
the end never conflict; that works only while the ritual holds, because union
would otherwise keep two versions of an edited region. This document is made
entirely of those closeouts. From `AGENTS.md` and `.gitattributes`.

## 2. The machine

These cost real time in this repository, on macOS, with several worktrees live
at once.

**zsh does not word split an unquoted parameter.** `pre-commit run --files
$FILES` runs against nothing, reports "no files to check" and exits 0: a gate
passing because it checked nothing. Read the list into an array
(`FILES=("${(@f)$(cat list)}")`) and pass `"${FILES[@]}"`. From the C4 closeout.

**Read `rc=$?` directly, and never off a pipe.** `status` is read-only in zsh,
so `status=$?` fails. A pipe reports the exit code of its last stage, so
`flutter test | tail` is always 0 and a red suite reads as green. Run each gate
on its own with the tree untouched, capture `rc=$?` on the next line, and
report that number. From the plan, section 7.

**A long gate in a busy worktree gets reaped.** `verify.sh` runs both Flutter
suites, and a Git or Flutter command issued against the same worktree while it
runs will kill it with a bare exit code and no failing test. With several agent
worktrees live on one machine this is the common failure, not the rare one. Run
the gates the script contains one at a time, leave the tree alone while each
runs, and never diagnose a killed run as a failed one. From the wave briefs and
the plan section 7.

**Read a Flutter test log from a file, after `tr '\r' '\n'`.** `flutter test`
draws its progress with carriage returns, so grepping a live stream matches the
overwritten line rather than the result. Redirect to a file under a scratch
directory, wait for the process, then translate and read. From the wave briefs.

**The Write and Edit tools may be scoped to a directory other than the
worktree.** Create and change files through Bash with a heredoc or a short
Python script instead. Check this in the first minute of a slot rather than in
its last. From the wave briefs.

**Rerun `flutter analyze` after the last file is written.** Two
`unawaited_futures` infos in a test file written after the previous analyze run
survived to the gate stage, where `--fatal-infos` caught them. The gate order
in the plan exists for this. From the wave 1.5 closeout.

**`dart format` on this tree moves lines you did not write.** Running it on one
file reflowed eighty lines of a method the slot never touched, and twelve of
thirty one files under `controls/` change under the pinned Dart 3.10.4
formatter. Wave G's integration formatted the whole tree once and every gate
run has checked formatting since, so this is now a non-issue; before a tree is
formatted once, format only the lines you wrote. From the wave 1.5 and G1
closeouts.

### The Flutter test harness

**Goldens render every glyph as a filled box when no font is loaded.** The 121
screen goldens checked in before this refactor were rendered in Ahem, so they
were evidence of layout and of nothing else. The first wave to bundle a face
moves all of them, once, and that regeneration is the baseline every later diff
is read against. From the wave 0 closeout.

**A package font resolves under a prefixed family name.**
`TextStyle(fontFamily: 'Geist', package: 'specimen_ui')` is
`packages/specimen_ui/Geist`, and `PhosphorIconData` sets `fontPackage`, so its
family is `packages/phosphor_flutter/PhosphorRegular`. A `FontLoader` registered
under the bare name loads a face nothing asks for, and every glyph renders as a
box with no error at all. From the wave 0 closeout.

**Creating the test binding installs an `HttpOverrides` that answers every
request with a mock 400.** A `flutter_test_config.dart` that calls
`TestWidgetsFlutterBinding.ensureInitialized()` in order to load a font
therefore breaks every test that does real loopback HTTP: thirty six of them
here, all reporting "The request did not complete". Restore whatever override
was in place before the binding was created. Any wave that adds a global test
configuration meets this. From the wave 0 closeout.

**A repeating animation makes `pumpAndSettle` time out.** Every gallery golden
calls it, so a page with a spinner, a shimmer or a pulse on it wraps that
specimen in `TickerMode(enabled: false)`. The same applies to an application
test that drives a batch past a loading button, and to any fixture harness that
settles while a skeleton is on screen. From the C1, E1 and E5 closeouts.

**A golden presses no key, so no focus ring is ever drawn in one.** The ring is
gated on `FocusHighlightMode.traditional` and the test binding starts in
`touch`. A golden that wants a focused control has to set
`FocusManager.instance.highlightStrategy = FocusHighlightStrategy.alwaysTraditional`.
The same gate silently makes a hover assertion pass vacuously. From the C1 and
C2 closeouts.

**`flutter_test` reuses widget state across `pumpWidget` calls in one test.**
Two pumps of structurally identical trees update the element tree rather than
rebuilding it, so a select left open by one assertion is still open at the
next. Split such a test in two rather than trusting a fresh pump. From the C2
closeout.

**`RenderRepaintBoundary.toImage()` never completes when awaited under the
test's own clock.** The rasteriser runs on a real frame, so the capture has to
sit inside `tester.runAsync`, which is the route `matchesGoldenFile` takes
internally. Awaited directly, the test hangs silently rather than failing: it
sat at `+3` for three minutes before it was killed. From the E6 closeout.

**Goldens are compared on macOS and rendered everywhere else.** Linux
rasterises the same bundled fonts one to eleven percent differently, which
failed all 336 package goldens on the first CI run of the pull request. The
comparator renders the golden on other platforms, so every layout, overflow and
semantics assertion in the same test still runs, sets the pixel comparison
aside, and refuses `--update-goldens` off macOS so no file is written by a
platform that did not draw the rest of the set. From the 2026-09-17 status log
entry.

**A gate with a mode switch measures nothing in the gap.** The composition
harness read only `PinnedChrome` markers the moment one was mounted anywhere,
and fell back to a list of widget types only in a tree with none, so the first
merge to mount a marker (the scaffold, around the top bar, the band and the
navigation) silently dropped every region no screen had marked yet. The record
screen measured 27 percent of the phone with its decision bar uncounted, against
54 with it, and the shrink-only ratchet then demanded the backlog line be
deleted, which is a false green wearing the gate's own words. Measure the old
form and the new in one walk, outermost only, for as long as both exist; a
switch that picks one is right only at the two ends of the migration. From the
wave A integration.

**Two green slots merge into a red screen, and the gate says green.** Slot A2
made the record publish its decision bar into the frame's action bar slot; slot
A3 made the queue give the slot back with a null when a record is pushed over
it. Each branch passed every test. Merged, the queue's null arrived one frame
after the record's bar and cleared it, so the record had no decision bar at any
window, and the chrome budget read the missing region as a screen well inside
its budget. Three of the wave's four integration defects were of this shape: a
last write to a shared slot from a screen that no longer held it, a nearer ask
(the shell's band form by window) shadowing a farther one (the record's), and
one ask (hide the navigation) read wider than its clause (hide the pill). When
two slots publish into one seam, run the seam's tests on the merged tree before
the gates, and print the parts a gate sums, not only the share: 27 percent with
five regions and 27 percent with four are different screens. From the wave A
integration.

**A shared slot is a contract about who may write null.** `UiScaffoldSlots`
took an owner so that `release(owner)` gives back only what that owner holds,
and every setter then accepted a null from anyone. The owner has to bind the
null as well as the value, or the first screen to say "I no longer need this"
takes the next screen's chrome with it; a null that names no one is the only
outright clear, and it belongs to `release` alone. The same rule applies to any
ambient a screen publishes and a frame reads. From the wave A integration.

## 3. The design lessons

**Every layer was correct and nobody owned the seam.** Checkpoint 1 found a
focused field drawing three edges, control labels breaking one letter to a line
in a narrow column, and dialog text underlined twice in yellow. None of the
three had a faulty layer. The field's three edges were a bridge theme, a
primitive and a control each painting one, correctly, by its own lights. The
yellow underline was `MaterialApp`'s fallback text style reaching a route the
package published nothing over, which two slots had then patched at L5 and L4
for an L1 responsibility. The letter-by-letter labels were twenty five files
that each drew text and none of which declared a width policy. Three ownership
rules closed all three classes at once: one text style source, one width policy
per control, one edge per control. When a defect has no faulty layer, the bug
is that a seam has no owner, and the fix is to give it one. From
`11-fit-and-scale.md` section 0 and the F1 and F2 closeouts.

**The fit contract: what a control does with less room than it needs is
declared, not discovered.** A control has an intrinsic width, its widest label
at the current text scale plus its padding and glyphs. Given at least that it
lays out as the gallery draws it. Given less: a label never wraps, a control
never shrinks below its intrinsic width, it switches to the compact variants it
declares in order, and only when none fits does the label end in an ellipsis
with the whole of it on the tooltip and the semantics label. Parents own
arrangement; a row of buttons wraps or stacks by window class and never asks a
child to shrink. Content is not a label and wraps as content should. Three
control contract clauses and a 288 golden matrix, four window classes by three
text scales by two modes, hold it. From `11-fit-and-scale.md` section 3.3 and
the G1, G2 and G3 closeouts.

**A height that holds text is never a constant.** It is
`max(density height, scaled line height + 2 * inset)`, where the inset is what
reproduces the density height at scale 1.0, so a control is unchanged at
ordinary text size and grows above it without a second number. The related
finding is subtler: every type role needs `TextLeadingDistribution.even`.
Flutter splits the leading a `height` multiplier adds in proportion to ascent
and descent, and Geist's asymmetry then floats text above the centre of its
line box. Material's own 2021 typography sets `even` on every style, so text
drawn under a `Material` was already correct and text the package drew was not,
which is why "the text sits high" was a design system symptom and never a
Material one, and why exactly the windows whose words are drawn outside a
`Material` were the goldens that moved. From the F2 closeout.

**The composition contract: the controls were right and the screen was
wrong.** After every screen was migrated, the record screen on a phone still
put the readings, which are the work, below the fold. A scroll inside a scroll,
chrome taking about three quarters of the height, surfaces inside surfaces, and
no priority: four causes, none of them a control defect. Every pinned region
had been laid out as if the window were tall and nobody added them up. The
rules are one scroll per screen per axis, a surface depth of one at compact, a
pinned chrome budget of 28 percent of the viewport at compact, one job per
region with nothing repeating another region's words, and the primary region
visible at its minimum height within the first viewport. A component library is
necessary and not sufficient: a screen is a second contract, and it needs its
own gates. From `13-screen-composition.md` section 0.

**A number that must be written down becomes a token, with no per-line escape
hatch.** The static geometry gate began as four sample patterns and became a
census of every `BorderRadius`, `Radius`, `Duration`, `EdgeInsets`,
`BoxConstraints`, `Offset`, `Size` and named dimension in both trees, run as two
tests so the design system can hold itself to zero while the application burns a
backlog down. Deliberately there is no way to silence one line: a number that
genuinely has to exist goes to the foundation. The census also taught that one
pattern can mean two things, because `Duration` in the package is motion and
`Duration` in the application is elapsed time, with opposite resolutions, so
the backlog says which is which or the next agent reaches for a motion token to
fix an HTTP timeout. From the G4 closeout.

**A golden proves the picture did not move; it cannot state the rule.** The
mark's geometry is pinned by cases that sample the rendered pixels and assert 16
dp of pin, 9 dp above the centre and 7 below, a 5 dp head and a 2 dp shaft.
Without them, the optical rise being wrong would have shown as a diff nobody
could name. The companion rule is that a golden which reviews the top of a page
is not reviewing the controls below the fold: every family golden window in this
package is measured against its own page with a throwaway test, not guessed, and
one family's window can grow without moving another family's files. From the E6,
C1 and G2 closeouts.

**An instrument can be wrong, and three sightings make it a property rather
than a coincidence.** `textContrastGuideline` takes the most frequent colour on
each side of a luminance threshold across a node's whole rectangle, so for a
node much wider than its glyphs both frequencies land on the background and it
reports a ratio between two shades of the same thing: 0.66:1 for a top bar
title that measures 11.22:1, 1.06:1 for a disclosure header that measures
17.10:1. Ten of the seventeen failures in the dark mode sweep were that. It was
met independently by a slot whose heading was stretched across a pane, a slot
whose control straddled a scroll fold, and a slot pumping a package surface
inside Material's scrim. Read the pixels before you write the defect. From the
wave 0, E3, E4 and H3 closeouts.

**The semantics tree is the other half of a screen, and a checked-in fixture is
what shows it moving.** The fixtures caught a queue heading, summary and
freshness line sharing one live region, so a screen reader heard the whole
phrase again every second as the age ticked; an intake capture card that was
one merged node holding a forty word paragraph with eight controls under it;
and a filter form whose six group headings merged into one label the moment its
scroller moved. None of those is visible in a screenshot and none fails a
layout assertion. From the E2, E5 and polish 2 closeouts.

**Accessibility roles in this SDK have sharp edges.** Seven `SemanticsRole`
values (`tooltip`, `progressBar`, `loadingSpinner`, `dragHandle`, `spinButton`,
`comboBox`, `hotKey`) map to `_unimplemented` in Flutter 3.38.5 and raise on the
first frame that publishes one; where a role is unusable, the property carrying
the same meaning is used instead. `SemanticsRole.tabBar` requires every child
node to carry `tab`, so a focus node or a label node between the bar and its
tabs fails the whole frame rather than degrading, which is why a composite
control's own `Shortcuts` is built with `includeSemantics: false`. And two
`Semantics` configurations that set the same flag cannot merge, so when wrapping
an SDK control, state only what it does not. From the C2, C3 and C4 closeouts.

## 4. Failed approaches

**Publishing the test harness's tokens below the navigator.** `uiHarness` put
`UiTheme` inside `home`, so every modal pushed in a package test fell back to
the light tokens and the first dark mode sheet golden came out with a light
pane and an inverted button. It reads as a token defect and is a harness defect.
The slot that found it could not fix it, because three sibling slots were live
on the same file and moving it would have moved their goldens, so it lifted the
theme by hand at its own call sites and recorded the fix for the integration
slot, which made it once and moved nothing: the hand-lifted theme and the
harness one resolve to the same tokens. The lesson is both halves, the defect
and the timing. From the C3 and wave 1.5 closeouts.

**Registering a gallery page in the list the foundation goldens draw.** The
shell renders one sidebar row per page, so adding a family page changes the
sidebar in all twenty four foundation captures, and then changes it again for
each of the next four families. Two slots reached this independently. The fix
belongs to the golden rather than to the registration: the foundation golden
pins its own page list explicitly, and the shell carries three lists so
`/gallery` can still show everything. From the C1, C2 and C3 closeouts.

**Asserting a rule by reading a private painter's `toString`.** A private
`CustomPainter` prints its type and nothing else. The rule moved into a small
public value type with one factory, and the test asserts the rule directly,
which is the better shape anyway: the reduced motion substitution became a named
thing rather than a branch inside a builder. From the C5 closeout.

**Timing a web frame from outside the page.** Four attempts, all dead ends: a
synthetic wheel event on `flt-glass-pane`, which is 0 by 0 and not the input
target; the same on `flutter-view`, which the engine does not accept; a resize
event to the same size, which Flutter ignores; and nudging the view's CSS width
a pixel each frame, which never changed the canvas. The automation surface also
throttles `requestAnimationFrame` between tool calls, so the frame cadence
measured was the display's own. An in-app probe using
`SchedulerBinding.addTimingsCallback` that draws its own results on screen took
twenty minutes and produced the same three numbers on the web, an iOS simulator
and an Android emulator, readable from a screenshot. One instrument that makes
the device tell you the number beats three that make you infer it. From the H3
closeout.

**Sharing one scanner between two gate tests.** Three ways were tried and all
three were rejected: putting it in the package's shipped `lib/` drags `dart:io`
into a web compile; putting it in the application's scripts leaves the package
test unable to import it; and a relative import across the package boundary is a
known way to get two copies of one library anyway. The two files now carry the
same scanner on purpose, each says so in its header, and the eight behaviour
assertions in each are identical, so a change made to one and not the other
fails visibly. From the G4 closeout.

**Bounding a scrolling sheet body by arithmetic over its chrome.** Subtracting
a computed chrome height from the window is a second rule for one measurement,
and it is wrong twice over: the pane sits inside a `SafeArea`, so the window's
height is not the height the route left, and the action row's real height is
the button's rather than the derived one. One `Flexible` around the padded
block is exact, because the layout already knows what the safe area took. The underlying
trap is worth stating on its own: a `Column` hands an inflexible child an
unbounded main axis, which is why the inner `Flexible` had nothing to be
flexible against and a filter sheet overflowed a phone by 1044 dp. From the G2
closeout.

**Keeping `MaterialPageRoute` for a full window surface.** It is the only route
`PageTransitionsTheme` reaches, so keeping it was defensible, but it brings
`material.dart` with it and the import gate is per file and does not read a
`show` clause, so the slot's exit criterion and the route could not both be met.
The replacement is a `PageRouteBuilder` with the same emphasized pair, and the
cost is the platform's own back gesture, which a bare `PageRouteBuilder` has no
answer for. That cost is why the product still has two full window entrances and
why a `UiPageRoute` is the one package API the cleanup slot still wanted. From
the E3 and H1 closeouts.

**Capping a list row's trailing column at a share of the row's width.** It
survives 200 percent text and truncates a status chip at ordinary text size in a
360 dp pane, which the writing guidelines call a defect rather than an ellipsis
case. What works is a two layout split: the status, the risk and the age sit
beside the text above a named width and on a line of their own below it. Three
separate slots arrived at the same answer for three different rows before it
became a declared variant of the control. From the E2, E5 and polish 2
closeouts.

**Believing the first scroll.** The intake screen looked like it had the same
bottom inset defect as the queue and two swipes were not enough to prove it
either way. Six swipes to the true end of each list separated them: intake
clears the navigation capsule and the queue does not. One of the two is a defect
in the report and the other is not. From the H3 closeout.

## 5. If you run the next one

1. Write the direction and the component specification before any code, and
   write down the specific things you reject. Six agents converge on a
   specification that says what it is not.
2. Cut one integration branch. No agent commits to it; the integrator merges,
   regenerates and pushes.
3. Turn every rule into a test in the first wave, with a shrink-only backlog
   where it cannot start at zero. A rule that is not a test is a wish.
4. Give each slot a brief that names its files, its gates, the exit criteria,
   and the sibling slots whose files it must not touch.
5. Build the review surface early. The gallery at checkpoint 1 produced
   `11-fit-and-scale.md`; an emulator review of one screen produced
   `13-screen-composition.md`. No test could have found either set.
6. Keep binaries out of slot branches. Regenerate once per wave, predict the
   moved set, read the diff, and treat a surprise as a finding.
7. Run each gate on its own, in a quiet worktree, and read its own exit code.
8. Make the closeout part of the work, not a report about it. Every lesson in
   this document exists because a slot wrote it down before its worktree was
   removed.
