// What the accessibility tree actually says (smoke test defects 4 and 5).
//
// The four guideline matchers check that a tappable node has some label and a
// big enough box. They do not check that the label distinguishes one row from
// the next, and they do not check that a row can be activated. A reviewer
// using the client through a browser's accessibility tree found both missing:
// the queue exposed rows that could not be opened, and twenty field rows that
// all announced the same three words.
//
// Everything here reads the tree with `tester.getSemantics`, never the
// rendered pixels.

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import '../app/routing_test.dart' show pumpApp;

Future<void> pumpPanel(WidgetTester tester, Widget child) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(1000, 2000);
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      home: Scaffold(body: child),
    ),
  );
  await tester.pumpAndSettle();
}

/// Every name the semantics tree currently carries, in tree order.
///
/// Labels and tooltips both, because an icon-only control names itself
/// through its tooltip and a screen reader reads that name.
List<String> allSemanticsNames(WidgetTester tester) {
  final List<String> labels = <String>[];
  void walk(SemanticsNode node) {
    final SemanticsData data = node.getSemanticsData();
    if (data.label.isNotEmpty) labels.add(data.label);
    if (data.tooltip.isNotEmpty) labels.add(data.tooltip);
    node.visitChildren((SemanticsNode child) {
      walk(child);
      return true;
    });
  }

  walk(tester.getSemantics(find.byType(MaterialApp)));
  return labels;
}

void main() {
  testWidgets('the queue exposes rows a reviewer can open from the tree', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpApp(tester);

    // `QueueRow` composes a `UiListRow`, which is where the row's one merged
    // node lives; a finder on the pattern itself resolves to the node above
    // it.
    final Finder row = find.descendant(
      of: find.byType(QueueRow).first,
      matching: find.byType(UiListRow),
    );
    final SemanticsNode node = tester.getSemantics(row);
    final SemanticsData data = node.getSemanticsData();

    // A row names the record, not just its state.
    expect(data.label, contains('Synthetic insect label'));
    // It is a button, and it can be activated without a pointer.
    expect(data.flagsCollection.isButton, isTrue);
    expect(data.hasAction(SemanticsAction.tap), isTrue);

    handle.dispose();
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('the queue controls beside the list all carry names', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpApp(tester);

    // The search field.
    expect(
      tester
          .getSemantics(find.byType(TextField).first)
          .getSemanticsData()
          .label,
      contains('Search by specimen ID'),
    );

    // The destinations, the filters control and the help control. Read from
    // the tree itself rather than through a finder: a label merged into an
    // ancestor node belongs to no widget, and a merged label is still a label
    // a screen reader reads.
    final List<String> spoken = allSemanticsNames(tester);
    for (final String name in <String>[
      'Queue',
      'Intake',
      'Filters',
      'Help and shortcuts',
      'Search by specimen ID',
    ]) {
      expect(
        spoken.any((String label) => label.contains(name)),
        isTrue,
        reason: '$name is not in the semantics tree',
      );
    }

    handle.dispose();
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a field row announces which field it is', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpPanel(
      tester,
      const Column(
        children: <Widget>[
          FieldRow(
            name: 'Country',
            state: SpecimenStatus.cleared,
            asWritten: 'Chicago',
          ),
          FieldRow(
            name: 'Collector',
            state: SpecimenStatus.cleared,
            asWritten: 'A. Smith',
          ),
        ],
      ),
    );

    // Two rows in the same state used to be indistinguishable, because the
    // only label either produced came from its status chip.
    final String first = tester
        .getSemantics(find.byType(FieldRow).first)
        .getSemanticsData()
        .label;
    final String second = tester
        .getSemantics(find.byType(FieldRow).last)
        .getSemanticsData()
        .label;
    expect(first, contains('Country'));
    expect(second, contains('Collector'));
    expect(first, isNot(second));

    handle.dispose();
  });

  testWidgets('an evidence drawer can name what it holds', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpPanel(
      tester,
      const Column(
        children: <Widget>[
          EvidenceDrawer(
            payload: <String, dynamic>{'revision': 3},
            section: 'Version 3',
          ),
          EvidenceDrawer(
            payload: <String, dynamic>{'revision': 4},
            section: 'Version 4',
          ),
        ],
      ),
    );

    // The visible word stays the same, so the control is still learned once.
    expect(find.text(EvidenceDrawer.defaultTitle), findsNWidgets(2));
    // The spoken name does not.
    expect(find.bySemanticsLabel(RegExp('Version 3')), findsWidgets);
    expect(find.bySemanticsLabel(RegExp('Version 4')), findsWidgets);

    handle.dispose();
  });
}
