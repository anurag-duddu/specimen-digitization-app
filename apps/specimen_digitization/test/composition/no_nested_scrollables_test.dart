// One scroll per screen per axis (13 sections 2.1 and 5, `no_nested_scrollables`).
//
// The first line of 13 section 0 is "a scroll inside a scroll", and the reason
// it was in the shipped record screen is that nothing failed when it was
// there. This is what fails.
//
// Two instruments, because the defect has two shapes. The first walks the
// element tree of every routed screen at every window, both modes and three
// text scales, and objects to a vertical `Scrollable` whose nearest vertical
// `Scrollable` ancestor is on the same route. The second reads `lib/` as text
// and objects to `shrinkWrap` and `NeverScrollableScrollPhysics`, which is
// where the first instrument cannot reach: a `ListView` builds only the rows
// its viewport holds, so a nested list below the fold is not in the tree until
// the page is scrolled to it. The walk sweeps every scroll view to its end for
// that reason, and the text scan is the belt to that brace.
//
// What is allowed, from 13 section 2.1: a horizontal strip inside the vertical
// scroll, which is the one exception the clause grants; a text editor's own
// scroll, which is `EditableText`'s and not a region's; and a sheet or a
// dialog's own scroll, because it is its own surface and the screen under the
// scrim does not count.

import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'composition_harness.dart';

// ---------------------------------------------------------------------------
// The backlog.
// ---------------------------------------------------------------------------

/// The cells that nest a vertical scroll today. Shrink only.
///
/// Measured on 2026-09-17 against `front-end-refactor` at f3b6363, by the walk
/// below, at every window, both modes and 1.0, 1.3 and 2.0.
///
/// Two screens, and each one is a sentence in 13 section 0. Intake on a phone
/// puts the manifest, which is a `ListView`, inside the page's own `ListView`
/// and turns its physics off to make the nesting lie still
/// (`intake.dart` `_manifest(nested: true)`, `manifest_panel.dart` lines 109
/// to 111); slot A3 owns 13 section 4.4, which is one scroll of sections. The
/// import sheet puts a `SingleChildScrollView` inside the one
/// `UiDialog.showAdaptive` already wraps its body in
/// (`source_import_sheet.dart` lines 119 and 194); the sheet's own scroll is
/// the allowed one and the body's is the second.
///
/// The region editor was the same defect as the import sheet by the same
/// cause, found by this gate rather than predicted: from the expanded floor up
/// `showRegionEditor` opens a `UiDialog`, whose body `UiDialog` already wraps
/// in a scroll, and the editor wrapped its coordinate form in a second. The
/// dialog passes `scrollBody: false` now, so it lends the editor the height
/// and the editor keeps the one scroll it has always had above its own
/// footer, which is what 13 section 2.1 grants a surface that owns a scroll.
///
/// The record screen is deliberately not here. 13 section 0 names it as the
/// screen the defect was found on, and it was; it is one `CustomScrollView`
/// of slivers now (13 sections 2.1 and 4.1) and the walk below finds no
/// nesting on it at any window or scale.
final Set<String> nestedScrollBacklog = <String>{
  'intake@compact-390x844',
  'import-sheet@compact-390x844',
  'import-sheet@medium-768x1024',
  'import-sheet@expanded-1180x820',
  'import-sheet@large-1440x900',
};

/// Per file counts of `shrinkWrap` and `NeverScrollableScrollPhysics` under
/// `lib/`. Shrink only, and a file at zero leaves the map.
///
/// Three, over two files. Both exist to nest a list, which is what 13 section
/// 2.1 says of the pair: `help_screen.dart` shrink wraps the shortcut list so
/// it can sit in a `Flexible` inside the sheet's column, and
/// `manifest_panel.dart` carries the shrink wrap and the physics that make the
/// intake nesting above lie still.
const Map<String, int> shrinkWrapBacklog = <String, int>{
  'lib/src/app/help_screen.dart': 1,
  'lib/src/screens/intake/manifest_panel.dart': 2,
};

// ---------------------------------------------------------------------------
// The walk.
// ---------------------------------------------------------------------------

/// One vertical scroll view found inside another.
class Nesting {
  /// Records the inner view and the ancestor it sits in.
  const Nesting(this.inner, this.outer);

  /// What the inner scroll view is written as.
  final String inner;

  /// What the outer one is written as.
  final String outer;

  @override
  String toString() => '$inner inside $outer';
}

/// The nearest enclosing widget of [element] that reads as a scroll view.
///
/// `Scrollable` is what the tree holds and `ListView` is what the file says, so
/// a finding names the widget a reader can search for.
String _scrollViewName(Element element) {
  String? name;
  element.visitAncestorElements((Element parent) {
    final Widget widget = parent.widget;
    if (widget is ListView ||
        widget is CustomScrollView ||
        widget is SingleChildScrollView ||
        widget is GridView ||
        widget is PageView) {
      name = '${widget.runtimeType}';
      return false;
    }
    // Stop before leaving this scroll view for the one above it.
    if (widget is Viewport || widget is ShrinkWrappingViewport) return true;
    return true;
  });
  return name ?? 'Scrollable';
}

/// Every vertical scroll view that sits inside another on the same route.
List<Nesting> nestingsNow() {
  final List<Nesting> found = <Nesting>[];
  for (final Element element in compositionElements()) {
    final Widget widget = element.widget;
    if (widget is! Scrollable || !isVerticalScrollable(widget)) continue;
    Element? outer;
    bool ownedByEditor = false;
    element.visitAncestorElements((Element parent) {
      final Widget up = parent.widget;
      if (up is EditableText) {
        // A multiline editor scrolls its own value. That is the field, not a
        // region, and it is not what 13 section 2.1 is about.
        ownedByEditor = true;
        return false;
      }
      if (up is Scrollable && isVerticalScrollable(up)) {
        outer = parent;
        return false;
      }
      return true;
    });
    if (ownedByEditor || outer == null) continue;
    // A sheet or a dialog owns its own scroll, and the element tree has
    // already granted that allowance: a modal route's content is its own
    // overlay entry, a sibling of the entry the page is in, so the page's
    // scroll view is never an ancestor of anything inside the sheet. An
    // ancestor found here is therefore always on the same surface, and
    // comparing routes to prove it would only add a lookup that throws on a
    // deactivated element mid sweep.
    found.add(Nesting(_scrollViewName(element), _scrollViewName(outer!)));
  }
  return found;
}

// ---------------------------------------------------------------------------
// The text scan.
// ---------------------------------------------------------------------------

/// Any `shrinkWrap` argument.
final RegExp shrinkWrapArgument = RegExp(r'\bshrinkWrap\s*:');

/// A `shrinkWrap` argument turned off, which nests nothing.
///
/// Counted and subtracted rather than written as a negative lookahead in the
/// expression above: a lookahead after a greedy `\s*` matches the space before
/// the word it was meant to exclude, so `shrinkWrap: false` reads as a
/// finding on the second attempt the engine makes.
final RegExp shrinkWrapOff = RegExp(r'\bshrinkWrap\s*:\s*false\b');

/// The physics that exist only to stop a nested list scrolling.
final RegExp neverScrollable = RegExp(r'\bNeverScrollableScrollPhysics\b');

/// Drops comments, so a note about the rule is not read as a breach of it.
String withoutComments(String source) => source
    .replaceAll(RegExp(r'/\*[\s\S]*?\*/'), '')
    .replaceAll(RegExp(r'//.*'), '');

/// How many times [source] nests a list.
int nestingMarkersIn(String source) {
  final String code = withoutComments(source);
  return shrinkWrapArgument.allMatches(code).length -
      shrinkWrapOff.allMatches(code).length +
      neverScrollable.allMatches(code).length;
}

/// Every Dart file under the application's `lib/`.
List<File> libraryFiles() {
  final Directory root = Directory('lib');
  expect(
    root.existsSync(),
    isTrue,
    reason: 'run this test from the application root',
  );
  return <File>[
    for (final FileSystemEntity entity in root.listSync(recursive: true))
      if (entity is File && entity.path.endsWith('.dart')) entity,
  ];
}

/// Every file that nests a list, and how many times.
Map<String, int> nestingCensus() {
  final Map<String, int> found = <String, int>{};
  for (final File file in libraryFiles()) {
    final int count = nestingMarkersIn(file.readAsStringSync());
    if (count > 0) found[file.path] = count;
  }
  return found;
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('the backlog names cells the matrix runs', () {
    expectBacklogCellsExist(nestedScrollBacklog, 'nestedScrollBacklog');
  });

  group('no vertical scroll sits inside another', () {
    for (final CompositionScreen screen in compositionScreens) {
      for (final MapEntry<String, Size> window in compositionWindows.entries) {
        testWidgets('${screen.name} at ${window.key}', (
          WidgetTester tester,
        ) async {
          final List<String> failures = <String>[];
          await overCell(
            tester,
            screen: screen,
            window: window.value,
            measure: (String where) async {
              final Set<String> found = <String>{};
              await sweepScrolls(tester, () async {
                for (final Nesting nesting in nestingsNow()) {
                  found.add('$nesting');
                }
              });
              for (final String nesting in found) {
                failures.add('  $where: $nesting');
              }
            },
          );
          expectCell(
            cellOf(screen.name, window.key),
            failures: failures,
            backlog: nestedScrollBacklog,
            backlogName: 'nestedScrollBacklog',
            clause:
                '${screen.name} at ${window.key} scrolls inside a scroll. '
                '13 section 2.1 gives a screen one vertical scroll. A '
                'horizontal strip is the one exception, and a sheet owns its '
                'own.',
          );
        });
      }
    }
  });

  group('shrinkWrap and NeverScrollableScrollPhysics', () {
    test('the scanner reads a file the way a reviewer would', () {
      expect(nestingMarkersIn('ListView(shrinkWrap: true)'), 1);
      expect(nestingMarkersIn('ListView(shrinkWrap: widget.nested)'), 1);
      expect(nestingMarkersIn('ListView(shrinkWrap: false)'), 0);
      expect(
        nestingMarkersIn('physics: const NeverScrollableScrollPhysics()'),
        1,
      );
      expect(nestingMarkersIn('// shrinkWrap: true was here'), 0);
      expect(
        nestingMarkersIn('/// Never use NeverScrollableScrollPhysics.'),
        0,
      );
      expect(nestingMarkersIn('/* shrinkWrap: true */'), 0);
    });

    test('no file gained one', () {
      final Map<String, int> found = nestingCensus();
      final Iterable<String> unexpected = found.keys.where(
        (String path) => !shrinkWrapBacklog.containsKey(path),
      );
      expect(
        unexpected,
        isEmpty,
        reason:
            'these files nest a list and are not in the backlog. 13 section '
            '2.1: each of the two exists only to put a scroll inside a '
            'scroll.\n'
            '${unexpected.map((String p) => '  $p: ${found[p]}').join('\n')}',
      );
      for (final MapEntry<String, int> entry in found.entries) {
        expect(
          entry.value,
          lessThanOrEqualTo(shrinkWrapBacklog[entry.key]!),
          reason:
              '${entry.key} went from ${shrinkWrapBacklog[entry.key]} to '
              '${entry.value}. The backlog may only shrink.',
        );
      }
    });

    test('the backlog only lists files that still hold one', () {
      final Map<String, int> found = nestingCensus();
      for (final String path in shrinkWrapBacklog.keys) {
        expect(
          File(path).existsSync(),
          isTrue,
          reason: '$path is in the backlog and does not exist',
        );
        expect(
          found.containsKey(path),
          isTrue,
          reason: '$path is clean now, so delete it from the backlog',
        );
      }
    });
  });
}
