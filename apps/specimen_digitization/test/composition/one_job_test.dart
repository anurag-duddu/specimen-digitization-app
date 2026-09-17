// One job per region (13 sections 2.4 and 5, `one_job`).
//
// The fourth row of 13 section 0 is a list of things a screen says twice: a
// title that repeats what the top bar carries, a "Back to queue" row that
// repeats what the bar's leading slot is for, a heading over a photograph that
// names what is self evident. 13 section 2.4 is the rule and this is its two
// measurable halves.
//
// The first half: no two `Text` nodes inside pinned regions carry the same
// string. Pinned regions are where repetition costs the most, because they are
// on screen at every scroll offset and they are the budget of section 2.3.
//
// The second half: no screen has a row whose only content is a back action.
// 13 section 2.4 gives the way out to the top bar, and 13 section 4.1 puts
// back in the bar on the record screen, so a row of the page that holds a back
// action and nothing else is a second region doing the bar's one job. "Only
// content" is measured rather than assumed: a control is a finding when the
// slot it occupies in its nearest row or column holds that control and no
// other, which is what an `Align` around a single button is.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import 'composition_harness.dart';

// ---------------------------------------------------------------------------
// The backlogs. Shrink only.
// ---------------------------------------------------------------------------

/// The cells whose pinned regions say something twice today.
///
/// Measured on 2026-09-17 against `front-end-refactor` at f3b6363, at every
/// window, both modes and 1.0, 1.3 and 2.0. Empty, and it is a real zero
/// rather than an unwritten gate: the shell's chrome carries the mark, the
/// switcher, the reload and the account on one row, the band carries one
/// sentence, and the pill carries two destination names, and none of them
/// repeats another. The clause is here because the screens are about to gain
/// a pinned collapsing header and a pinned decision bar that each carry words
/// the bar above them already has.
final Set<String> pinnedRepetitionBacklog = <String>{};

/// The cells that draw a back action outside the top bar today.
///
/// Empty, and it is a real zero. The three it held were one control:
/// `workbench_screen.dart` drew an `Align` holding a "Back to queue" button
/// and nothing else whenever the record was narrow. It was the third row of 13
/// section 0's table, and 13 section 4.1 deletes it by putting back in the top
/// bar, which the record now publishes into the frame itself.
final Set<String> backRowBacklog = <String>{};

// ---------------------------------------------------------------------------
// The measurements.
// ---------------------------------------------------------------------------

/// Every string a pinned region draws right now, in the order it is painted.
///
/// Only text that is actually laid out: a label a control builds for a tooltip
/// it is not showing has no box, and a string nobody can read is not a
/// repetition.
List<String> pinnedStringsNow() {
  final List<Element> elements = compositionElements();
  final bool markers = pinnedMarkersPresent(elements);
  final List<String> found = <String>[];
  for (final Element element in elements) {
    final String? text = textOf(element.widget);
    if (text == null || text.trim().isEmpty) continue;
    if (rectOf(element) == null) continue;
    if (!isInPinnedRegion(element, markersPresent: markers)) continue;
    found.add(text);
  }
  return found;
}

/// The strings a pinned region draws more than once right now.
List<String> pinnedRepetitionsNow() {
  final Map<String, int> counts = <String, int>{};
  for (final String text in pinnedStringsNow()) {
    counts[text] = (counts[text] ?? 0) + 1;
  }
  return <String>[
    for (final MapEntry<String, int> entry in counts.entries)
      if (entry.value > 1) '"${entry.key}" ${entry.value} times',
  ];
}

/// True where [widget] is a control that takes the reviewer back.
///
/// The glyph decides and the word confirms it, because a back action is a
/// glyph with a word beside it on one control and a glyph alone on another.
bool isBackAction(Widget widget) {
  if (widget is UiButton) {
    return widget.leading == UiIcons.back || widget.label.startsWith('Back');
  }
  if (widget is UiIconButton) {
    return widget.icon == UiIcons.back ||
        widget.semanticsLabel.startsWith('Back');
  }
  return false;
}

/// True where [widget] is a control a reviewer can press.
bool isPressableControl(Widget widget) =>
    widget is UiButton || widget is UiIconButton;

/// True where [slot] holds a back action and no other control.
bool holdsOnlyABackAction(Element slot) {
  int controls = 0;
  bool back = false;
  void visit(Element element) {
    if (isPressableControl(element.widget)) {
      controls++;
      if (isBackAction(element.widget)) back = true;
    }
    element.visitChildren(visit);
  }

  visit(slot);
  return back && controls == 1;
}

/// The rows whose only content is a back action right now.
///
/// A back action inside a pinned region is the top bar's own, which is where
/// 13 section 2.4 puts it.
///
/// "A row" is one band of a column: a column lays its children out as
/// horizontal bands, so a child of one that holds a back action and no other
/// control is exactly the "Back to queue" row of 13 section 0.
List<String> backRowsNow() {
  final List<Element> elements = compositionElements();
  final bool markers = pinnedMarkersPresent(elements);
  final List<String> found = <String>[];
  for (final Element element in elements) {
    if (!isBackAction(element.widget)) continue;
    if (rectOf(element) == null) continue;
    if (isInPinnedRegion(element, markersPresent: markers)) continue;
    // The band this control occupies. A row of the page is one child of a
    // column, because a column lays its children out as horizontal bands, so
    // the finding is a control whose nearest enclosing `Flex` runs vertically
    // and whose own slot in it holds nothing else. A back action beside other
    // actions in a `Row` is a row with more than one job rather than a row
    // with only this one, and belongs to whatever else the row is for.
    Element slot = element;
    Element? column;
    element.visitAncestorElements((Element parent) {
      final Widget widget = parent.widget;
      if (widget is Flex) {
        if (widget.direction == Axis.vertical) column = parent;
        return false;
      }
      slot = parent;
      return true;
    });
    if (column == null) continue;
    if (!holdsOnlyABackAction(slot)) continue;
    final Widget widget = element.widget;
    final String label = widget is UiButton
        ? widget.label
        : (widget as UiIconButton).semanticsLabel;
    found.add(
      '"$label" is the whole of one band of a ${column!.widget.runtimeType}',
    );
  }
  return found;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('the backlogs name cells the matrix runs', () {
    expectBacklogCellsExist(pinnedRepetitionBacklog, 'pinnedRepetitionBacklog');
    expectBacklogCellsExist(backRowBacklog, 'backRowBacklog');
  });

  group('the instruments read a screen the way a reviewer would', () {
    const Size window = Size(390, 844);

    testWidgets('a pinned region that says a word twice is a finding', (
      WidgetTester tester,
    ) async {
      await pumpGoldenRoute(
        tester,
        window: window,
        brightness: Brightness.light,
        child: const UiScaffold(
          sky: SkyPreset.none,
          topBar: UiTopBar(title: 'Queue', center: Text('Queue')),
          body: Center(child: Text('Queue')),
        ),
      );
      // Twice in the bar is the finding. The third, in the body, is not in a
      // pinned region and does not count.
      expect(pinnedRepetitionsNow(), <String>['"Queue" 2 times']);
    });

    testWidgets('a pinned region that says each word once is not', (
      WidgetTester tester,
    ) async {
      await pumpGoldenRoute(
        tester,
        window: window,
        brightness: Brightness.light,
        child: const UiScaffold(
          sky: SkyPreset.none,
          topBar: UiTopBar(title: 'Queue'),
          body: Center(child: Text('Queue')),
        ),
      );
      expect(pinnedRepetitionsNow(), isEmpty);
    });

    testWidgets('a row holding only a back action is a finding', (
      WidgetTester tester,
    ) async {
      await pumpGoldenRoute(
        tester,
        window: window,
        brightness: Brightness.light,
        child: UiScaffold(
          sky: SkyPreset.none,
          topBar: const UiTopBar(title: 'Record'),
          body: Column(
            children: <Widget>[
              Align(
                alignment: AlignmentDirectional.centerStart,
                child: UiButton(
                  label: 'Back to queue',
                  leading: UiIcons.back,
                  onPressed: () {},
                ),
              ),
              const Expanded(child: Center(child: Text('The record'))),
            ],
          ),
        ),
      );
      expect(backRowsNow(), hasLength(1));
      expect(backRowsNow().single, contains('Back to queue'));
    });

    testWidgets('a back action beside other content is not', (
      WidgetTester tester,
    ) async {
      await pumpGoldenRoute(
        tester,
        window: window,
        brightness: Brightness.light,
        child: UiScaffold(
          sky: SkyPreset.none,
          topBar: const UiTopBar(title: 'Record'),
          body: Column(
            children: <Widget>[
              Row(
                children: <Widget>[
                  UiButton(
                    label: 'Back to queue',
                    leading: UiIcons.back,
                    onPressed: () {},
                  ),
                  UiButton(label: 'Approve record', onPressed: () {}),
                ],
              ),
              const Expanded(child: Center(child: Text('The record'))),
            ],
          ),
        ),
      );
      expect(backRowsNow(), isEmpty);
    });

    testWidgets('the top bar own back action is not', (
      WidgetTester tester,
    ) async {
      await pumpGoldenRoute(
        tester,
        window: window,
        brightness: Brightness.light,
        child: UiScaffold(
          sky: SkyPreset.none,
          topBar: UiTopBar(
            title: 'Record',
            leading: UiIconButton(
              icon: UiIcons.back,
              semanticsLabel: 'Back to queue',
              onPressed: () {},
            ),
          ),
          body: const Center(child: Text('The record')),
        ),
      );
      expect(backRowsNow(), isEmpty);
    });
  });

  group('each pinned region says its job once', () {
    for (final CompositionScreen screen in compositionScreens) {
      for (final MapEntry<String, Size> window in compositionWindows.entries) {
        testWidgets('${screen.name} at ${window.key}', (
          WidgetTester tester,
        ) async {
          final List<String> repeated = <String>[];
          final List<String> backRows = <String>[];
          await overCell(
            tester,
            screen: screen,
            window: window.value,
            measure: (String where) async {
              for (final String text in pinnedRepetitionsNow()) {
                repeated.add('  $where: $text');
              }
              for (final String row in backRowsNow()) {
                backRows.add('  $where: $row');
              }
            },
          );
          final String cell = cellOf(screen.name, window.key);
          expectCell(
            cell,
            failures: repeated,
            backlog: pinnedRepetitionBacklog,
            backlogName: 'pinnedRepetitionBacklog',
            clause:
                '${screen.name} at ${window.key} says the same words twice in '
                'its pinned regions. 13 section 2.4: anything that repeats '
                'another region is removed, not styled.',
          );
          expectCell(
            cell,
            failures: backRows,
            backlog: backRowBacklog,
            backlogName: 'backRowBacklog',
            clause:
                '${screen.name} at ${window.key} draws a row whose only '
                'content is a back action. 13 section 2.4 gives the way out '
                'to the top bar, and 13 section 4.1 puts back in the bar on '
                'the record.',
          );
        });
      }
    }
  });
}
