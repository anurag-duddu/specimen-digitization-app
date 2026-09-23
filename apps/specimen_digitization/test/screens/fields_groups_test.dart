// The Fields segment in two groups, required and optional (UI.md T2.3).

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';

import '../widgets/harness.dart';

Json field(String key, String name, {required bool required}) =>
    <String, dynamic>{
      'field_key': key,
      'display_name': name,
      'required': required,
      'state': 'unknown',
      'literal_value': null,
    };

Specimen record(List<Json> fields) => Specimen(<String, dynamic>{
  'specimen_id': 'specimen-fields',
  'revision': 3,
  'fields': fields,
});

Future<void> pumpFields(WidgetTester tester, Specimen specimen) =>
    pumpComponent(
      tester,
      SingleChildScrollView(
        child: WorkbenchFields(
          specimen: specimen,
          anchors: <String, GlobalKey>{
            for (final Json f in specimen.fields)
              f['field_key'] as String: GlobalKey(),
          },
          pending: const <PendingFieldChange>[],
          onPendingChanged: (_) {},
          onFocusRegion: (_) {},
        ),
      ),
      size: const Size(1000, 3000),
    );

double top(WidgetTester tester, String text) =>
    tester.getTopLeft(find.text(text)).dy;

void main() {
  // The record's order interleaves the groups, as a profile's order can.
  final List<Json> fields = <Json>[
    field('country', 'Country', required: true),
    field('habitat', 'Habitat', required: false),
    field('collectors', 'Collectors', required: true),
    field('identified_by_irn', 'Identified by IRN', required: false),
  ];

  testWidgets('required fields come first, under their own heading', (
    WidgetTester tester,
  ) async {
    await pumpFields(tester, record(fields));
    final double required = top(tester, 'Required fields');
    final double optional = top(tester, 'Optional fields');
    expect(required, lessThan(optional));
    for (final String row in <String>[
      'Country (required)',
      'Collectors (required)',
    ]) {
      expect(top(tester, row), inExclusiveRange(required, optional));
    }
    for (final String row in <String>['Habitat', 'Identified by IRN']) {
      expect(top(tester, row), greaterThan(optional));
    }
  });

  testWidgets("within a group the record's order holds", (
    WidgetTester tester,
  ) async {
    await pumpFields(tester, record(fields));
    expect(
      top(tester, 'Country (required)'),
      lessThan(top(tester, 'Collectors (required)')),
    );
    expect(top(tester, 'Habitat'), lessThan(top(tester, 'Identified by IRN')));
  });

  testWidgets('each group heading is a heading', (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await pumpFields(tester, record(fields));
    for (final String heading in <String>[
      'Required fields',
      'Optional fields',
    ]) {
      expect(
        tester.getSemantics(find.text(heading)),
        matchesSemantics(label: heading, isHeader: true),
      );
    }
    handle.dispose();
  });

  testWidgets('a group with no fields is left out', (
    WidgetTester tester,
  ) async {
    await pumpFields(
      tester,
      record(<Json>[
        field('country', 'Country', required: true),
        field('collectors', 'Collectors', required: true),
      ]),
    );
    expect(find.text('Required fields'), findsOneWidget);
    expect(find.text('Optional fields'), findsNothing);
  });

  testWidgets('a record with no fields keeps its caveat and no group', (
    WidgetTester tester,
  ) async {
    await pumpFields(tester, record(const <Json>[]));
    expect(find.text('No fields recorded yet.'), findsOneWidget);
    expect(find.text('Required fields'), findsNothing);
    expect(find.text('Optional fields'), findsNothing);
  });
}
