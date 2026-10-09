import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/part_reasons.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';

import 'field_parts_fixture.dart';

// The review list's sentences for the reason codes a part's review writes
// (wire contract, section 5). No server writes these codes yet: today the list
// shows one generic line for a code it does not know, and this gives the four
// a plain sentence and the field to open. Every other code reads as it did.

Specimen withCodes(List<String> codes, {Specimen? base}) =>
    Specimen(<String, dynamic>{
      ...(base ?? subject105526321()).data,
      'reason_codes': codes,
    });

ClearanceBlocker only(Specimen specimen) {
  final List<ClearanceBlocker> blockers = blockersFor(specimen);
  expect(blockers, hasLength(1));
  return blockers.single;
}

void main() {
  const String generic = 'A specimen check needs review before approval';

  test('a doubt names the part and says why in the writer own words', () {
    final ClearanceBlocker issue = only(
      withCodes(<String>['part_doubt:location/place']),
    );
    expect(issue.message, 'Check named place');
    expect(
      issue.detail,
      'No approved source holds this mountain. A lookup of Mt. McKinley '
      'returns Denali, which is not in Davao.',
    );
    expect(issue.fieldKey, 'precise_location');
    expect(issue.kind, ClearanceBlockerKind.field);
    expect(issue.segment, WorkbenchSegment.fields);
    expect(issue.rawCode, 'part_doubt:location/place');
    expect(
      issue.anchor,
      'precise_location',
      reason: 'Go to scrolls to the row',
    );
  });

  test('a conflict names what differs, and the readings it is between', () {
    final ClearanceBlocker issue = only(
      withCodes(<String>['part_conflict:collectors/1']),
    );
    expect(issue.message, 'Readings differ for collector 1');
    expect(issue.detail, 'F.G. Werner or F.G. Wermer.');
    expect(issue.fieldKey, 'collectors');
  });

  test('a conflict between sources says sources', () {
    final List<Map<String, dynamic>> evidence = <Map<String, dynamic>>[
      for (final Map<String, dynamic> row in partEvidence())
        if (row['evidence_id'] == 'ev-2B-collector')
          <String, dynamic>{...row, 'kind': 'lookup'}
        else
          row,
    ];
    final ClearanceBlocker issue = only(
      Specimen(<String, dynamic>{
        ...subject105526321().data,
        'evidence': evidence,
        'reason_codes': <String>['part_conflict:collectors/1'],
      }),
    );
    expect(issue.message, 'Sources differ for collector 1');
  });

  test('no support says so, with the writer reason behind it', () {
    final List<Map<String, dynamic>> parts = locationParts();
    parts[1]
      ..remove('value')
      ..remove('basis')
      ..['state'] = 'unresolved'
      ..['evidence_ids'] = <String>[]
      ..['evidence_relations'] = <String, String>{}
      ..['review'] = <String, dynamic>{
        'code': 'no_support',
        'reason': 'No source supports an island for this label.',
      };
    final Specimen specimen = Specimen(<String, dynamic>{
      ...subject105526321().data,
      'fields': <Map<String, dynamic>>[
        workspaceField('precise_location', literal: locality, parts: parts),
      ],
      'reason_codes': <String>['part_no_support:location/island'],
    });
    final ClearanceBlocker issue = only(specimen);
    expect(issue.message, 'No source supports island');
    expect(issue.detail, 'No source supports an island for this label.');
    expect(issue.fieldKey, 'precise_location');
  });

  test('a record that has no parts still gets the sentence and the field', () {
    // The reason can arrive before parts do, or from a server whose parts this
    // reader set aside. The sentence needs only the code.
    final Specimen specimen = Specimen(<String, dynamic>{
      'specimen_id': 'no-parts',
      'fields': <Map<String, dynamic>>[
        workspaceField('precise_location', literal: locality),
      ],
      'reason_codes': <String>['part_doubt:location/country'],
    });
    final ClearanceBlocker issue = only(specimen);
    expect(issue.message, 'Check country');
    expect(issue.detail, 'Review the value and its supporting sources.');
    expect(issue.fieldKey, 'precise_location');
  });

  test('parts that did not fit name the value, not a part', () {
    final ClearanceBlocker location = only(
      withCodes(<String>['part_bounds_exceeded:location']),
    );
    expect(location.message, 'Check location');
    expect(
      location.detail,
      'It has more parts than the record can hold, so none were saved. '
      'The value is unchanged.',
    );
    expect(location.fieldKey, 'precise_location');

    // Two fields carry dates, so a reason about the whole value names neither.
    final ClearanceBlocker dates = only(
      withCodes(<String>['part_bounds_exceeded:when']),
    );
    expect(dates.message, 'Check dates');
    expect(dates.fieldKey, isNull);
    expect(dates.kind, ClearanceBlockerKind.record);
  });

  test('a part on a field the record does not hold has no field to open', () {
    final ClearanceBlocker issue = only(
      withCodes(<String>['part_doubt:taxon/accepted']),
    );
    expect(issue.message, 'Check accepted name');
    expect(issue.fieldKey, isNull);
    expect(issue.segment, WorkbenchSegment.fields);
  });

  test('a level the app does not know is shown, not hidden', () {
    final ClearanceBlocker issue = only(
      withCodes(<String>['part_doubt:location/barangay']),
    );
    expect(issue.message, 'Check barangay');
    expect(issue.fieldKey, 'precise_location');
  });

  test('a subject this reader does not know falls to the generic line', () {
    for (final String code in <String>[
      'part_doubt:bogus/x',
      'part_doubt:location/Country',
      'part_doubt:location/verbatim',
      'part_conflict:',
      'part_no_support',
      'part_bounds_exceeded:bogus',
      'part_unheard_of:location/country',
    ]) {
      final ClearanceBlocker issue = only(withCodes(<String>[code]));
      expect(issue.message, generic, reason: code);
      expect(issue.fieldKey, isNull, reason: code);
    }
  });

  test('each reason is listed once, in the order the codes come', () {
    final List<ClearanceBlocker> blockers = blockersFor(
      withCodes(<String>[
        'part_doubt:location/place',
        'part_conflict:collectors/1',
        'part_doubt:location/place',
      ]),
    );
    expect(blockers.map((ClearanceBlocker b) => b.message), <String>[
      'Check named place',
      'Readings differ for collector 1',
    ]);
  });

  test('the sentences obey the writing rules', () {
    final List<String> sentences = <String>[];
    for (final String code in <String>[
      'part_doubt:location/place',
      'part_conflict:collectors/1',
      'part_no_support:location/island',
      'part_bounds_exceeded:location',
    ]) {
      final ClearanceBlocker issue = only(withCodes(<String>[code]));
      sentences
        ..add(issue.message)
        ..addAll(<String>[?issue.detail]);
    }
    expect(sentences, hasLength(8));
    for (final String sentence in sentences) {
      expect(sentence, isNot(contains('—')), reason: sentence);
      expect(sentence, isNot(contains('–')), reason: sentence);
      expect(
        sentence,
        isNot(
          matches(RegExp(r'\b(error|failed|invalid)\b', caseSensitive: false)),
        ),
        reason: sentence,
      );
      expect(sentence, isNot(contains('part_')), reason: 'no internal code');
    }
  });

  test('another code reads exactly as it did', () {
    final ClearanceBlocker issue = only(
      withCodes(<String>['mandatory_unresolved:country']),
    );
    expect(issue.message, 'Country needs a supported value');
    expect(issue.fieldKey, 'country');
  });

  test('the bases the list knows are the four the contract names', () {
    expect(partReasonBases, <String>{
      'part_conflict',
      'part_doubt',
      'part_no_support',
      'part_bounds_exceeded',
    });
  });
}
