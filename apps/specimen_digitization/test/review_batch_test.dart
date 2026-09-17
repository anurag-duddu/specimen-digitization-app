// Pass criterion 7.2: five corrections on one record, one reason, one
// reviewer action.
//
// `reviewBatch` is the fan out path the workbench still takes: one call per
// correction, carrying one reason, one idempotency key prefix, and the
// revision the call before it produced, with the screen moved once on the last
// result rather than five times. These tests hold that behaviour.
//
// The API no longer requires it. `POST /decisions:batch` takes several
// decisions in one call, including several addressed at one record, and
// `tests/test_decisions_batch.py` covers that shape directly. Moving the
// workbench onto it is a separate change in workbench-owned files; until then
// this path is what ships there, so it stays tested as it is.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_digitization/src/workbench.dart';

import 'golden/golden_harness.dart';
import 'widget_test.dart' show TestRepository, fixture;
import 'workbench_harness.dart';
import 'ui_finders.dart';

/// A repository that records every call the batch makes.
class RecordingRepository extends TestRepository {
  final List<String> keys = <String>[];
  final List<Json> sent = <Json>[];
  final List<int> revisionsSeen = <int>[];

  /// The one-based call that throws, or zero for a repository that never
  /// fails.
  int failOnCall = 0;

  /// True for a server that answers without a newer version, which pull
  /// request #42 taught this client to treat as an unconfirmed save.
  bool freezeRevision = false;

  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    keys.add(key);
    sent.add(change);
    revisionsSeen.add(specimen.revision);
    if (keys.length == failOnCall) {
      throw const ApiFailure('The server refused', status: 409);
    }
    return Specimen(<String, dynamic>{
      ...specimen.data,
      'revision': freezeRevision ? specimen.revision : specimen.revision + 1,
    });
  }
}

const CollectionScope scope = CollectionScope(
  organizationId: 'org',
  collectionId: 'insects',
  name: 'Synthetic Insects',
  permissions: <String>['reviewer'],
);

List<Json> corrections(int count) => <Json>[
  for (int i = 0; i < count; i++)
    <String, dynamic>{
      'kind': 'field_correction',
      'target_id': 'field_$i',
      'state': 'unknown',
    },
];

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  group('reviewBatch', () {
    test('sends one call per change, in order, under one reason', () async {
      final RecordingRepository repository = RecordingRepository();
      await repository.reviewBatch(
        scope,
        fixture,
        corrections(5),
        'Nothing on the label supports these fields',
        'review-batch-1',
      );
      expect(repository.sent, hasLength(5));
      expect(repository.sent.map((Json c) => c['reason']).toSet(), <String>{
        'Nothing on the label supports these fields',
      });
      expect(repository.sent.map((Json c) => c['target_id']).toList(), <String>[
        'field_0',
        'field_1',
        'field_2',
        'field_3',
        'field_4',
      ]);
    });

    test('every call shares one idempotency key prefix', () async {
      final RecordingRepository repository = RecordingRepository();
      await repository.reviewBatch(
        scope,
        fixture,
        corrections(3),
        'One reason',
        'review-batch-7',
      );
      expect(repository.keys, <String>[
        'review-batch-7-0',
        'review-batch-7-1',
        'review-batch-7-2',
      ]);
      expect(
        repository.keys.toSet(),
        hasLength(3),
        reason: 'two calls sharing a key would reconcile as one decision',
      );
    });

    test('each call carries the version the one before it produced', () async {
      final RecordingRepository repository = RecordingRepository();
      final ReviewBatchResult result = await repository.reviewBatch(
        scope,
        fixture,
        corrections(3),
        'One reason',
        'review-batch-2',
      );
      expect(repository.revisionsSeen, <int>[
        fixture.revision,
        fixture.revision + 1,
        fixture.revision + 2,
      ]);
      expect(result.specimen.revision, fixture.revision + 3);
      expect(result.saved, 3);
      expect(result.stopped, isFalse);
    });

    // Pull request #42's rule, applied where a batch cannot re-read the
    // screen between its own calls: a correction whose field moved under the
    // reviewer is never sent automatically against a newer revision.
    test('a correction that no longer applies stops the batch', () async {
      final RecordingRepository repository = RecordingRepository();
      final ReviewBatchResult result = await repository.reviewBatch(
        scope,
        fixture,
        corrections(4),
        'One reason',
        'review-batch-5',
        stillApplies: (Specimen current, Json change) =>
            change['target_id'] != 'field_2',
      );
      expect(result.saved, 2);
      expect(result.stopped, isTrue);
      expect(repository.sent, hasLength(2));
      expect(result.specimen.revision, fixture.revision + 2);
    });

    test('a result that is not a newer version is refused', () async {
      final RecordingRepository repository = RecordingRepository()
        ..freezeRevision = true;
      await expectLater(
        repository.reviewBatch(
          scope,
          fixture,
          corrections(3),
          'One reason',
          'review-batch-6',
        ),
        throwsA(
          isA<ReviewBatchFailure>()
              .having((ReviewBatchFailure f) => f.saved, 'saved', 0)
              .having(
                (ReviewBatchFailure f) => f.cause,
                'cause',
                isA<ApiFailure>().having(
                  (ApiFailure e) => e.code,
                  'code',
                  'unconfirmed_save',
                ),
              ),
        ),
      );
    });

    test(
      'a failure part way says how many landed and what they left',
      () async {
        final RecordingRepository repository = RecordingRepository()
          ..failOnCall = 3;
        await expectLater(
          repository.reviewBatch(
            scope,
            fixture,
            corrections(5),
            'One reason',
            'review-batch-3',
          ),
          throwsA(
            isA<ReviewBatchFailure>()
                .having((ReviewBatchFailure f) => f.saved, 'saved', 2)
                .having(
                  (ReviewBatchFailure f) => f.specimen.revision,
                  'record as the server has it',
                  fixture.revision + 2,
                ),
          ),
        );
        expect(
          repository.sent,
          hasLength(3),
          reason: 'the batch stopped at the call that failed',
        );
      },
    );

    test('an empty batch is not a call', () async {
      final RecordingRepository repository = RecordingRepository();
      final ReviewBatchResult result = await repository.reviewBatch(
        scope,
        fixture,
        const <Json>[],
        'One reason',
        'review-batch-4',
      );
      expect(repository.keys, isEmpty);
      expect(result.specimen.revision, fixture.revision);
      expect(result.saved, 0);
    });
  });

  testWidgets('the workbench moves the screen once, on the last result', (
    WidgetTester tester,
  ) async {
    useWindow(tester, largeWindow);
    final List<List<Json>> batches = <List<Json>>[];
    final List<bool Function(Specimen, Json)> guards =
        <bool Function(Specimen, Json)>[];
    int rebuilds = 0;
    final Specimen many = Specimen(<String, dynamic>{
      ...fixture.data,
      'fields': <Json>[
        for (int i = 0; i < 5; i++)
          <String, dynamic>{
            'field_key': 'field_$i',
            'display_name': 'Field $i',
            'required': true,
            'state': 'unknown',
            'literal_value': null,
          },
      ],
      'validation_findings': const <Json>[],
    });

    await tester.pumpWidget(
      workbenchHost(
        Builder(
          builder: (BuildContext context) {
            rebuilds++;
            return ReviewWorkbench(
              specimen: many,
              onChange: (Json change) async => true,
              onChangeBatch:
                  (
                    List<Json> changes,
                    String reason,
                    bool Function(Specimen, Json) stillApplies,
                  ) async {
                    batches.add(changes);
                    // The workbench has to hand the batch a way to ask, or
                    // the guarantee the one at a time path gets for free is
                    // lost the moment the batch path is used.
                    guards.add(stillApplies);
                    return changes.length;
                  },
              onRetry: (String reason) async {},
              onRefresh: () {},
            );
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Fields'));
    await tester.pumpAndSettle();
    for (int i = 0; i < 5; i++) {
      await scrollAndTap(
        tester,
        uiIconButton(RegExp(r'^Edit as written')).at(i),
      );
      await tester.tap(find.text('Keep this correction'));
      await tester.pumpAndSettle();
    }
    final int beforeSave = rebuilds;

    await tester.tap(find.text('Save 5 pending changes').last);
    await tester.pumpAndSettle();
    await tester.enterText(
      uiField('Reason'),
      'Nothing on the label supports these fields',
    );
    await tester.pumpAndSettle();
    await tester.tap(
      find.descendant(
        of: find.byType(ReasonForm),
        matching: uiButton('Save 5 pending changes'),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      batches,
      hasLength(1),
      reason: 'five corrections are one reviewer action, not five',
    );
    expect(batches.single, hasLength(5));
    expect(batches.single.map((Json c) => c['reason']).toSet(), <String>{
      'Nothing on the label supports these fields',
    });
    expect(find.textContaining('pending change'), findsNothing);
    expect(guards, hasLength(1));
    expect(
      guards.single(many, batches.single.first),
      isTrue,
      reason: 'a draft against the record as it stands still applies',
    );
    expect(
      guards.single(
        Specimen(<String, dynamic>{
          ...many.data,
          'fields': <Json>[
            for (final Json field in many.fields)
              if (field['field_key'] == 'field_0')
                <String, dynamic>{...field, 'literal_value': 'moved'}
              else
                field,
          ],
        }),
        batches.single.first,
      ),
      isFalse,
      reason: 'a draft whose field moved under the reviewer does not apply',
    );
    expect(
      rebuilds - beforeSave,
      lessThanOrEqualTo(1),
      reason: 'the host was asked to rebuild once, not once per correction',
    );
  });

  // Pass criterion 7.3. The server now accepts a decision across records
  // (`POST /decisions:batch`), so the queue offers one, and the half of the
  // criterion that used to be held as an absence is now held as a capability:
  // the affordance exists, it is bounded by what the server actually takes,
  // and nothing in the queue implies more than that.
  //
  // What lives here is only the part that keeps this file honest: `reviewBatch`
  // above is still one record and several corrections, which is criterion 7.2,
  // and it is a different path from the queue's. The selection model, the bar,
  // the confirmation and the per record outcomes are covered in
  // `test/selection_model_test.dart`, `test/widgets/selection_bar_test.dart`
  // and `test/screens/queue_bulk_test.dart`.
  group('the queue offers the bulk actions the server permits', () {
    testWidgets('a selection model exists, over the records on screen', (
      WidgetTester tester,
    ) async {
      await pumpGoldenApp(
        tester,
        window: const Size(1180, 1400),
        brightness: Brightness.light,
        location: goldenQueueLocation,
        repository: GoldenQueueRepository(goldenQueue(6)),
      );
      expect(
        find.descendant(
          of: find.byType(SelectableRow),
          matching: find.byType(UiCheckbox),
        ),
        findsNWidgets(6),
      );
      expect(
        find.textContaining('Select all matching'),
        findsNothing,
        reason:
            'the list API answers a page, never a total, so no control '
            'may claim the whole filter',
      );
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('and offers nothing the wire cannot take across records', (
      WidgetTester tester,
    ) async {
      await pumpGoldenApp(
        tester,
        window: const Size(1180, 1400),
        brightness: Brightness.light,
        location: goldenQueueLocation,
        repository: GoldenQueueRepository(goldenQueue(6)),
      );
      await tester.tap(
        find
            .descendant(
              of: find.byType(SelectableRow),
              matching: find.byType(UiCheckbox),
            )
            .first,
      );
      await tester.pumpAndSettle();
      expect(find.text('1 record selected'), findsOneWidget);
      // The two record level decisions, and only those. A field correction or
      // a transcription names a target inside one record, and there is no
      // sense in which six records share it.
      expect(find.text('Approve'), findsOneWidget);
      expect(find.text('Confirm coverage'), findsOneWidget);
      for (final String absent in <String>[
        'Correct field',
        'Adjudicate readings',
        'Delete',
        'Remove',
      ]) {
        expect(
          find.textContaining(absent),
          findsNothing,
          reason:
              'the queue offers "$absent" across records, which the '
              'decisions endpoint does not take',
        );
      }
      await tester.pumpWidget(const SizedBox());
    });
  });
}
