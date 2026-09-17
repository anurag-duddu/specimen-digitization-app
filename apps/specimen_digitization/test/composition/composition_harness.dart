// The instruments the composition gates measure with (13 section 5).
//
// 13 states the composition contract as five clauses and says each one is a
// test in this directory. The clauses measure different things, but they all
// need the same four facts: a routed screen pumped at a window, a walk of the
// element tree that screen built, a way to tell a pinned region from a
// scrolling one, and a backlog that says which cells are known to fail today
// so a gate can be red about the rest from its first day.
//
// Everything here is measurement. A gate file holds the rule, the budget and
// the backlog; this file holds nothing a reader has to agree with.
//
// The screens are pumped through `test/golden/golden_harness.dart`, the same
// harness the size class goldens use, so a screen that composes differently in
// a gate than it does in a golden is not possible.

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/app/routes.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/intake/capture_card.dart';
import 'package:specimen_digitization/src/screens/intake/manifest_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/decision_bar.dart';
import 'package:specimen_digitization/src/screens/workbench/source_pane.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/widgets/source_import_sheet.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';

// ---------------------------------------------------------------------------
// The matrix. 13 section 5: every routed screen at the four windows, in both
// modes, at 1.0, 1.3 and 2.0.
// ---------------------------------------------------------------------------

/// The four windows, from the size class goldens.
Map<String, Size> get compositionWindows => goldenWindows;

/// Both modes, from the size class goldens.
Map<String, Brightness> get compositionThemes => goldenThemes;

/// The three text scales the control contract promises (11 section 2.1).
const List<double> compositionScales = <double>[1.0, 1.3, 2.0];

/// The window class a window name belongs to, for a per class budget.
///
/// The names in [compositionWindows] carry their class as their first word,
/// which is what makes this a split rather than a table to keep in step.
String windowClassOf(String window) => window.split('-').first;

/// True where [window] is the phone.
bool isCompact(String window) => windowClassOf(window) == 'compact';

/// The cell a backlog line names: one screen at one window.
///
/// Mode and text scale are deliberately not in the key. A composition defect
/// is a property of an arrangement, and an arrangement is chosen by the window
/// class; a screen that broke the contract in dark and not in light would be a
/// finding about the theme rather than about the composition. Where a clause
/// is measured as a number, the backlog carries the worst number over the
/// modes and the scales, so a cell is one line whatever it took to find it.
String cellOf(String screen, String window) => '$screen@$window';

// ---------------------------------------------------------------------------
// The screens.
// ---------------------------------------------------------------------------

/// Pumps one screen at one window, one mode and one text scale.
typedef CompositionPump =
    Future<void> Function(
      WidgetTester tester, {
      required Size window,
      required Brightness brightness,
      required double textScale,
    });

/// One routed screen, and what 13 section 4 expects above its fold.
///
/// [primary] and [next] are the two regions of 13 section 2.5: the region the
/// screen exists to show, and the region beneath it whose first row proves
/// there is more. They are builders rather than finders because a `Finder` is
/// evaluated against whatever is mounted, and these are declared once at the
/// top of a file that runs many pumps.
class CompositionScreen {
  /// Declares one screen of the matrix.
  const CompositionScreen({
    required this.name,
    required this.pump,
    this.primary,
    this.primaryMinFraction,
    this.next,
    this.nextIsSecondPrimary = false,
  });

  /// What the backlog calls it.
  final String name;

  /// How it is put on screen.
  final CompositionPump pump;

  /// The primary region of 13 section 2.5, or null where 13 names none.
  final Finder Function()? primary;

  /// The share of the viewport the primary region has to show at compact,
  /// where 13 section 4 gives one. The record's photograph is 0.40.
  final double? primaryMinFraction;

  /// The region beneath the primary one, whose first row has to be visible.
  final Finder Function()? next;

  /// True where the next region is the primary region's own second instance,
  /// which is what "the first two rows on the queue" means.
  final bool nextIsSecondPrimary;
}

/// Pumps a screen of the collection through the shipped router.
CompositionPump _routed(
  String location, {
  bool signedIn = true,
  GoldenRepository Function()? repository,
}) =>
    (
      WidgetTester tester, {
      required Size window,
      required Brightness brightness,
      required double textScale,
    }) => pumpGoldenApp(
      tester,
      window: window,
      brightness: brightness,
      textScale: textScale,
      location: location,
      signedIn: signedIn,
      repository: repository?.call(),
    );

/// Pumps the source screen and opens the import sheet on it.
///
/// The sheet is raised through `confirmSourceImport`, which is the call the
/// source screen's own add control makes, from a context inside the mounted
/// screen. Driving the control instead was tried and is not stable enough to
/// be a gate: at 200 percent text on a phone the selection bar overflows its
/// column by seventeen pixels and the tap on the add control misses, so the
/// cell that should report a nested scroll reports a missed hit test. The
/// surface, the navigator, the theme and the window are the application's
/// either way; only the finger is skipped.
Future<void> _pumpImportSheet(
  WidgetTester tester, {
  required Size window,
  required Brightness brightness,
  required double textScale,
}) async {
  await _routed(goldenSourceLocation, repository: GoldenSourceRepository.new)(
    tester,
    window: window,
    brightness: brightness,
    textScale: textScale,
  );
  final BuildContext inside = tester.element(find.byType(UiListRow).first);
  // Not awaited: the future completes when the sheet is dismissed, and the
  // gate measures the sheet while it is open.
  unawaited(confirmSourceImport(inside, count: 1, alreadyInQueue: 0));
  await tester.pumpAndSettle();
}

/// Pumps the region editor the way the application opens it (13 section 4.3).
///
/// A dialog at expanded and above, a full screen route below, which is the
/// branch `showRegionEditor` takes and the one the size class goldens capture.
Future<void> _pumpRegionEditor(
  WidgetTester tester, {
  required Size window,
  required Brightness brightness,
  required double textScale,
}) async {
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  if (window.width >= expandedWindowFloor) {
    await pumpGoldenDialog(
      tester,
      window: window,
      brightness: brightness,
      semanticsLabel: regionEditorTitle,
      dialog: RegionEditor(
        regions: goldenRegions,
        asset: goldenEditableAsset(),
      ),
    );
    return;
  }
  await pumpGoldenRoute(
    tester,
    window: window,
    brightness: brightness,
    child: UiScaffold(
      sky: SkyPreset.none,
      topBar: const UiTopBar(title: regionEditorTitle),
      body: RegionEditorBody(
        regions: goldenRegions,
        asset: goldenEditableAsset(),
      ),
    ),
  );
}

/// Every screen the composition contract binds, and what it expects.
///
/// The nine locations a reviewer can reach, plus the two surfaces a screen
/// opens over itself. `verify` is not here: it is behind a redirect the
/// fixture session does not reach, which slot H3 recorded when the fit matrix
/// covered eleven screens rather than every location.
final List<CompositionScreen> compositionScreens = <CompositionScreen>[
  CompositionScreen(
    name: 'signin',
    pump: _routed(AppRoutes.signIn, signedIn: false),
  ),
  CompositionScreen(name: 'setup', pump: _routed(AppRoutes.setup)),
  CompositionScreen(name: 'help', pump: _routed(AppRoutes.help)),
  CompositionScreen(
    name: 'queue',
    // Four records rather than the one the default fixture answers: 13
    // section 2.5 asks for the first two rows of the queue to be visible, and
    // a list with one row cannot answer that question either way.
    pump: _routed(
      goldenQueueLocation,
      repository: () => GoldenQueueRepository(goldenQueue(4)),
    ),
    // 13 section 2.5: the list is the queue's primary region and the first
    // two rows are what has to be visible.
    primary: () => find.byType(UiListRow),
    next: () => find.byType(UiListRow),
    nextIsSecondPrimary: true,
  ),
  CompositionScreen(
    name: 'record',
    pump: _routed(goldenSpecimenLocation),
    // 13 section 4.1: the photograph at 0.40 of the viewport, with the status
    // strip and the first reading beneath it.
    primary: () => find.byType(SourceMatte),
    primaryMinFraction: 0.40,
    next: () => find.byType(WorkbenchStatusStrip),
  ),
  CompositionScreen(
    name: 'intake',
    pump: _routed(goldenIntakeLocation),
    // 13 section 4.4: the capture card is the form, the manifest is the
    // region beneath it.
    primary: () => find.byType(IntakeCaptureCard),
    next: () => find.byType(IntakeManifest),
  ),
  CompositionScreen(
    name: 'sources',
    pump: _routed(
      goldenSourcesLocation,
      repository: GoldenSourceRepository.new,
    ),
    // 13 section 4.5: the rows. The fixture registers one source, so there is
    // no second row to ask for and no region under the list.
    primary: () => find.byType(UiListRow),
  ),
  CompositionScreen(
    name: 'source',
    pump: _routed(goldenSourceLocation, repository: GoldenSourceRepository.new),
    primary: () => find.byType(UiListRow),
    next: () => find.byType(UiListRow),
    nextIsSecondPrimary: true,
  ),
  CompositionScreen(name: 'import-sheet', pump: _pumpImportSheet),
  CompositionScreen(name: 'region-editor', pump: _pumpRegionEditor),
];

// ---------------------------------------------------------------------------
// The walk.
// ---------------------------------------------------------------------------

/// Every element in the tree right now, in paint order.
///
/// From the binding's root rather than from a finder, because a gate has to
/// see the shell, the routed screen and anything open over both.
List<Element> compositionElements() {
  final List<Element> found = <Element>[];
  void visit(Element element) {
    found.add(element);
    element.visitChildren(visit);
  }

  final Element? root = WidgetsBinding.instance.rootElement;
  if (root != null) visit(root);
  return found;
}

/// The widgets the shell and the screens pin today.
///
/// The fallback for the `PinnedChrome` marker slot A1 lands: 13 section 2.3
/// names the top bar, the environment band, a pinned header at its collapsed
/// height, the decision bar and the navigation pill, and these are the widgets
/// that draw those five today. A rail and a sidebar are deliberately absent:
/// they are laid out beside the body rather than above it, so they spend width
/// and the budget is a share of the height.
bool isPinnedChromeWidget(Widget widget) =>
    widget is UiTopBar ||
    widget is UiPillNav ||
    widget is EnvironmentBanner ||
    widget is WorkbenchDecisionBar;

/// The name of the marker slot A1 publishes for a pinned region.
///
/// Matched by name, and read through `dynamic`, rather than through the class
/// on purpose. This slot is cut from the same head as `fe/compose-package` and
/// cannot import a class that branch has not merged yet, and a gate that waits
/// for a sibling is a gate that measures nothing in the meantime. The moment a
/// screen wraps a region in the marker, every gate here reads the marker
/// instead of the widget list above, with no change to this file.
///
/// `fe/compose-package` at b04e6ec publishes
/// `PinnedChrome({region, child, extent})` with
/// `static double extentOf(Element)`, and `PrimaryRegion({child, minExtent})`
/// with `static double minExtentOf(Element)`. [markerExtent] and
/// [markerMinExtent] below are those two rules written out. The integrator
/// replaces the three of them with the import once A1 is merged, and nothing
/// else here moves.
const String pinnedChromeMarker = 'PinnedChrome';

/// The name of the marker slot A1 publishes for a screen's primary region.
const String primaryRegionMarker = 'PrimaryRegion';

/// True where [element] is an instance of the marker named [marker].
bool isMarker(Element element, String marker) =>
    element.widget.runtimeType.toString() == marker;

/// The value of the named `double?` field [name] on [widget], or null.
///
/// Read dynamically for the reason above. A marker whose field has been
/// renamed reads as undeclared rather than as a crash, and the measurement
/// falls back to the box under it, which is the same answer for every marker
/// that has one.
double? _declaredDouble(Widget widget, String name) {
  final dynamic target = widget;
  try {
    final dynamic value = switch (name) {
      'extent' => target.extent,
      'minExtent' => target.minExtent,
      _ => null,
    };
    return value is double ? value : null;
  } on NoSuchMethodError {
    return null;
  }
}

/// The height the `PinnedChrome` marker at [element] contributes.
///
/// `PinnedChrome.extentOf`: the extent the marker declares, or the height of
/// the box under it. A sliver has no box, which is why a marker may declare
/// one; a marker with neither is a marker that cannot be measured, and the
/// gate says so rather than counting it as nothing.
double? markerExtent(Element element) =>
    _declaredDouble(element.widget, 'extent') ?? rectOf(element)?.height;

/// The height the `PrimaryRegion` marker at [element] has to be shown in.
///
/// `PrimaryRegion.minExtentOf`: the minimum the marker declares, or the height
/// of the box under it.
double? markerMinExtent(Element element) =>
    _declaredDouble(element.widget, 'minExtent') ?? rectOf(element)?.height;

/// Which pinned region the marker at [element] says it is, for a failure to
/// name it.
String markerRegionName(Element element) {
  final dynamic target = element.widget;
  try {
    final dynamic region = target.region;
    final dynamic name = region.name;
    return name is String ? name : pinnedChromeMarker;
  } on NoSuchMethodError {
    return pinnedChromeMarker;
  }
}

/// The rectangle [element] occupies in the window, or null where it has none.
Rect? rectOf(Element element) {
  final RenderObject? object = element.renderObject;
  if (object is! RenderBox || !object.hasSize || !object.attached) return null;
  return object.localToGlobal(Offset.zero) & object.size;
}

/// The string a `Text` draws, or null where the widget is not one.
String? textOf(Widget widget) {
  if (widget is! Text) return null;
  return widget.data ?? widget.textSpan?.toPlainText();
}

/// True where an ancestor of [element] satisfies [test], stopping at the first.
bool hasAncestor(Element element, bool Function(Widget widget) test) {
  bool found = false;
  element.visitAncestorElements((Element parent) {
    if (test(parent.widget)) {
      found = true;
      return false;
    }
    return true;
  });
  return found;
}

/// True where [element] sits inside a pinned region.
///
/// Reads the marker where one is in the tree and the widget list where none
/// is, so a screen that has moved to slot A1's marker and a screen that has
/// not are both measured.
bool isInPinnedRegion(Element element, {required bool markersPresent}) {
  bool found = false;
  element.visitAncestorElements((Element parent) {
    final bool pinned = markersPresent
        ? isMarker(parent, pinnedChromeMarker)
        : isPinnedChromeWidget(parent.widget);
    if (pinned) {
      found = true;
      return false;
    }
    return true;
  });
  return found;
}

/// True where any `PinnedChrome` marker is mounted.
bool pinnedMarkersPresent(List<Element> elements) =>
    elements.any((Element element) => isMarker(element, pinnedChromeMarker));

// ---------------------------------------------------------------------------
// Scrolling.
// ---------------------------------------------------------------------------

/// True where [scrollable] scrolls up and down.
bool isVerticalScrollable(Scrollable scrollable) =>
    axisDirectionToAxis(scrollable.axisDirection) == Axis.vertical;

/// Builds every lazy row of every vertical scroll view, sampling as it goes.
///
/// A `ListView` builds only what its viewport holds, so an element walk taken
/// at rest cannot see a list nested below the fold: intake's manifest is the
/// third child of the page's list on a phone and is never built until the page
/// is scrolled to it. Every gate here therefore samples at rest and then once
/// per viewport of every vertical scroll view, and takes the union.
///
/// [steps] bounds the sweep so a screen whose content is many viewports tall
/// does not turn one cell into a hundred pumps. Twelve viewports is past the
/// end of every screen in this application at 200 percent text.
Future<void> sweepScrolls(
  WidgetTester tester,
  Future<void> Function() sample, {
  int steps = 12,
}) async {
  await sample();
  int taken = 0;
  final List<ScrollableState> scrolls = tester
      .stateList<ScrollableState>(find.byType(Scrollable))
      .where(
        (ScrollableState state) =>
            state.position.axis == Axis.vertical &&
            state.position.hasContentDimensions,
      )
      .toList();
  for (final ScrollableState state in scrolls) {
    final double end = state.position.maxScrollExtent;
    if (end <= 0) continue;
    final double step = state.position.viewportDimension * 0.8;
    double at = 0;
    while (at < end && taken < steps) {
      at += step;
      state.position.jumpTo(at > end ? end : at);
      await tester.pumpAndSettle();
      taken++;
      await sample();
    }
    if (state.position.hasPixels && state.position.pixels != 0) {
      state.position.jumpTo(0);
      await tester.pumpAndSettle();
    }
  }
}

// ---------------------------------------------------------------------------
// The backlogs.
//
// One line per cell, and a cell is one screen at one window. Both shapes below
// are checked in both directions: a cell that is not listed has to satisfy the
// clause, and a cell that is listed has to still breach it. A backlog that
// only allows failures drifts, because nobody notices when a line stops being
// true; this is the mechanism `knownWorkbenchOverflows` uses in the size class
// goldens and `no_literal_geometry` uses on its per file counts, and it is why
// a slot that fixes a screen deletes the line in the same change.
// ---------------------------------------------------------------------------

/// Asserts one cell of a clause that a screen either satisfies or does not.
///
/// [failures] is every breach seen over both modes and the three text scales,
/// each one saying where it was seen, so a cell that fails at 200 percent text
/// only still reads as one line of backlog and still names the scale.
void expectCell(
  String cell, {
  required List<String> failures,
  required Set<String> backlog,
  required String backlogName,
  required String clause,
}) {
  if (backlog.contains(cell)) {
    expect(
      failures,
      isNotEmpty,
      reason:
          '$cell is in $backlogName and now satisfies the clause at every '
          'mode and text scale. If that is the fix, delete the line in the '
          'same change.',
    );
    return;
  }
  expect(failures, isEmpty, reason: '$clause\n${failures.join('\n')}');
}

/// Asserts one cell of a clause measured as a number.
///
/// [worst] is the worst number over both modes and the three text scales,
/// which is what a line records: a cell is one line whatever it took to find
/// the worst of it. A listed cell has to be over [budget] still, and has to be
/// no worse than the line says, and the line has to state what it measures
/// rather than round it, so a fix that halves a number moves the line.
void expectCellWithin(
  String cell, {
  required num worst,
  required num budget,
  required Map<String, num> backlog,
  required String backlogName,
  required String failure,
  num tolerance = 0.001,
}) {
  final num? allowed = backlog[cell];
  if (allowed == null) {
    expect(worst, lessThanOrEqualTo(budget), reason: failure);
    return;
  }
  expect(
    worst,
    greaterThan(budget),
    reason:
        '$cell measures $worst, which is inside the budget of $budget, and is '
        'still in $backlogName. Delete the line.',
  );
  expect(
    worst,
    lessThanOrEqualTo(allowed),
    reason:
        '$cell measured $worst against the $allowed $backlogName records. '
        'The backlog may only shrink. $failure',
  );
  expect(
    worst,
    closeTo(allowed, tolerance),
    reason:
        '$cell measures $worst and $backlogName allows $allowed. Move the '
        'line to what it measures, so the backlog states the debt rather than '
        'rounding it.',
  );
}

/// Asserts that every cell a backlog names is a cell the matrix actually runs.
///
/// A line for a screen that has been renamed, or for a window the matrix does
/// not hold, is a line nobody will ever delete.
void expectBacklogCellsExist(Iterable<String> cells, String backlogName) {
  final Set<String> known = <String>{
    for (final CompositionScreen screen in compositionScreens)
      for (final String window in compositionWindows.keys)
        cellOf(screen.name, window),
  };
  final Iterable<String> unknown = cells.where(
    (String cell) => !known.contains(cell),
  );
  expect(
    unknown,
    isEmpty,
    reason:
        '$backlogName names cells the matrix does not run: $unknown. A line '
        'nobody can reach is a line nobody deletes.',
  );
}

/// Runs [measure] for one screen at one window, in both modes at every scale.
///
/// The tree is torn down between pumps. `pumpWidget` reuses an element whose
/// widget is of the same type, so the application's navigator survives a
/// second pump and anything a screen pushed on it, such as the import sheet,
/// is still there: six pumps measured six stacked sheets rather than one.
Future<void> overCell(
  WidgetTester tester, {
  required CompositionScreen screen,
  required Size window,
  required Future<void> Function(String where) measure,
}) async {
  for (final MapEntry<String, Brightness> theme in compositionThemes.entries) {
    for (final double scale in compositionScales) {
      await tester.pumpWidget(const SizedBox.shrink());
      await screen.pump(
        tester,
        window: window,
        brightness: theme.value,
        textScale: scale,
      );
      await measure('in ${theme.key} at $scale');
    }
  }
}
