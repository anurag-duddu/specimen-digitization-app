import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/screens/workbench/workbench_layout.dart';

import 'widgets/harness.dart';

const String firstLabel = '3d50f205-7885-5be3-9c15-6d31ac324947';
const String secondLabel = '7fb0fadb-9e9e-4941-92af-70fd1e197e9d';

Specimen record({
  List<Json> findings = const <Json>[],
  List<String> reasons = const <String>[],
  List<Json> transcriptions = const <Json>[],
  String? processingBlocker,
}) => Specimen(<String, dynamic>{
  'specimen_id': 'review-issue-fixture',
  'revision': 1,
  'disposition': 'needs_human_review',
  'regions': const <Json>[
    <String, dynamic>{'region_id': firstLabel},
    <String, dynamic>{'region_id': secondLabel},
  ],
  'fields': const <Json>[
    <String, dynamic>{'field_key': 'country', 'state': 'unknown'},
    <String, dynamic>{'field_key': 'collectors', 'state': 'unknown'},
    <String, dynamic>{'field_key': 'fmnh_ins_number', 'state': 'unknown'},
    <String, dynamic>{'field_key': 'taxon', 'state': 'unknown'},
    <String, dynamic>{'field_key': 'elevation_from_m', 'state': 'unknown'},
  ],
  'validation_findings': findings,
  'reason_codes': reasons,
  'transcriptions': transcriptions,
  'run': <String, dynamic>{'blocker': processingBlocker},
});

Json finding(String code, {String? field, String? message}) =>
    <String, dynamic>{
      'reason_code': code,
      'rule_id': code,
      'severity': 'hard',
      'outcome': 'fail',
      'field_key': ?field,
      'message': ?message,
    };

void main() {
  test(
    'run reasons attach to actual fields with plain review instructions',
    () {
      final List<ClearanceBlocker> issues = blockersFor(
        record(
          reasons: <String>[
            'mandatory_unresolved:country',
            'mandatory_evidence_unresolved:collectors',
          ],
        ),
      );

      expect(issues, hasLength(2));
      expect(issues[0].fieldKey, 'country');
      expect(issues[0].message, 'Country needs a supported value');
      expect(issues[1].fieldKey, 'collectors');
      expect(issues[1].message, 'Collectors need supporting evidence');
      expect(
        issues.every(
          (ClearanceBlocker issue) =>
              issue.kind == ClearanceBlockerKind.field &&
              issue.segment == WorkbenchSegment.fields,
        ),
        isTrue,
      );
      expect(issues[0].rawCode, 'mandatory_unresolved:country');
    },
  );

  test(
    'duplicate wire findings and reasons preserve distinct field issues',
    () {
      final List<ClearanceBlocker> issues = blockersFor(
        record(
          findings: <Json>[
            finding('mandatory_unresolved', field: 'country'),
            finding('mandatory_unresolved:country'),
            finding('mandatory_unresolved:collectors'),
            finding('mandatory_evidence_unresolved:country'),
          ],
          reasons: <String>[
            'mandatory_unresolved:country',
            'mandatory_unresolved:country',
            'mandatory_unresolved:collectors',
            'mandatory_evidence_unresolved:country',
          ],
        ),
      );

      expect(issues, hasLength(3));
      expect(issues.map((ClearanceBlocker issue) => issue.fieldKey), <String>[
        'country',
        'collectors',
        'country',
      ]);
    },
  );

  test('one unresolved label appears once across every published form', () {
    final List<ClearanceBlocker> issues = blockersFor(
      record(
        transcriptions: const <Json>[
          <String, dynamic>{
            'region_id': firstLabel,
            'resolved': false,
            'alternatives': <String>['A', 'B'],
          },
        ],
        findings: <Json>[
          finding('unresolved_transcription:$firstLabel'),
          finding('unresolved_transcription:$secondLabel'),
        ],
        reasons: <String>[
          'unresolved_transcription:$firstLabel',
          'unresolved_transcription:$secondLabel',
        ],
      ),
    );

    expect(issues, hasLength(2));
    expect(issues[0].message, 'Two readings differ for Label 1');
    expect(issues[1].message, 'Transcription not resolved for Label 2');
    expect(issues.map((ClearanceBlocker issue) => issue.regionId), <String>[
      firstLabel,
      secondLabel,
    ]);
    expect(
      issues.every(
        (ClearanceBlocker issue) =>
            issue.kind == ClearanceBlockerKind.label &&
            issue.segment == WorkbenchSegment.readings,
      ),
      isTrue,
    );
    expect(
      issues.any(
        (ClearanceBlocker issue) =>
            issue.message.contains(firstLabel) ||
            issue.message.contains(secondLabel),
      ),
      isFalse,
    );
  });

  test(
    'unmatched or future reason targets remain blocking without fake routing',
    () {
      final List<ClearanceBlocker> issues = blockersFor(
        record(
          reasons: const <String>[
            'mandatory_unresolved:future_field',
            'mandatory_unresolved:province_state',
            'unresolved_transcription:missing-label',
          ],
        ),
      );

      expect(issues, hasLength(3));
      expect(
        issues.every((ClearanceBlocker issue) => !issue.isTargeted),
        isTrue,
      );
      expect(
        issues.every(
          (ClearanceBlocker issue) =>
              issue.message == 'A specimen check needs review before approval',
        ),
        isTrue,
      );
      expect(issues.map((ClearanceBlocker issue) => issue.rawCode), <String>[
        'mandatory_unresolved:future_field',
        'mandatory_unresolved:province_state',
        'unresolved_transcription:missing-label',
      ]);
    },
  );

  test(
    'generic approval requirement is the final action in either wire list',
    () {
      final Specimen specimen = record(
        findings: <Json>[
          finding('human_approval_required'),
          finding('mandatory_unresolved:country'),
        ],
        reasons: const <String>[
          'human_approval_required',
          'mandatory_unresolved:country',
        ],
      );

      expect(blockersFor(specimen), hasLength(1));
      expect(blockersFor(specimen).single.fieldKey, 'country');
      expect(specimen.disposition, 'needs_human_review');
    },
  );

  test(
    'policy and worker problems identify operator work, not field edits',
    () {
      final List<ClearanceBlocker> issues = blockersFor(
        record(
          findings: <Json>[finding('institutional_policy_unapproved')],
          reasons: const <String>[
            'institutional_policy_unapproved',
            'worker_readiness_not_verified',
          ],
          processingBlocker: 'worker_readiness_not_verified',
        ),
      );

      expect(issues, hasLength(2));
      expect(
        issues.every((ClearanceBlocker issue) => issue.isOperational),
        isTrue,
      );
      expect(
        issues.every((ClearanceBlocker issue) => !issue.isTargeted),
        isTrue,
      );
      expect(
        issues[0].message,
        'An administrator must approve the collection policy',
      );
      expect(
        issues[1].message,
        'An operator must check that processing is ready',
      );
    },
  );

  test('unknown processing issues are retained and safely described', () {
    const String code = 'future_worker_failure:$firstLabel';
    final List<ClearanceBlocker> issues = blockersFor(
      record(
        findings: <Json>[finding(code)],
        reasons: const <String>[code],
        processingBlocker: code,
      ),
    );

    expect(issues, hasLength(1));
    expect(issues.single.isOperational, isTrue);
    expect(issues.single.rawCode, code);
    expect(
      issues.single.message,
      'Processing needs an operator check before it can continue',
    );
    expect(issues.single.detail, isNot(contains(code)));
  });

  test('unknown codes retain different structured field targets', () {
    final List<ClearanceBlocker> issues = blockersFor(
      record(
        findings: <Json>[
          finding(
            'source_conflict',
            field: 'country',
            message: 'Country needs review',
          ),
          finding(
            'source_conflict',
            field: 'collectors',
            message: 'Collectors need review',
          ),
        ],
        reasons: const <String>['source_conflict'],
      ),
    );

    expect(issues, hasLength(2));
    expect(issues[0].fieldKey, 'country');
    expect(issues[1].fieldKey, 'collectors');
    expect(issues[0].message, 'Country needs review');
    expect(issues[1].message, 'Collectors need review');
  });

  test('unknown suffixes on one field remain separate substantive issues', () {
    final List<ClearanceBlocker> issues = blockersFor(
      record(
        findings: <Json>[
          finding('future_check:first', field: 'country'),
          finding('future_check:second', field: 'country'),
        ],
      ),
    );

    expect(issues, hasLength(2));
    expect(issues.map((ClearanceBlocker issue) => issue.rawCode), <String>[
      'future_check:first',
      'future_check:second',
    ]);
  });

  test('machine payloads copied into finding messages stay in diagnostics', () {
    final List<ClearanceBlocker> issues = blockersFor(
      record(
        findings: <Json>[
          finding('future_validation', field: 'country', message: firstLabel),
          finding('future_validation_two', message: '{"field_key":"country"}'),
        ],
      ),
    );

    expect(issues, hasLength(2));
    expect(issues[0].message, 'Country needs review');
    expect(issues[1].message, 'A specimen check needs review before approval');
    expect(issues[0].diagnosticRuleId, 'future_validation');
  });

  group('field research', () {
    const Set<String> genericMessages = <String>{
      'A specimen check needs review before approval',
      'Processing needs an operator check before it can continue',
      'This field needs review',
    };

    test('an outage names each field that was not checked, with a retry', () {
      final List<ClearanceBlocker> issues = blockersFor(
        record(
          reasons: const <String>[
            'lookup_operational_failure:country',
            'field_research_model_error:taxon',
            'field_research_timeout:collectors',
          ],
          processingBlocker: 'lookup_operational_failure',
        ),
      );

      expect(issues.map((ClearanceBlocker issue) => issue.message), <String>[
        'Country was not checked because an approved source could not be '
            'reached',
        'Taxon was not checked because the model gave no usable answer',
        'Collectors were not checked because field research ran out of time',
        'An operator must restore the source lookup service',
      ]);
      expect(
        issues.take(3).map((ClearanceBlocker issue) => issue.detail),
        everyElement('Retry processing to check this field again.'),
      );
      expect(
        issues.every((ClearanceBlocker issue) => issue.isOperational),
        isTrue,
      );
      expect(
        issues.every((ClearanceBlocker issue) => !issue.isTargeted),
        isTrue,
      );
      expect(issues.first.rawCode, 'lookup_operational_failure:country');
    });

    test('a stopped run says what stopped it and offers a retry', () {
      for (final (String code, String message) in <(String, String)>[
        (
          'field_research_model_error',
          'Field research stopped because the model gave no usable answer',
        ),
        (
          'field_research_timeout',
          'Field research ran out of time before every field was checked',
        ),
      ]) {
        final ClearanceBlocker issue = blockersFor(
          record(processingBlocker: code),
        ).single;
        expect(issue.message, message, reason: code);
        expect(
          issue.detail,
          'Retry processing to check the remaining fields.',
          reason: code,
        );
        expect(issue.isOperational, isTrue, reason: code);
      }
    });

    test('an outage on a field this record does not name stays run-wide', () {
      final ClearanceBlocker issue = blockersFor(
        record(reasons: const <String>['field_research_timeout:future_field']),
      ).single;
      expect(
        issue.message,
        'Field research ran out of time before every field was checked',
      );
      expect(issue.message, isNot(contains('This field')));
      expect(issue.isOperational, isTrue);
    });

    test('a configuration stop names who can clear it', () {
      for (final (String code, String message) in <(String, String)>[
        (
          'field_research_price_unavailable',
          'An administrator must add a price for the field research model',
        ),
        (
          'field_research_unconfigured',
          'An operator must finish setting up field research',
        ),
      ]) {
        final ClearanceBlocker issue = blockersFor(
          record(processingBlocker: code),
        ).single;
        expect(issue.message, message, reason: code);
        expect(issue.isOperational, isTrue, reason: code);
      }
    });

    test('review reasons go to the field or label they are about', () {
      final List<ClearanceBlocker> issues = blockersFor(
        record(
          reasons: const <String>[
            'raw_reading_grounding_unproved:taxon',
            'preserved_human_decision:collectors',
            'independent_observations_missing:$firstLabel',
            'raw_provenance_missing:$secondLabel',
          ],
        ),
      );

      expect(issues.map((ClearanceBlocker issue) => issue.message), <String>[
        'Taxon cannot be traced to the label readings',
        'Collectors have an earlier review decision to confirm',
        'Label 1 needs two independent readings',
        'Label 2 has a reading with no saved evidence file',
      ]);
      expect(issues.map((ClearanceBlocker issue) => issue.fieldKey), <String?>[
        'taxon',
        'collectors',
        null,
        null,
      ]);
      expect(issues.map((ClearanceBlocker issue) => issue.regionId), <String?>[
        null,
        null,
        firstLabel,
        secondLabel,
      ]);
      expect(issues.map((ClearanceBlocker issue) => issue.kind), <Object>[
        ClearanceBlockerKind.field,
        ClearanceBlockerKind.field,
        ClearanceBlockerKind.label,
        ClearanceBlockerKind.label,
      ]);
      expect(issues[2].segment, WorkbenchSegment.readings);
      expect(
        issues[2].detail,
        'Check the label against its readings before approving the specimen.',
      );
      expect(
        issues.any((ClearanceBlocker issue) => issue.isOperational),
        isFalse,
      );
    });

    test('a label reason for a label this record lacks is not routed', () {
      final ClearanceBlocker issue = blockersFor(
        record(
          reasons: const <String>[
            'independent_observations_missing:missing-label',
          ],
        ),
      ).single;
      expect(issue.message, 'A label needs two independent readings');
      expect(issue.isTargeted, isFalse);
    });

    test('an unconfirmed identifier goes to the identifier field', () {
      final Specimen specimen = Specimen(<String, dynamic>{
        ...record(
          reasons: const <String>['identified_by_irn_identity_unproved'],
        ).data,
        'fields': const <Json>[
          <String, dynamic>{
            'field_key': 'identified_by_irn',
            'state': 'unknown',
          },
        ],
      });
      final ClearanceBlocker issue = blockersFor(specimen).single;
      expect(
        issue.message,
        'The identifier needs a confirmed EMu person record',
      );
      expect(issue.fieldKey, 'identified_by_irn');
      expect(issue.kind, ClearanceBlockerKind.field);
    });

    test('no field research code falls back to a generic sentence', () {
      // The run blockers field research raises, and every reason it records.
      const List<String> blockerCodes = <String>[
        'field_research_model_error',
        'field_research_timeout',
        'field_research_price_unavailable',
        'field_research_unconfigured',
      ];
      const List<String> reasonCodes = <String>[
        ...blockerCodes,
        'field_research_model_error:taxon',
        'field_research_timeout:country',
        'raw_reading_grounding_unproved:taxon',
        'independent_observations_missing:$firstLabel',
        'raw_provenance_missing:$firstLabel',
        'identified_by_irn_identity_unproved',
        'preserved_human_decision:country',
      ];
      for (final (String code, List<ClearanceBlocker> issues)
          in <(String, List<ClearanceBlocker>)>[
            for (final String code in reasonCodes)
              (code, blockersFor(record(reasons: <String>[code]))),
            for (final String code in blockerCodes)
              (code, blockersFor(record(processingBlocker: code))),
          ]) {
        expect(issues, hasLength(1), reason: code);
        for (final ClearanceBlocker issue in issues) {
          expect(issue.message, isNot(isIn(genericMessages)), reason: code);
          expect(issue.message, isNot(contains('_')), reason: code);
          expect(issue.message, isNot(contains(firstLabel)), reason: code);
          expect(issue.detail, isNotNull, reason: code);
        }
      }
    });

    testWidgets('processing details name the stop in plain words', (
      WidgetTester tester,
    ) async {
      await pumpComponent(
        tester,
        ProcessingDetail(
          specimen: record(processingBlocker: 'field_research_timeout'),
          canOperate: false,
          busy: false,
          onAction: (_) async {},
        ),
      );

      expect(
        find.text('Blocked: Field research ran out of time'),
        findsOneWidget,
      );
      expect(find.textContaining('field_research'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets(
    'transient status feedback does not repeat internal review issues',
    (WidgetTester tester) async {
      final Specimen specimen = record(
        reasons: const <String>['mandatory_unresolved:country'],
        processingBlocker: 'future_worker_failure:$firstLabel',
      );
      await pumpComponent(
        tester,
        WorkbenchStatusStrip(
          specimen: specimen,
          blockers: blockersFor(specimen),
          pending: const <PendingFieldChange>[],
          onGoToBlocker: (_) =>
              fail('Reading status feedback must not navigate'),
        ),
      );

      expect(find.textContaining('mandatory_unresolved'), findsNothing);
      expect(find.textContaining(firstLabel), findsNothing);
      expect(find.text('Country needs a supported value'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
