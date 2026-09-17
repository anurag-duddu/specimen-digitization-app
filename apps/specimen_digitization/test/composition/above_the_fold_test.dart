// Above the fold (13 sections 2.5 and 5, `above_the_fold`).
//
// The fourth row of 13 section 0 is "no priority", and the sentence under the
// capture that started it is "the readings, which are the work, were below the
// fold". This measures the fold.
//
// At compact, the screen's primary region is laid out inside the first
// viewport, and the region beneath it has its first row on screen. Which
// region is primary is 13 section 4's per screen table, held here as one Dart
// map beside the screens themselves in `composition_harness.dart`, so the
// expectation and the screen it belongs to are read together.
//
// Compact only, deliberately, because 13 section 2.5 is about a phone: a
// window with room to spare has no fold to be below. Both modes and all three
// text scales, because the fold is exactly what a larger type crosses.
//
// The primary region is the `PrimaryRegion` marker slot A1 lands, where a
// screen carries one, and the widget 13 section 2.5 names where it does not:
// the photograph's matte on the record, the first row on a list.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'composition_harness.dart';

// ---------------------------------------------------------------------------
// The backlog.
// ---------------------------------------------------------------------------

/// The compact screens whose work is below the fold today. Shrink only.
///
/// Measured on 2026-09-17 against `front-end-refactor` at f3b6363, in both
/// modes at 1.0, 1.3 and 2.0.
///
/// Intake lays its capture card out 1018 dp tall, so the manifest under it
/// starts a viewport and a half down. The queue holds the fold at 1.0 and 1.3
/// and loses it at 2.0, where the first row starts at 803 of 844: the rows are
/// below a header, a search field and a filter row that all scroll with them.
///
/// The record left this list on `fe/compose-record`: the photograph is the
/// content of a `UiCollapsingHeader` pinned between 55 and 40 percent of the
/// viewport, and the status strip is the sliver under it.
///
/// Slot A3 owns the queue and intake.
final Set<String> aboveTheFoldBacklog = <String>{
  'intake@compact-390x844',
  'queue@compact-390x844',
};

// ---------------------------------------------------------------------------
// The measurement.
// ---------------------------------------------------------------------------

/// The window this clause is measured at.
const String compactWindow = 'compact-390x844';

/// The primary region of [screen]: where it is, and the height it has to be
/// shown in.
///
/// The `PrimaryRegion` marker wins where one is in the tree, so a screen that
/// slot A1's marker has reached is measured by what it declares rather than by
/// what this file guessed for it, and the minimum is
/// `PrimaryRegion.minExtentOf`. Where no marker is in the tree the region is
/// the widget 13 section 2.5 names, and the minimum is the share of the
/// viewport 13 section 4 gives it, or the region's own height where 13 gives
/// no share.
({Rect box, double needed})? primaryOf(
  CompositionScreen screen,
  double viewport,
) {
  final Iterable<Element> markers = compositionElements().where(
    (Element element) => element.widget is PrimaryRegion,
  );
  if (markers.isNotEmpty) {
    final Rect? box = rectOf(markers.first);
    if (box == null) return null;
    return (box: box, needed: primaryMinExtent(markers.first) ?? box.height);
  }
  final Finder? finder = screen.primary?.call();
  if (finder == null) return null;
  final List<Element> found = finder.evaluate().toList();
  if (found.isEmpty) return null;
  final Rect? box = rectOf(found.first);
  if (box == null) return null;
  final double? fraction = screen.primaryMinFraction;
  return (
    box: box,
    needed: fraction == null ? box.height : viewport * fraction,
  );
}

/// The rectangle of the first row of the region beneath the primary one.
Rect? nextRectOf(CompositionScreen screen) {
  final Finder? finder = screen.nextIsSecondPrimary
      ? screen.primary?.call()
      : screen.next?.call();
  if (finder == null) return null;
  final List<Element> found = finder.evaluate().toList();
  final int index = screen.nextIsSecondPrimary ? 1 : 0;
  return found.length > index ? rectOf(found[index]) : null;
}

/// Why [screen] is below the fold at [viewport], or null where it is not.
String? foldFailure(CompositionScreen screen, double viewport) {
  final ({Rect box, double needed})? primary = primaryOf(screen, viewport);
  if (primary == null) {
    return 'the primary region is not laid out at all';
  }
  final Rect box = primary.box;
  if (box.top < 0 || box.top >= viewport) {
    return 'the primary region starts at ${box.top.round()} and the first '
        'viewport is 0 to ${viewport.round()}';
  }
  final double visible =
      (box.bottom < viewport ? box.bottom : viewport) - box.top;
  if (visible < primary.needed) {
    return 'the primary region shows ${visible.round()} of the '
        '${primary.needed.round()} it has to be shown in';
  }
  if (screen.next == null && !screen.nextIsSecondPrimary) return null;
  final Rect? next = nextRectOf(screen);
  if (next == null) {
    return 'the region beneath the primary one is not laid out at all';
  }
  if (next.top < 0 || next.top >= viewport) {
    return 'the next region starts at ${next.top.round()} and the first '
        'viewport ends at ${viewport.round()}';
  }
  return null;
}

/// The screens 13 section 2.5 names a primary region for.
Iterable<CompositionScreen> get screensWithAPrimaryRegion => compositionScreens
    .where((CompositionScreen screen) => screen.primary != null);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('the backlog names cells the matrix runs', () {
    expectBacklogCellsExist(aboveTheFoldBacklog, 'aboveTheFoldBacklog');
  });

  test('the table names a primary region for the screens 13 does', () {
    // 13 section 2.5 names four: the photograph on the record screen, the list
    // on the queue, the form on intake, the sources list on sources. The
    // browse surface over one source is the same list by another route in, so
    // it is held to the same rule.
    expect(
      screensWithAPrimaryRegion
          .map((CompositionScreen screen) => screen.name)
          .toList(),
      <String>['queue', 'record', 'intake', 'sources', 'source'],
      reason:
          'the per screen expectations are the table 13 section 4 states. A '
          'screen added to the matrix without one is a screen this clause '
          'does not reach.',
    );
  });

  group('the work is above the fold at compact', () {
    for (final CompositionScreen screen in screensWithAPrimaryRegion) {
      testWidgets(screen.name, (WidgetTester tester) async {
        final Size window = compositionWindows[compactWindow]!;
        final List<String> failures = <String>[];
        await overCell(
          tester,
          screen: screen,
          window: window,
          measure: (String where) async {
            final String? why = foldFailure(screen, window.height);
            if (why != null) failures.add('  $where: $why');
          },
        );
        expectCell(
          cellOf(screen.name, compactWindow),
          failures: failures,
          backlog: aboveTheFoldBacklog,
          backlogName: 'aboveTheFoldBacklog',
          clause:
              '${screen.name} at $compactWindow is below the fold. 13 section '
              '2.5 puts the primary region in the first viewport with a row '
              'of the next region under it.',
        );
      });
    }
  });
}
