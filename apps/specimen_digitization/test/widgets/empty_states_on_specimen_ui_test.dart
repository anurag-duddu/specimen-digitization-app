// Empty states and loading placeholders come from `specimen_ui` directly
// (10 sections 4.5 and 5).
//
// The app kept its own `EmptyState`, which put `UiEmptyState` inside the same
// centre, reading measure and s6 by s12 padding `UiEmptyState` already draws,
// so every empty state the app raised carried its padding twice. It also kept
// `SkeletonBar`, `SkeletonRow` and `SkeletonBlock` over `UiSkeleton`, and the
// queue drew a third, text-only absence for an empty review view. These tests
// hold all three gone: a real screen's empty state is one `UiEmptyState` and
// nothing around it, the queue's empty views are that same component, and
// `lib/` declares no widget of its own over either one.

import 'dart:io';

import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/sources/sources_screen.dart';
import 'package:specimen_digitization/src/sources.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../screens/queue_test.dart' show ScriptedRepository, pumpQueue;
import '../screens/source_screen_test.dart' show pumpBrowse;
import '../sources/source_fixtures.dart';
import '../ui_finders.dart' show pickSpecimenQueue;
import 'harness.dart';

/// The insets `UiEmptyState` draws around its own column.
EdgeInsetsDirectional _ownInsets(UiThemeData ui) =>
    EdgeInsetsDirectional.symmetric(
      horizontal: ui.space.s6,
      vertical: ui.space.s12,
    );

/// The `UiEmptyState` titled [title], which must be the only one.
Finder _emptyState(String title) =>
    find.ancestor(of: find.text(title), matching: find.byType(UiEmptyState));

/// Holds the empty state titled [title] to one layer of its own insets.
///
/// Between the window and the glyph there is exactly one padding with
/// `UiEmptyState`'s insets and exactly one reading measure, which are the
/// empty state's own. A wrapper that adds them again doubles both.
void expectOneInsetLayer(WidgetTester tester, String title) {
  final Finder state = _emptyState(title);
  expect(state, findsOneWidget, reason: '"$title" is a UiEmptyState');
  final UiThemeData ui = tester.element(state).ui;
  final Finder glyph = find.descendant(
    of: state,
    matching: find.byType(UiIcon),
  );
  expect(
    find.ancestor(
      of: glyph,
      matching: find.byWidgetPredicate(
        (Widget widget) =>
            widget is Padding && widget.padding == _ownInsets(ui),
      ),
    ),
    findsOneWidget,
    reason:
        'UiEmptyState pads its column by s6 and s12 itself; a second layer '
        'of the same insets is a wrapper doubling it',
  );
  expect(
    find.ancestor(
      of: glyph,
      matching: find.byWidgetPredicate(
        (Widget widget) =>
            widget is ConstrainedBox &&
            widget.constraints.maxWidth == ui.space.readingMax,
      ),
    ),
    findsOneWidget,
    reason: "one reading measure, and it is the empty state's own",
  );
}

/// Holds the sliver slot a screen hands its empty state to that state alone.
///
/// The box in the slot is the `UiEmptyState` itself, and the glyph sits one
/// s12 below the slot's top, which is what `UiEmptyState` alone produces.
void expectSlotIsTheEmptyState(WidgetTester tester, String title) {
  final Finder state = _emptyState(title);
  expect(state, findsOneWidget, reason: '"$title" is a UiEmptyState');
  final UiThemeData ui = tester.element(state).ui;
  final Finder adapter = find.ancestor(
    of: state,
    matching: find.byType(SliverToBoxAdapter),
  );
  expect(
    adapter,
    findsWidgets,
    reason: 'each screen here hands its empty state a sliver slot',
  );
  final RenderSliverToBoxAdapter sliver = tester
      .renderObject<RenderSliverToBoxAdapter>(adapter.first);
  final RenderBox slot = sliver.child!;
  final Rect slotRect = slot.localToGlobal(Offset.zero) & slot.size;
  expect(
    tester.getRect(state),
    slotRect,
    reason: 'the slot holds the empty state and nothing drawn around it',
  );
  final Finder glyph = find.descendant(
    of: state,
    matching: find.byType(UiIcon),
  );
  expect(
    tester.getTopLeft(glyph).dy - slotRect.top,
    ui.space.s12,
    reason: 'the glyph sits one s12 below the slot, not two',
  );
}

/// A real screen showing an empty state, and the title it shows.
typedef _CallSite = ({
  String name,
  String title,
  Future<void> Function(WidgetTester tester) pump,
});

final List<_CallSite> _callSites = <_CallSite>[
  (
    name: 'a collection with no sources',
    title: 'No sources registered',
    pump: (WidgetTester tester) => pumpComponent(
      tester,
      SourcesScreen(
        repository: FakeSourceRepository(sources0: const <RegisteredSource>[]),
        scope: testScope,
        onOpen: (RegisteredSource _) {},
      ),
    ),
  ),
  (
    name: 'a source with no photographs',
    title: 'No photographs here',
    pump: (WidgetTester tester) => pumpBrowse(
      tester,
      FakeSourceRepository(objects: const <SourceObject>[]),
    ),
  ),
  (
    name: 'an empty review view in the queue',
    title: 'No specimens need a human',
    pump: (WidgetTester tester) => pumpQueue(tester, ScriptedRepository()),
  ),
];

void main() {
  group('a screen empty state has one padding layer', () {
    for (final _CallSite site in _callSites) {
      testWidgets('${site.name}: one layer of insets', (
        WidgetTester tester,
      ) async {
        await site.pump(tester);
        expectOneInsetLayer(tester, site.title);
        await tester.pumpWidget(const SizedBox());
      });

      testWidgets('${site.name}: the slot is the empty state', (
        WidgetTester tester,
      ) async {
        await site.pump(tester);
        expectSlotIsTheEmptyState(tester, site.title);
        await tester.pumpWidget(const SizedBox());
      });
    }
  });

  testWidgets('the queue empty review views are UiEmptyState', (
    WidgetTester tester,
  ) async {
    await pumpQueue(tester, ScriptedRepository());
    final Finder pane = find.byType(QueuePane);
    for (final MapEntry<String, String> view in <String, String>{
      'Needs a human': 'No specimens need a human',
      'Deferred': 'No deferred specimens',
      'Cleared': 'No cleared specimens',
    }.entries) {
      await pickSpecimenQueue(tester, view.key);
      final Finder state = find.descendant(
        of: pane,
        matching: find.byType(UiEmptyState),
      );
      expect(
        state,
        findsOneWidget,
        reason: 'the ${view.key} view names its absence with the component',
      );
      final UiEmptyState empty = tester.widget<UiEmptyState>(state);
      expect(empty.title, view.value);
      expect(
        empty.icon,
        UiIcons.queue,
        reason: 'the registry names the queue glyph as the empty-queue glyph',
      );
      expect(
        empty.body,
        endsWith('.'),
        reason: 'one sentence saying what would fill the view',
      );
      expect(
        empty.action,
        isNull,
        reason: 'nothing on this screen fills a review view',
      );
    }
    await tester.pumpWidget(const SizedBox());
  });

  test(
    'lib/ declares no widget of its own over UiEmptyState or UiSkeleton',
    () {
      // A class named for either component is a second copy of it. The four
      // this replaced were `EmptyState`, `SkeletonRow`, `SkeletonBar` and
      // `SkeletonBlock`. `specimen_ui` lives under `packages/`, outside the
      // directory this scans.
      final Directory root = Directory('lib');
      expect(root.existsSync(), isTrue, reason: 'run this from the app root');
      final RegExp declaration = RegExp(
        r'^\s*(?:(?:abstract|base|final|sealed|interface|mixin)\s+)*class\s+'
        r'(_?\w*(?:EmptyState|Skeleton)\w*)\b',
        multiLine: true,
      );
      final List<String> found = <String>[
        for (final FileSystemEntity entity in root.listSync(recursive: true))
          if (entity is File && entity.path.endsWith('.dart'))
            for (final RegExpMatch match in declaration.allMatches(
              entity.readAsStringSync(),
            ))
              '${entity.path}: ${match.group(1)}',
      ];
      expect(
        found,
        isEmpty,
        reason:
            'use UiEmptyState and UiSkeleton from specimen_ui directly '
            '(10 section 5)',
      );
    },
  );
}
