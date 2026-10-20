// The cost report as the client reads it (`lib/src/costs.dart`): the wire
// contract, the collection tree, the month list and who may ask.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/costs.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/vocabulary.dart';

import 'cost_fixtures.dart';

CostCollection collection(String id, {String? parent}) => CostCollection(
  id: id,
  name: 'Collection $id',
  parentId: parent,
  own: CostAmounts.none,
  total: CostAmounts.none,
  limit: null,
);

void main() {
  group('the report', () {
    test('reads every field of the contract', () {
      final CostReport report = CostReport.fromWire(costWire(thisMonth));

      expect(report.organizationId, costOrganization);
      expect(report.fromMonth, thisMonth);
      expect(report.toMonth, thisMonth);
      expect(report.updatedAt, DateTime.utc(2026, 10, 20, 15, 4, 5));
      expect(report.totals.costMicros, 12345678);
      expect(report.totals.heldMicros, 500000);
      expect(report.totals.listCostMicros, 15000000);
      expect(report.totals.entries, 1234);
      expect(report.organizationLimit!.monthlyMicros, 50000000);
      expect(report.organizationLimit!.month, thisMonth);
      expect(report.organizationLimit!.spentMicros, 12345678);
      expect(report.organizationLimit!.remainingMicros, 37654322);
      expect(report.collections.map((CostCollection c) => c.name), <String>[
        'Insects',
        'Beetles',
        'Plants',
        'Microscopic slides',
      ]);
      final CostCollection insects = report.collections.first;
      expect(insects.own.costMicros, 4200000);
      expect(insects.total.costMicros, 7100000);
      expect(insects.total.heldMicros, 100000);
      expect(insects.total.listCostMicros, 8000000);
      expect(insects.limit!.remainingMicros, 2900000);
      expect(report.collections[1].parentId, 'col-insects');
      expect(report.collections[1].limit, isNull);
      expect(report.months.single.month, thisMonth);
      expect(report.models, hasLength(3));
      expect(report.models.first.provider, 'huggingface');
      expect(report.models.first.resource, 'handwriting-qwen');
      expect(report.meter!.status, 'ok');
      expect(report.meter!.allocation, CostAllocation.ok);
      expect(report.meter!.allocatedThrough, '2026-10-19');
    });

    test('takes a null limit and a null meter as none, not as zero', () {
      final CostReport report = CostReport.fromWire(emptyCostWire('2026-09'));

      expect(report.organizationLimit, isNull);
      expect(report.collections.single.limit, isNull);
      expect(report.meter, isNull);
      expect(report.months, isEmpty);
      expect(report.totals.hasCosts, isFalse);
    });

    test('keeps a stage and a meter status it has not met', () {
      final Json wire = costWire(thisMonth);
      ((wire['months'] as List<Object?>).first! as Json)['stages'] = <Json>[
        <String, dynamic>{'stage': 'new_thing', ...amounts(5)},
      ];
      wire['meter'] = <String, dynamic>{
        'allocated_through': null,
        'allocation_status': 'something_new',
      };
      final CostReport report = CostReport.fromWire(wire);

      expect(report.months.single.stages.single.stage, 'new_thing');
      expect(report.meter!.status, 'something_new');
      expect(report.meter!.allocatedThrough, isNull);
    });

    test('reads a limit with no remaining figure from the other two', () {
      final CostLimit? limit = CostLimit.fromWire(<String, dynamic>{
        'monthly_cap_micros': 5000000,
        'month': thisMonth,
        'spent_micros': 1200000,
      });

      expect(limit!.remainingMicros, 3800000);
      expect(limit.reached, isFalse);
    });

    test('a limit that is not a limit reads as none', () {
      expect(CostLimit.fromWire(null), isNull);
      expect(CostLimit.fromWire(<String, dynamic>{'month': thisMonth}), isNull);
      expect(CostLimit.fromWire('5'), isNull);
    });

    test('a limit at or past its amount is reached', () {
      expect(
        CostLimit.fromWire(limitWire(5000000, spent: 5000000))!.reached,
        isTrue,
      );
      expect(
        CostLimit.fromWire(limitWire(5000000, spent: 5200000))!.reached,
        isTrue,
      );
    });

    test('drops a row that names nothing rather than inventing one', () {
      final Json wire = costWire(thisMonth);
      (wire['collections'] as List<Object?>).add(<String, dynamic>{
        'name': 'No identifier',
      });
      (wire['models'] as List<Object?>).add(<String, dynamic>{'stage': 'x'});
      final CostReport report = CostReport.fromWire(wire);

      expect(report.collections, hasLength(4));
      expect(report.models, hasLength(3));
    });

    test('refuses a currency that is not US dollars', () {
      final Json wire = costWire(thisMonth)..['currency'] = 'EUR';

      expect(
        () => CostReport.fromWire(wire),
        throwsA(
          isA<ApiFailure>().having(
            (ApiFailure f) => f.code,
            'code',
            'unsupported_currency',
          ),
        ),
      );
    });

    test('refuses a body that is not a report', () {
      expect(
        () => CostReport.fromWire(<String, dynamic>{}),
        throwsA(
          isA<ApiFailure>().having(
            (ApiFailure f) => f.code,
            'code',
            'invalid_response',
          ),
        ),
      );
    });

    test('lists the stages that recorded something, largest first', () {
      final CostReport report = CostReport.fromWire(costWire(thisMonth));
      final List<String> stages = report
          .monthOf(thisMonth)!
          .stagesByCost
          .map((CostStage s) => s.stage)
          .toList();

      // `api` recorded nothing, so it is not a row.
      expect(stages, <String>[
        'reading',
        'label_finding',
        'first_pass',
        'storage',
        'database',
      ]);
      expect(report.monthOf('2026-01'), isNull);
    });

    test('breaks a tie by stage so the order never changes', () {
      const CostMonth month = CostMonth(
        month: thisMonth,
        totals: CostAmounts.none,
        stages: <CostStage>[
          CostStage(
            stage: 'worker',
            amounts: CostAmounts(
              costMicros: 5,
              heldMicros: 0,
              listCostMicros: 5,
              entries: 1,
            ),
          ),
          CostStage(
            stage: 'api',
            amounts: CostAmounts(
              costMicros: 5,
              heldMicros: 0,
              listCostMicros: 5,
              entries: 1,
            ),
          ),
        ],
      );

      expect(
        month.stagesByCost.map((CostStage s) => s.stage).toList(),
        <String>['api', 'worker'],
      );
    });

    test('lists the models of one month, largest first', () {
      final Json wire = costWire(thisMonth);
      (wire['models'] as List<Object?>).add(<String, dynamic>{
        'month': '2026-09',
        'stage': 'reading',
        'provider': 'huggingface',
        'resource': 'older',
        ...amounts(99999999),
      });
      final CostReport report = CostReport.fromWire(wire);

      expect(
        report
            .modelsOf(thisMonth)
            .map((CostModelRow row) => row.resource)
            .toList(),
        <String>['handwriting-qwen', 'printed-glm', 'first-pass-glm'],
      );
    });
  });

  group('the meter states', () {
    test('are read from the server\'s snake_case words', () {
      expect(CostAllocation.fromWire('ok'), CostAllocation.ok);
      expect(
        CostAllocation.fromWire('monitoring_unavailable'),
        CostAllocation.monitoringUnavailable,
      );
      expect(CostAllocation.fromWire('never_run'), CostAllocation.neverRun);
    });

    test('leave a state this client has not met unnamed', () {
      for (final String word in <String>[
        'catching_up',
        '',
        'OK',
        'monitoringUnavailable',
        'never__run',
        'never_',
      ]) {
        expect(CostAllocation.fromWire(word), isNull, reason: word);
      }
    });

    test('keep the word the server sent', () {
      const CostMeter meter = CostMeter(
        allocatedThrough: null,
        status: 'catching_up',
      );

      expect(meter.status, 'catching_up');
      expect(meter.allocation, isNull);
    });
  });

  group('the collection tree', () {
    test('places a collection under its parent, indented a level', () {
      final List<CostCollectionRow> rows = costCollectionRows(
        CostReport.fromWire(costWire(thisMonth)).collections,
      );

      expect(
        rows
            .map(
              (CostCollectionRow r) =>
                  (r.collection.name, r.depth, r.hasChildren),
            )
            .toList(),
        <(String, int, bool)>[
          ('Insects', 0, true),
          ('Beetles', 1, false),
          ('Plants', 0, false),
          // Its parent was not listed, so it is shown at the top rather than
          // dropped.
          ('Microscopic slides', 0, false),
        ],
      );
    });

    test('orders a child under its parent whatever order they arrive in', () {
      final List<CostCollectionRow> rows = costCollectionRows(<CostCollection>[
        collection('child', parent: 'root'),
        collection('other'),
        collection('root'),
        collection('grandchild', parent: 'child'),
      ]);

      expect(
        rows.map((CostCollectionRow r) => (r.collection.id, r.depth)).toList(),
        <(String, int)>[
          ('other', 0),
          ('root', 0),
          ('child', 1),
          ('grandchild', 2),
        ],
      );
    });

    test('shows a cycle once each rather than looping or losing one', () {
      final List<CostCollectionRow> rows = costCollectionRows(<CostCollection>[
        collection('a', parent: 'b'),
        collection('b', parent: 'a'),
        collection('self', parent: 'self'),
      ]);

      expect(
        rows.map((CostCollectionRow r) => r.collection.id).toSet(),
        <String>{'a', 'b', 'self'},
      );
      expect(rows, hasLength(3));
    });
  });

  group('the months', () {
    test('are the current UTC month and the eleven before it', () {
      final List<String> months = costMonthChoices(
        DateTime.utc(2026, 10, 20, 15),
      );

      expect(months, hasLength(12));
      expect(months.first, '2026-10');
      expect(months[1], '2026-09');
      expect(months.last, '2025-11');
    });

    test('cross a year without skipping or repeating one', () {
      final List<String> months = costMonthChoices(DateTime.utc(2026, 1, 5));

      expect(months.first, '2026-01');
      expect(months[1], '2025-12');
      expect(months.last, '2025-02');
      expect(months.toSet(), hasLength(12));
    });

    test('count in UTC, not on the local clock', () {
      // 23:30 on 31 October in Chicago is already November in UTC.
      expect(
        costMonthChoices(DateTime.utc(2026, 11, 1, 4, 30)).first,
        '2026-11',
      );
      expect(costMonthKey(DateTime.utc(2026, 10, 31, 23, 59)), '2026-10');
    });

    test('are named the way a reviewer reads them', () {
      expect(costMonthLabel('2026-10'), 'October 2026');
      expect(costMonthLabel('2025-02'), 'February 2025');
      expect(costMonthLabel('garbage'), 'garbage');
      expect(costMonthLabel('2026-13'), '2026-13');
    });

    test('name a day without moving it to the reviewer\'s clock', () {
      expect(costDayLabel('2026-10-19'), '19 Oct 2026');
      expect(costDayLabel('2026-01-01'), '1 Jan 2026');
      expect(costDayLabel('yesterday'), 'yesterday');
    });
  });

  group('the stage and provider words', () {
    test('name every stage the contract lists', () {
      for (final String stage in <String>[
        'label_finding',
        'reading',
        'first_pass',
        'structuring',
        'classification',
        'field_research',
        'worker',
        'api',
        'storage',
        'database',
      ]) {
        final String label = costStageLabel(stage);
        expect(label, isNot(contains('_')), reason: stage);
        expect(label[0], label[0].toUpperCase(), reason: stage);
        expect(label, isNot(stage), reason: stage);
      }
      expect(costStageLabel('first_pass'), 'First pass');
    });

    test('still name a stage this client has not met', () {
      expect(costStageLabel('image_cleanup'), 'Image cleanup');
      expect(costStageLabel('x'), 'X');
      expect(costStageLabel(''), '');
    });

    test('name a provider by its own spelling, and an unknown one plainly', () {
      expect(costProviderLabel('huggingface'), 'Hugging Face');
      expect(costProviderLabel('nvidia'), 'NVIDIA');
      expect(costProviderLabel('fireworks'), 'Fireworks');
    });
  });

  group('who may ask', () {
    const CollectionScope insects = CollectionScope(
      organizationId: 'org',
      collectionId: 'insects',
      name: 'Insects',
      permissions: <String>['admin'],
    );
    const CollectionScope plants = CollectionScope(
      organizationId: 'org',
      collectionId: 'plants',
      name: 'Plants',
      permissions: <String>['reviewer'],
    );
    const CollectionScope elsewhere = CollectionScope(
      organizationId: 'other',
      collectionId: 'birds',
      name: 'Birds',
      permissions: <String>['admin'],
    );

    test('an administrator of a collection in the open organization', () {
      expect(costOrganizationOf(<CollectionScope>[insects], insects), 'org');
    });

    test('an administrator of any collection in it, not only the open one', () {
      expect(
        costOrganizationOf(<CollectionScope>[insects, plants], plants),
        'org',
      );
    });

    test('nobody who is only a reviewer or a manager', () {
      expect(costOrganizationOf(<CollectionScope>[plants], plants), isNull);
      const CollectionScope manager = CollectionScope(
        organizationId: 'org',
        collectionId: 'm',
        name: 'M',
        permissions: <String>['manager'],
      );
      expect(costOrganizationOf(<CollectionScope>[manager], manager), isNull);
    });

    test('nobody who administers only another organization', () {
      expect(
        costOrganizationOf(<CollectionScope>[plants, elsewhere], plants),
        isNull,
      );
    });

    test('nobody while no collection is open', () {
      expect(costOrganizationOf(<CollectionScope>[insects], null), isNull);
      expect(costOrganizationOf(const <CollectionScope>[], null), isNull);
    });

    test('a permission named admin is not the role', () {
      const CollectionScope odd = CollectionScope(
        organizationId: 'org',
        collectionId: 'odd',
        name: 'Odd',
        permissions: <String>['reviewer', 'administer'],
      );
      expect(costOrganizationOf(<CollectionScope>[odd], odd), isNull);
    });
  });

  test('a repository serves costs only when it implements them', () {
    expect(costsIn(FakeCostRepository()), isA<CostRepository>());
    expect(costsIn(Object()), isNull);
    expect(costsIn(null), isNull);
  });
}
