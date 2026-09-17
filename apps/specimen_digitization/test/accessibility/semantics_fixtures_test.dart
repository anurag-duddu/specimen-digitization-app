// What the accessibility tree says, screen by screen, checked in
// (accessibility, section 4.1, "Semantics-tree dump test per screen").
//
// Two halves. The first writes one text fixture per top-level surface into
// `test/accessibility/fixtures/`, so a change to what a screen reader hears
// shows up as a reviewable diff rather than as nobody noticing. Regenerate
// with `flutter test --update-goldens test/accessibility`.
//
// The second asserts the eight properties the accessibility document names
// and the guideline matchers cannot see: a disabled action says why, the
// evidence switcher exposes its selected state, a region overlay and its chip
// answer to the same name, the reading diff leads with its summary sentence,
// placeholders are silent while exactly one node says something is loading, a
// dialog takes focus and gives it back, a queue row can be activated and names
// its record, and a field row names its field.
//
// Everything here reads `tester.getSemantics`, never the rendered pixels.

import 'dart:io';
import 'dart:ui' show CheckedState, Tristate;

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/region_editor.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/search_filters.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import '../golden/golden_harness.dart';

/// Where the checked-in dumps live.
const String fixtureDirectory = 'test/accessibility/fixtures';

/// The window every dump is taken at.
///
/// Expanded, because it is the widest layout that still puts every surface on
/// one screen: a compact window hides the history pane behind a segment and a
/// large one splits the queue away from the record.
const Size dumpWindow = Size(1180, 820);

/// Values that change between runs and would make every dump a false diff.
///
/// A relative age, an absolute time carrying the machine's zone, and the
/// queue header's own seconds counter.
String stabilise(String input) => input
    .replaceAll(
      RegExp(r'\d+ \w{3} \d{4}, \d{2}:\d{2} [A-Za-z+\-0-9:]+'),
      '<absolute time>',
    )
    .replaceAll(RegExp(r'Updated \d+ (s|min|h) ago'), 'Updated <age> ago')
    .replaceAll(RegExp(r'\b\d+ (min|h|d|w)\b'), '<age>')
    .replaceAll('moments ago', '<age>')
    .replaceAll(RegExp(r'new-\d+'), 'new-<id>');

/// One line per semantics node, indented by depth.
///
/// Labels, hints and values because a screen reader speaks all three; the
/// role, the button and selected flags and the tap action because those are
/// what decide whether a node can be reached and activated at all.
String dumpSemantics(WidgetTester tester) {
  final StringBuffer out = StringBuffer();
  void walk(SemanticsNode node, int depth) {
    final SemanticsData data = node.getSemanticsData();
    final List<String> parts = <String>[];
    if (data.role != SemanticsRole.none) parts.add('role=${data.role.name}');
    if (data.flagsCollection.isButton) parts.add('button');
    if (data.flagsCollection.isTextField) parts.add('textField');
    if (data.flagsCollection.isSelected != Tristate.none) {
      parts.add('selected=${data.flagsCollection.isSelected.toBoolOrNull()}');
    }
    if (data.flagsCollection.isChecked != CheckedState.none) {
      parts.add('checked=${data.flagsCollection.isChecked.name}');
    }
    if (data.flagsCollection.isEnabled != Tristate.none) {
      parts.add('enabled=${data.flagsCollection.isEnabled.toBoolOrNull()}');
    }
    if (data.flagsCollection.isLiveRegion) parts.add('liveRegion');
    if (data.flagsCollection.isInMutuallyExclusiveGroup) {
      parts.add('inMutuallyExclusiveGroup');
    }
    if (data.hasAction(SemanticsAction.tap)) parts.add('tap');
    if (data.label.isNotEmpty) parts.add('label="${data.label}"');
    if (data.value.isNotEmpty) parts.add('value="${data.value}"');
    if (data.hint.isNotEmpty) parts.add('hint="${data.hint}"');
    if (data.tooltip.isNotEmpty) parts.add('tooltip="${data.tooltip}"');
    if (parts.isNotEmpty) {
      out.writeln('${'  ' * depth}${parts.join(' ')}'.replaceAll('\n', ' '));
    }
    // A node that merges its descendants is the only node the platform is
    // sent for that subtree, so descending past it would print controls that
    // no screen reader ever stops on and turn one control into two findings.
    if (node.mergeAllDescendantsIntoThisNode) return;
    node.visitChildren((SemanticsNode child) {
      walk(child, parts.isEmpty ? depth : depth + 1);
      return true;
    });
  }

  walk(tester.getSemantics(find.byType(MaterialApp)), 0);
  return stabilise(out.toString());
}

/// Compares the tree against `fixtures/<name>.txt`, or rewrites it under
/// `--update-goldens`.
void expectSemanticsFixture(WidgetTester tester, String name) {
  final String actual = dumpSemantics(tester);
  final File file = File('$fixtureDirectory/$name.txt');
  if (autoUpdateGoldenFiles) {
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(actual);
    return;
  }
  expect(
    file.existsSync(),
    isTrue,
    reason:
        'no checked-in semantics fixture for $name; regenerate with '
        'flutter test --update-goldens test/accessibility',
  );
  expect(
    actual,
    file.readAsStringSync(),
    reason:
        'the semantics tree for $name changed. Read the diff: a reviewer '
        'using a screen reader now hears something different. Regenerate '
        'with flutter test --update-goldens test/accessibility once the '
        'change is the one you meant.',
  );
}

/// Every label, value, hint and tooltip in the tree, in tree order.
List<String> spokenNames(WidgetTester tester) {
  final List<String> names = <String>[];
  void walk(SemanticsNode node) {
    final SemanticsData data = node.getSemanticsData();
    for (final String part in <String>[
      data.label,
      data.value,
      data.hint,
      data.tooltip,
    ]) {
      if (part.isNotEmpty) names.add(part);
    }
    if (node.mergeAllDescendantsIntoThisNode) return;
    node.visitChildren((SemanticsNode child) {
      walk(child);
      return true;
    });
  }

  walk(tester.getSemantics(find.byType(MaterialApp)));
  return names;
}

/// Pumps one widget on the product theme at a known window.
Future<void> pumpSurface(
  WidgetTester tester,
  Widget child, {
  Size window = dumpWindow,
  bool settle = true,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    ),
  );
  // A placeholder pulses until it is replaced, so a surface that holds one
  // never settles; those callers pump two frames instead.
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    await tester.pump();
    await tester.pump();
  }
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('checked-in semantics trees', () {
    testWidgets('queue', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpGoldenApp(
        tester,
        window: dumpWindow,
        brightness: Brightness.light,
        location: goldenQueueLocation,
      );
      expectSemanticsFixture(tester, 'queue');
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    for (final WorkbenchSegment segment in WorkbenchSegment.values) {
      testWidgets('workbench ${segment.name}', (WidgetTester tester) async {
        final SemanticsHandle handle = tester.ensureSemantics();
        await pumpGoldenApp(
          tester,
          window: dumpWindow,
          brightness: Brightness.light,
          location: goldenSpecimenLocation,
        );
        final Finder tab = find
            .descendant(
              of: find.byType(SegmentedButton<WorkbenchSegment>),
              matching: find.text(segment.label),
            )
            .first;
        await tester.ensureVisible(tab);
        await tester.pumpAndSettle();
        await tester.tap(tab);
        await tester.pumpAndSettle();
        expectSemanticsFixture(tester, 'workbench-${segment.name}');
        handle.dispose();
        await tester.pumpWidget(const SizedBox());
      });
    }

    testWidgets('intake', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpGoldenApp(
        tester,
        window: dumpWindow,
        brightness: Brightness.light,
        location: goldenIntakeLocation,
      );
      expectSemanticsFixture(tester, 'intake');
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('filters', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpSurface(
        tester,
        const SearchFilters(initial: <String, String>{}),
      );
      expectSemanticsFixture(tester, 'filters');
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('region editor', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpSurface(
        tester,
        RegionEditorBody(regions: goldenRegions, asset: goldenEditableAsset()),
      );
      expectSemanticsFixture(tester, 'region-editor');
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('reason sheet', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpSurface(
        tester,
        const ReasonForm(
          title: 'Approve record',
          action: 'Record review approval',
          consequence: 'The record is cleared for publication.',
          retained: 'Every earlier decision stays in the history.',
          outstanding: <String>['A supported collector is required'],
          recentReasons: <String>['Label read and confirmed'],
        ),
      );
      expectSemanticsFixture(tester, 'reason-sheet');
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });
  });

  group('what a screen reader must be able to tell', () {
    testWidgets('every disabled action carries a hint saying why', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpGoldenApp(
        tester,
        window: dumpWindow,
        brightness: Brightness.light,
        location: goldenSpecimenLocation,
        repository: _ViewerRepository(),
      );

      final List<String> silent = <String>[];
      void walk(SemanticsNode node) {
        final SemanticsData data = node.getSemanticsData();
        final bool disabledAction =
            data.flagsCollection.isButton &&
            data.flagsCollection.isEnabled == Tristate.isFalse;
        if (disabledAction && data.hint.isEmpty && data.tooltip.isEmpty) {
          silent.add(data.label.isEmpty ? '<unnamed>' : data.label);
        }
        if (node.mergeAllDescendantsIntoThisNode) return;
        node.visitChildren((SemanticsNode child) {
          walk(child);
          return true;
        });
      }

      walk(tester.getSemantics(find.byType(MaterialApp)));
      expect(
        silent,
        isEmpty,
        reason:
            'a dimmed control that says nothing is a dead end for a screen '
            'reader (accessibility, section 3.2)',
      );
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the evidence switcher exposes which segment is selected', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpGoldenApp(
        tester,
        window: dumpWindow,
        brightness: Brightness.light,
        location: goldenSpecimenLocation,
      );

      final Finder selector = find.byType(SegmentedButton<WorkbenchSegment>);
      expect(selector, findsOneWidget);
      final Map<String, bool> states = <String, bool>{};
      void walk(SemanticsNode node) {
        final SemanticsData data = node.getSemanticsData();
        if (data.flagsCollection.isChecked != CheckedState.none &&
            data.label.isNotEmpty) {
          states[data.label] =
              data.flagsCollection.isChecked == CheckedState.isTrue;
        }
        node.visitChildren((SemanticsNode child) {
          walk(child);
          return true;
        });
      }

      walk(tester.getSemantics(selector));
      // Every segment answers to its visible word, and exactly one of them is
      // the current one. Without this a reviewer hears three identical
      // buttons and cannot tell which panel they are in.
      expect(states.keys, containsAll(<String>['Readings', 'Fields']));
      expect(
        states.values.where((bool selected) => selected).length,
        1,
        reason: 'exactly one segment is current',
      );
      expect(states['Readings'], isTrue);
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the evidence switcher announces itself as a tab list', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpGoldenApp(
        tester,
        window: dumpWindow,
        brightness: Brightness.light,
        location: goldenSpecimenLocation,
      );
      final List<SemanticsRole> roles = <SemanticsRole>[];
      void walk(SemanticsNode node) {
        roles.add(node.getSemanticsData().role);
        node.visitChildren((SemanticsNode child) {
          walk(child);
          return true;
        });
      }

      walk(tester.getSemantics(find.byType(SegmentedButton<WorkbenchSegment>)));
      expect(roles, contains(SemanticsRole.tab));
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a region overlay and its chip answer to the same name', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpGoldenApp(
        tester,
        window: dumpWindow,
        brightness: Brightness.light,
        location: goldenSpecimenLocation,
        // The default fixture is an original with no verified orientation,
        // and the workbench correctly draws no overlays on one of those.
        repository: GoldenRepository.verified(),
      );
      expect(find.byType(RegionOverlay), findsWidgets);
      final List<String> spoken = spokenNames(tester);
      // The overlay drawn on the photograph and the chip in the strip beneath
      // it are two ways to reach one region, so they have to be one name.
      for (final String region in <String>['Label 1', 'Label 2']) {
        expect(
          spoken.where((String name) => name.contains(region)).length,
          greaterThanOrEqualTo(2),
          reason:
              '$region must be reachable by the same name from the overlay '
              'and from the chip strip',
        );
      }
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('the reading diff speaks its summary before the text', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpSurface(
        tester,
        const DiffText(text: 'Chicago 1917', reference: 'Chicago 1912'),
      );
      final Iterable<String> spoken = spokenNames(tester);
      final String block = spoken.firstWhere(
        (String name) => name.contains('Chicago 1917'),
        orElse: () => '',
      );
      expect(block, isNotEmpty, reason: 'the reading must be spoken at all');
      expect(
        block.indexOf('Full text:'),
        greaterThan(0),
        reason:
            'the summary sentence comes first, then the text '
            '(accessibility, section 3.1)',
      );
      expect(
        block.substring(0, block.indexOf('Full text:')).toLowerCase(),
        contains('differ'),
        reason: 'the summary says the two readings are not the same',
      );
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('placeholders are silent and one node says it is loading', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpSurface(
        tester,
        const Column(
          children: <Widget>[
            LoadingAnnouncement(thing: 'queue', visible: true),
            SkeletonRow(),
            SkeletonRow(),
            SkeletonRow(),
            SkeletonBlock(),
          ],
        ),
        settle: false,
      );
      final List<String> spoken = spokenNames(tester);
      expect(
        spoken.where((String name) => name.startsWith('Loading')).length,
        1,
        reason: 'exactly one announcement, however many placeholders are drawn',
      );
      expect(spoken.single, 'Loading queue');
      // And the live flag, so it is heard when it appears rather than only
      // when focus happens to land on it.
      expect(
        tester
            .getSemantics(find.byType(LoadingAnnouncement))
            .getSemanticsData()
            .flagsCollection
            .isLiveRegion,
        isTrue,
      );
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a silent wait still announces that the queue is loading', (
      WidgetTester tester,
    ) async {
      // Finding V-4. With `visible` false, which is how the queue's own first
      // load uses it, there is no text on screen to host a live region and a
      // zero-size node is dropped from the semantics tree. The wait is
      // carried by an announcement instead, which is what a momentary event
      // with no text host is for.
      final SemanticsHandle handle = tester.ensureSemantics();
      final List<String> announced = <String>[];
      tester.binding.defaultBinaryMessenger.setMockDecodedMessageHandler<
        dynamic
      >(SystemChannels.accessibility, (dynamic message) async {
        final Map<Object?, Object?> event = message! as Map<Object?, Object?>;
        if (event['type'] != 'announce') return;
        final Map<Object?, Object?> data =
            event['data']! as Map<Object?, Object?>;
        announced.add(data['message'].toString());
      });
      addTearDown(
        () => tester.binding.defaultBinaryMessenger
            .setMockDecodedMessageHandler<dynamic>(
              SystemChannels.accessibility,
              null,
            ),
      );

      await pumpSurface(
        tester,
        Builder(
          builder: (BuildContext context) => MediaQuery(
            // The platform flag the framework gates `sendAnnouncement` on.
            data: MediaQuery.of(context).copyWith(supportsAnnounce: true),
            child: const Column(
              children: <Widget>[
                LoadingAnnouncement(thing: 'queue'),
                SkeletonRow(),
                SkeletonRow(),
              ],
            ),
          ),
        ),
        settle: false,
      );
      await tester.pump();
      expect(announced, contains('Loading queue'));
      // And no focusable node nobody can see was left behind to carry it.
      expect(spokenNames(tester), isNot(contains('Loading queue')));
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a dialog takes focus and gives it back on close', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = dumpWindow;
      addTearDown(tester.view.reset);
      final FocusNode opener = FocusNode(debugLabel: 'opener');
      addTearDown(opener.dispose);
      await tester.pumpWidget(
        MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: AppTheme.light(),
          home: Builder(
            builder: (BuildContext context) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  focusNode: opener,
                  onPressed: () => showReasonSheet(
                    context,
                    title: 'Approve record',
                    action: 'Record review approval',
                    consequence: 'The record is cleared for publication.',
                  ),
                  child: const Text('Approve record'),
                ),
              ),
            ),
          ),
        ),
      );
      opener.requestFocus();
      await tester.pumpAndSettle();
      expect(FocusManager.instance.primaryFocus, opener);

      await tester.tap(find.text('Approve record'));
      await tester.pumpAndSettle();
      // Focus is inside the sheet, on the field the reviewer has to fill,
      // not left behind on the button that opened it.
      expect(find.byType(ReasonForm), findsOneWidget);
      final FocusNode? inside = FocusManager.instance.primaryFocus;
      expect(inside, isNot(opener));
      expect(
        find.descendant(
          of: find.byType(ReasonForm),
          matching: find.byWidgetPredicate(
            (Widget w) => w is Focus && w.focusNode == inside,
          ),
        ),
        findsWidgets,
        reason: 'initial focus lands inside the sheet',
      );

      Navigator.of(tester.element(find.byType(ReasonForm))).pop();
      await tester.pumpAndSettle();
      expect(
        FocusManager.instance.primaryFocus,
        opener,
        reason: 'focus returns to the control that opened the sheet',
      );
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a queue row is a button that names its record', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpGoldenApp(
        tester,
        window: dumpWindow,
        brightness: Brightness.light,
        location: goldenQueueLocation,
      );
      // The row's one merged node is the `UiListRow` it composes.
      final SemanticsData row = tester
          .getSemantics(
            find.descendant(
              of: find.byType(QueueRow).first,
              matching: find.byType(UiListRow),
            ),
          )
          .getSemanticsData();
      expect(row.flagsCollection.isButton, isTrue);
      expect(row.hasAction(SemanticsAction.tap), isTrue);
      expect(row.label, contains('Pinned beetle, Chicago 1912'));
      // And the label carries the state and the reason too, so two rows in
      // the same queue are told apart without opening either.
      expect(row.label, contains('needs review'));
      expect(row.label, contains('human approval required'));
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a field row names its field', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpSurface(
        tester,
        const Column(
          children: <Widget>[
            FieldRow(
              name: 'Country',
              state: SpecimenStatus.cleared,
              asWritten: 'U.S.A.',
            ),
            FieldRow(
              name: 'Collectors',
              state: SpecimenStatus.needsReview,
              asWritten: 'A. Smith',
            ),
          ],
        ),
      );
      final String first = tester
          .getSemantics(find.byType(FieldRow).first)
          .getSemanticsData()
          .label;
      final String second = tester
          .getSemantics(find.byType(FieldRow).last)
          .getSemanticsData()
          .label;
      expect(first, contains('Country'));
      expect(second, contains('Collectors'));
      expect(first, isNot(second));
      handle.dispose();
      await tester.pumpWidget(const SizedBox());
    });
  });
}

/// A collection this account may look at but not act on, so every reviewer
/// control is disabled and has to say why.
class _ViewerRepository extends GoldenRepository {
  @override
  Future<List<CollectionScope>> scopes() async => <CollectionScope>[
    const CollectionScope(
      organizationId: 'org',
      collectionId: 'insects',
      name: 'Synthetic Insects',
      permissions: <String>['viewer'],
    ),
  ];
}
