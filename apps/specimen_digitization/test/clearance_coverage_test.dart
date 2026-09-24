// The label coverage check in what blocks clearance (UI.md T2.4; G15).
//
// The thread explains a blocker the record states, in what each failed check
// measured, and never adds one the record does not have.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';
import 'package:specimen_digitization/src/thread/thread.dart';

const String coverageCode = 'label_coverage_unconfirmed';

/// A record at the review stop, publishing [reasons] the way `workspace()`
/// does: in `reason_codes`, and again as a hard finding each.
Specimen record({List<String> reasons = const <String>[coverageCode]}) =>
    Specimen(<String, dynamic>{
      'specimen_id': 'specimen-coverage',
      'revision': 5,
      'reason_codes': reasons,
      'validation_findings': <Json>[
        for (final String reason in reasons)
          <String, dynamic>{
            'rule_id': reason,
            'severity': 'hard',
            'outcome': 'fail',
            'reason_code': reason,
          },
      ],
    });

/// The fixture's thread with its coverage check replaced by [checks].
SpecimenThread threadWith(List<Json> checks, {String status = 'failed'}) {
  final Json json =
      jsonDecode(
            File(
              'test/fixtures/thread-two-label-slide.json',
            ).readAsStringSync(),
          )
          as Json;
  (json['coverage_check'] as Json)
    ..['status'] = status
    ..['checks'] = checks;
  return SpecimenThread.fromJson(json);
}

Json regionCount({
  required int found,
  int? min = 1,
  int? max = 2,
  List<String> reasons = const <String>['label_region_count_out_of_range'],
}) => <String, dynamic>{
  'name': 'region_count',
  'passed': reasons.isEmpty,
  'detail': <String, dynamic>{
    'found': found,
    'min': ?min,
    'max': ?max,
    'reason_codes': reasons,
  },
};

Json fullImage({required int counted, required int outside}) =>
    <String, dynamic>{
      'name': 'full_image',
      'passed': outside == 0,
      'detail': <String, dynamic>{
        'counted': counted,
        'outside': outside,
        'threshold': 0.5,
        'min_inside_fraction': 0.9,
        'reason_codes': <String>[
          if (outside > 0) 'cross_check_detection_outside_labels',
        ],
      },
    };

/// The blockers that speak of label coverage.
List<ClearanceBlocker> coverage(List<ClearanceBlocker> blockers) =>
    <ClearanceBlocker>[
      for (final ClearanceBlocker b in blockers)
        if (b.message.toLowerCase().contains('coverage')) b,
    ];

void main() {
  test('a failed check is one blocker saying what each check measured', () {
    final List<ClearanceBlocker> found = coverage(
      blockersFor(
        record(),
        thread: threadWith(<Json>[
          regionCount(found: 3),
          fullImage(counted: 4, outside: 1),
        ]),
      ),
    );
    expect(found, hasLength(1), reason: 'the check is stated once');
    expect(found.single.message, 'Label coverage not confirmed');
    expect(
      found.single.detail,
      'Found 3 label regions; the profile allows 1 to 2. '
      '1 of 4 label-like detections lies outside the label regions',
    );
    expect(found.single.segment, WorkbenchSegment.readings);
  });

  test('no label regions is said once, not as a count out of range', () {
    final List<ClearanceBlocker> found = coverage(
      blockersFor(
        record(),
        thread: threadWith(<Json>[
          regionCount(
            found: 0,
            reasons: <String>[
              'zero_regions',
              'label_region_count_out_of_range',
            ],
          ),
          fullImage(counted: 0, outside: 0),
        ]),
      ),
    );
    expect(found.single.detail, 'Found no label regions');
  });

  test('a region outside the photograph says so', () {
    final List<ClearanceBlocker> found = coverage(
      blockersFor(
        record(),
        thread: threadWith(<Json>[
          regionCount(found: 2, reasons: <String>['region_out_of_bounds']),
          fullImage(counted: 2, outside: 0),
        ]),
      ),
    );
    expect(found.single.detail, 'A label region lies outside the photograph');
  });

  test('a range the check does not record is not guessed', () {
    final List<ClearanceBlocker> found = coverage(
      blockersFor(
        record(),
        thread: threadWith(<Json>[
          regionCount(found: 3, min: null, max: null),
          fullImage(counted: 3, outside: 0),
        ]),
      ),
    );
    expect(found.single.detail, 'Found 3 label regions');
  });

  test('several detections outside take the plural', () {
    final List<ClearanceBlocker> found = coverage(
      blockersFor(
        record(),
        thread: threadWith(<Json>[
          regionCount(found: 2, reasons: const <String>[]),
          fullImage(counted: 5, outside: 2),
        ]),
      ),
    );
    expect(
      found.single.detail,
      '2 of 5 label-like detections lie outside the label regions',
    );
  });

  test('a check this client does not know is named', () {
    final List<ClearanceBlocker> found = coverage(
      blockersFor(
        record(),
        thread: threadWith(<Json>[
          <String, dynamic>{
            'name': 'edge_margin',
            'passed': false,
            'detail': <String, dynamic>{},
          },
        ]),
      ),
    );
    expect(found.single.detail, 'Failed: edge margin');
  });

  test('the thread never adds a blocker the record does not state', () {
    final List<ClearanceBlocker> found = coverage(
      blockersFor(
        record(reasons: const <String>[]),
        thread: threadWith(<Json>[regionCount(found: 3)]),
      ),
    );
    expect(
      found,
      isEmpty,
      reason: 'a reviewer confirmed coverage after the run',
    );
  });

  test('a passed check leaves the record to speak for itself', () {
    final List<ClearanceBlocker> found = coverage(
      blockersFor(
        record(),
        thread: threadWith(<Json>[
          regionCount(found: 2, reasons: const <String>[]),
        ], status: 'passed'),
      ),
    );
    expect(found.single.message, 'Label coverage not confirmed');
    expect(found.single.detail, isNot(contains('Found')));
  });

  test('without the thread the reason still reads in words', () {
    final List<ClearanceBlocker> found = coverage(blockersFor(record()));
    expect(found, hasLength(1));
    expect(found.single.message, 'Label coverage not confirmed');
  });
}
