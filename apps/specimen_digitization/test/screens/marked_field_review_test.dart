// A field the units path settled for a person to check (docs/execution/units/
// PLAN.md, WP 1.6; FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 4,
// "Marked"). Its code `marked:<field>:<label>:<why>` reaches the app the way
// the workspace route publishes a run reason: a hard finding with no field
// key (`validations`), and in the summary's `reason_codes`. The field is the
// first part after `marked:`, so a supported field with a marked code is a
// field review and counts in its group's review count.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import '../widgets/harness.dart';

const String textOnly =
    'Only the readings back this value. The image and sources do not confirm '
    'it.';
const String conflict =
    'Another backed text competes with this value. Check it against the image.';
const String generic = 'Review the value and its supporting sources.';

/// A record with label L1, a supported habitat and collectors, and [reasons]
/// published as the workspace route publishes `run.reasons`.
Specimen record(
  List<String> reasons, {
  bool asFindings = true,
  List<Json> notes = const <Json>[],
}) => Specimen(<String, dynamic>{
  'specimen_id': 'marked',
  'revision': 2,
  'regions': <Json>[
    <String, dynamic>{'region_id': 'L1'},
  ],
  'fields': <Json>[
    <String, dynamic>{
      'field_key': 'habitat',
      'state': 'supported',
      'literal_value': 'Synthetic grassland',
    },
    <String, dynamic>{
      'field_key': 'collectors',
      'state': 'supported',
      'literal_value': 'H. Hoogstraal',
    },
  ],
  'reason_codes': reasons,
  'validation_findings': <Json>[
    if (asFindings)
      for (final String reason in reasons)
        <String, dynamic>{
          'rule_id': reason,
          'severity': 'hard',
          'outcome': 'fail',
          'reason_code': reason,
        },
    ...notes,
  ],
});

void main() {
  // Each row: the code, the field it targets (null: none), the message and
  // the next step the blockers list gives.
  final List<(String, String?, String, String)> rows =
      <(String, String?, String, String)>[
        (
          'marked:habitat:L1:text_only',
          'habitat',
          'Habitat is marked for review on Label 1',
          textOnly,
        ),
        (
          'marked:habitat:L1:conflict',
          'habitat',
          'Habitat is marked for review on Label 1',
          conflict,
        ),
        (
          'marked:collectors:L1:text_only',
          'collectors',
          'Collectors are marked for review on Label 1',
          textOnly,
        ),
        // A label the record does not hold is not named.
        (
          'marked:habitat:L9:text_only',
          'habitat',
          'Habitat is marked for review',
          textOnly,
        ),
        // A why the app has no words for falls back to the general step.
        (
          'marked:habitat:L1:other',
          'habitat',
          'Habitat is marked for review on Label 1',
          generic,
        ),
        ('marked:habitat', 'habitat', 'Habitat is marked for review', generic),
        // A field the record does not hold, and no field: no field target.
        (
          'marked:county:L1:text_only',
          null,
          'A specimen check needs review before approval',
          'Review the recorded issue before approving the specimen.',
        ),
        (
          'marked:',
          null,
          'A specimen check needs review before approval',
          'Review the recorded issue before approving the specimen.',
        ),
        // A field reason whose whole suffix is the field reads as before.
        (
          'mandatory_unresolved:habitat',
          'habitat',
          'Habitat needs a supported value',
          generic,
        ),
      ];

  for (final (String code, String? field, String message, String detail)
      in rows) {
    for (final bool asFindings in <bool>[true, false]) {
      test('$code from ${asFindings ? 'a hard finding' : 'reason codes'}', () {
        final List<ClearanceBlocker> blockers = blockersFor(
          record(<String>[code], asFindings: asFindings),
        );
        expect(blockers, hasLength(1));
        final ClearanceBlocker blocker = blockers.single;
        expect(blocker.fieldKey, field);
        expect(
          blocker.kind,
          field == null
              ? ClearanceBlockerKind.record
              : ClearanceBlockerKind.field,
        );
        expect(blocker.isBlocking, isTrue);
        expect(blocker.message, message);
        expect(blocker.detail, detail);
        expect(blocker.rawCode, code);
      });
    }
  }

  test('two labels marking one field are two items', () {
    expect(
      blockersFor(
        record(<String>[
          'marked:habitat:L1:text_only',
          'marked:habitat:L2:conflict',
        ]),
      ).map((ClearanceBlocker b) => (b.fieldKey, b.message, b.detail)),
      <(String?, String, String?)>[
        ('habitat', 'Habitat is marked for review on Label 1', textOnly),
        ('habitat', 'Habitat is marked for review', conflict),
      ],
    );
  });

  test('a list row names the marked field', () {
    for (final (String code, String summary) in <(String, String)>[
      ('marked:habitat:L1:text_only', 'Habitat is marked for review'),
      ('marked:collectors:L1:conflict', 'Collectors are marked for review'),
      ('mandatory_unresolved:habitat', 'Habitat needs a supported value'),
    ]) {
      expect(reviewIssueSummary(code), summary, reason: code);
    }
  });

  test('the settlement findings read as field notes, never as blockers', () {
    Json note(String severity, String code) => <String, dynamic>{
      'rule_id': 'field_settlement',
      'severity': severity,
      'field_key': 'habitat',
      'reason_code': code,
    };
    for (final (Json finding, String text) in <(Json, String)>[
      (
        note('warning', 'marked:habitat:L1:text_only'),
        'Marked on Label 1: only the readings back this value',
      ),
      (
        note('warning', 'marked:habitat:L1:conflict'),
        'Marked on Label 1: another backed text competes with this value',
      ),
      (
        note('warning', 'marked:habitat:L9:text_only'),
        'Marked: only the readings back this value',
      ),
      (
        note('warning', 'marked:habitat:L1:other'),
        'Marked on Label 1 for review',
      ),
      (
        note('info', 'cleared:habitat:L1'),
        'Confirmed on Label 1 by the image, a source or a person',
      ),
      (
        note('info', 'cleared:habitat:L9'),
        'Confirmed by the image, a source or a person',
      ),
    ]) {
      final Specimen specimen = record(
        const <String>[],
        notes: <Json>[finding],
      );
      expect(blockersFor(specimen), isEmpty, reason: finding['reason_code']);
      final ClearanceBlocker found = fieldNotesFor(specimen).single;
      expect(found.message, text);
      expect(found.fieldKey, 'habitat');
      expect(found.isBlocking, isFalse);
    }
  });

  Future<void> showFields(WidgetTester tester, Specimen specimen) =>
      pumpComponent(
        tester,
        SingleChildScrollView(
          child: WorkbenchFields(
            specimen: specimen,
            anchors: const <String, GlobalKey>{},
            pending: const [],
            onPendingChanged: (_) {},
          ),
        ),
        size: const Size(900, 1600),
      );

  String collectionCount(WidgetTester tester) => tester
      .widget<Text>(find.byKey(const ValueKey('field-group-count:Collection')))
      .data!;

  // The acceptance's case: a supported habitat with
  // marked:habitat:L1:text_only displays as marked and counts as a field
  // review. The rows around it hold the count to the code.
  for (final (List<String> reasons, String count, bool habitat, bool collectors)
      in <(List<String>, String, bool, bool)>[
        (<String>[], '0 review · 0 missing', false, false),
        (
          <String>['marked:habitat:L1:text_only'],
          '1 review · 0 missing',
          true,
          false,
        ),
        (
          <String>['marked:collectors:L1:conflict'],
          '1 review · 0 missing',
          false,
          true,
        ),
        (
          <String>[
            'marked:habitat:L1:text_only',
            'marked:collectors:L1:text_only',
          ],
          '2 review · 0 missing',
          true,
          true,
        ),
        // A code naming a field the record does not hold reviews no field.
        (
          <String>['marked:county:L1:text_only'],
          '0 review · 0 missing',
          false,
          false,
        ),
      ]) {
    testWidgets(
      'the fields with ${reasons.isEmpty ? 'no code' : reasons.join(' and ')}',
      (WidgetTester tester) async {
        await showFields(tester, record(reasons));
        expect(collectionCount(tester), count);
        for (final (String name, bool marked) in <(String, bool)>[
          ('Habitat', habitat),
          ('Collectors', collectors),
        ]) {
          final UiDisclosure row = tester.widget<UiDisclosure>(
            uiDisclosure(name),
          );
          expect(
            row.semanticsLabel!.endsWith('. Review needed'),
            marked,
            reason: row.semanticsLabel,
          );
          expect(row.collapsedIcon, marked ? isNull : UiIcons.check);
          final Finder header = find
              .descendant(
                of: uiDisclosure(name),
                matching: find.byWidgetPredicate((Widget w) => w is Pressable),
              )
              .first;
          await tester.ensureVisible(header);
          await tester.tap(header);
          await tester.pumpAndSettle();
          expect(
            find.descendant(
              of: uiDisclosure(name),
              matching: find.textContaining(
                RegExp('^$name (is|are) marked for review on Label 1\$'),
              ),
            ),
            marked ? findsOneWidget : findsNothing,
          );
        }
        expect(tester.takeException(), isNull);
      },
    );
  }
}
