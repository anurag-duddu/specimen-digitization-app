// A cleared record whose optional fields are open (plan WP K1): an optional
// field's doubt holds no record, so the server publishes it in
// `open_reason_codes`, not `reason_codes`. The field still needs attention
// exactly as before: the row reads "Review needed" with its plain reason, never
// the settled checkmark, and counts in its group's header. The record-level
// blocker list reads `reason_codes` alone.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import '../widgets/harness.dart';

/// Label L1; a supported habitat and an unresolved collectors field. The
/// codes go to `reason_codes` (held) or `open_reason_codes` (cleared).
Specimen record(List<String> codes, {required bool cleared}) =>
    Specimen(<String, dynamic>{
      'specimen_id': 'open-optional',
      'revision': 3,
      'disposition': cleared ? 'cleared' : 'needs_human_review',
      'regions': <Json>[
        <String, dynamic>{'region_id': 'L1'},
      ],
      'fields': <Json>[
        <String, dynamic>{
          'field_key': 'habitat',
          'state': 'supported',
          'literal_value': 'Synthetic grassland',
        },
        <String, dynamic>{'field_key': 'collectors', 'state': 'unresolved'},
      ],
      'reason_codes': cleared ? <String>[] : codes,
      'open_reason_codes': cleared ? codes : <String>[],
      'validation_findings': <Json>[
        // The settlement's own warning, as the run keeps it.
        <String, dynamic>{
          'rule_id': 'field_settlement',
          'severity': 'warning',
          'field_key': 'habitat',
          'reason_code': 'marked:habitat:L1:text_only',
        },
      ],
    });

const List<String> codes = <String>[
  'marked:habitat:L1:text_only',
  'mandatory_unresolved:collectors',
];

void main() {
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

  Future<void> expectNeedsAttention(
    WidgetTester tester,
    String name,
    Pattern reason,
  ) async {
    final UiDisclosure row = tester.widget<UiDisclosure>(uiDisclosure(name));
    expect(
      row.semanticsLabel!.endsWith('. Review needed'),
      isTrue,
      reason: row.semanticsLabel,
    );
    expect(row.collapsedIcon, isNull, reason: name);
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
        matching: find.textContaining(reason),
      ),
      findsOneWidget,
      reason: name,
    );
  }

  for (final bool cleared in <bool>[true, false]) {
    testWidgets(
      'a ${cleared ? 'cleared' : 'held'} record shows its marked and open '
      'fields as needing attention',
      (WidgetTester tester) async {
        await showFields(tester, record(codes, cleared: cleared));
        expect(collectionCount(tester), '2 review · 1 missing');
        await expectNeedsAttention(
          tester,
          'Habitat',
          RegExp(r'^Habitat is marked for review on Label 1\.$'),
        );
        await expectNeedsAttention(
          tester,
          'Collectors',
          'Collectors need a supported value',
        );
        expect(tester.takeException(), isNull);
      },
    );
  }

  test('the record-level blockers read only the reasons that hold it', () {
    expect(blockersFor(record(codes, cleared: true)), isEmpty);
    expect(
      blockersFor(
        record(codes, cleared: false),
      ).map((ClearanceBlocker b) => b.rawCode),
      containsAll(codes),
    );
  });

  test('a mark with a reason this client does not know still needs attention '
      'with generic words', () {
    final List<ClearanceBlocker> attention = fieldAttentionFor(
      record(<String>['marked:habitat:L1:a_new_check'], cleared: true),
    );
    expect(attention, hasLength(1));
    expect(attention.single.fieldKey, 'habitat');
    expect(
      attention.single.message,
      'Habitat is marked for review on Label 1.',
    );
    expect(
      attention.single.detail,
      'Review the value and its supporting sources.',
    );
  });

  test('a date check names each date field the record has', () {
    final Specimen specimen = Specimen(<String, dynamic>{
      ...record(const <String>['date_order'], cleared: true).data,
      'fields': <Json>[
        <String, dynamic>{
          'field_key': 'date_visited_from',
          'state': 'supported',
          'literal_value': '1946-09-06',
        },
        <String, dynamic>{
          'field_key': 'date_identified',
          'state': 'supported',
          'literal_value': '1941-06',
        },
      ],
    });
    expect(
      fieldAttentionFor(specimen).map((ClearanceBlocker b) => b.fieldKey),
      <String>['date_visited_from', 'date_identified'],
    );
  });

  test('the run carries the codes when the summary does not', () {
    final Specimen specimen = Specimen(<String, dynamic>{
      'run': <String, dynamic>{
        'open_reasons': <String>['taxonomy_unresolved'],
      },
    });
    expect(specimen.openReasonCodes, <String>['taxonomy_unresolved']);
  });

  // Codex round 2 on #455: L1 settles the catalogue number; L2 is unresolved
  // and feeds only the optional country. The server cleared the record and
  // put L2's doubt in open_reason_codes, with each field it reaches.
  Specimen secondLabelOpen({required bool held}) {
    final List<String> codes = <String>[
      'unresolved_transcription:L2',
      'label_unsettled:country',
    ];
    return Specimen(<String, dynamic>{
      'specimen_id': 'second-label',
      'revision': 4,
      'disposition': held ? 'needs_human_review' : 'cleared',
      'regions': <Json>[
        <String, dynamic>{'region_id': 'L1'},
        <String, dynamic>{'region_id': 'L2'},
      ],
      'transcriptions': <Json>[
        <String, dynamic>{'region_id': 'L1', 'resolved': true},
        <String, dynamic>{'region_id': 'L2', 'resolved': false},
      ],
      'fields': <Json>[
        <String, dynamic>{
          'field_key': 'fmnh_ins_number',
          'state': 'supported',
          'literal_value': 'FMNH-INS 0010001',
        },
        <String, dynamic>{
          'field_key': 'country',
          'state': 'supported',
          'literal_value': 'United States',
        },
      ],
      'reason_codes': held
          ? <String>['unresolved_transcription:L2']
          : <String>[],
      'open_reason_codes': held ? <String>[] : codes,
      'validation_findings': <Json>[
        <String, dynamic>{
          'rule_id': 'unresolved_transcription:L2',
          'severity': 'hard',
          'reason_code': 'unresolved_transcription:L2',
        },
      ],
    });
  }

  test('a cleared record lists no blocker for an open label doubt', () {
    expect(blockersFor(secondLabelOpen(held: false)), isEmpty);
    expect(
      fieldAttentionFor(
        secondLabelOpen(held: false),
      ).map((ClearanceBlocker b) => b.fieldKey),
      <String>['country'],
    );
  });

  test('a held record still lists the label as blocking', () {
    expect(
      blockersFor(
        secondLabelOpen(held: true),
      ).map((ClearanceBlocker b) => b.regionId),
      contains('L2'),
    );
  });

  testWidgets('the field an open label doubt reaches needs attention', (
    WidgetTester tester,
  ) async {
    await showFields(tester, secondLabelOpen(held: false));
    await expectNeedsAttention(
      tester,
      'Country',
      'Country comes from a label that needs checking',
    );
    expect(tester.takeException(), isNull);
  });
}
