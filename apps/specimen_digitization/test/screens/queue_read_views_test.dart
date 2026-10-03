import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/main.dart';
import 'package:specimen_digitization/src/models.dart';

import '../ui_finders.dart';
import '../widget_test.dart' show TestRepository, TestSession;

// Synthetic identifiers only. These rows preserve the real metadata shape of
// an imported record held before processing: no observations or disposition.
const _blocked = Specimen({
  'specimen_id': '00000000-0000-4000-8000-000000000001',
  'filename': 'Held source image.jpg',
  'revision': 1,
  'status': 'processing_blocked',
  'stage': 'processing_blocked',
  'disposition': null,
  'blocker': 'collection_processing_unconfigured',
  'available_actions': <String>[],
  'observations': <Json>[],
});
const _pending = Specimen({
  'specimen_id': '00000000-0000-4000-8000-000000000002',
  'filename': 'Pending source image.jpg',
  'revision': 1,
  'status': 'pending',
  'stage': 'pending',
  'disposition': null,
  'available_actions': <String>[],
  'observations': <Json>[],
});

class _ReadViewsRepository extends TestRepository {
  final requests = <Map<String, String>>[];
  final mutations = <String>[];

  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    requests.add(Map<String, String>.from(filters));
    return SpecimenPage(
      [_blocked, _pending].where((record) {
        return (filters['disposition'] == null ||
                record.disposition == filters['disposition']) &&
            (filters['state'] == null || record.state == filters['state']) &&
            (filters['specimen_id'] == null ||
                record.id == filters['specimen_id']);
      }).toList(),
    );
  }

  Never _mutation(String operation) {
    mutations.add(operation);
    throw StateError('Read-only queue navigation called $operation');
  }

  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async => _mutation('review');

  @override
  Future<Specimen> retry(
    CollectionScope scope,
    Specimen specimen,
    String reason,
    String key,
  ) async => _mutation('retry');

  @override
  Future<BulkDecisionReport> reviewMany(
    CollectionScope scope,
    List<Specimen> specimens,
    BulkDecisionKind kind,
    String reason,
    String key,
  ) async => _mutation('reviewMany');

  @override
  Future<Json> createIntake(
    CollectionScope scope,
    IntakeFile file,
    String key,
  ) async => _mutation('createIntake');

  @override
  Future<void> upload(
    CollectionScope scope,
    Json session,
    IntakeFile file,
    void Function(double) progress,
  ) async => _mutation('upload');

  @override
  Future<Json> completeIntake(
    CollectionScope scope,
    String id,
    String key,
  ) async => _mutation('completeIntake');
}

Future<void> _pumpQueue(
  WidgetTester tester,
  _ReadViewsRepository repository, {
  required Size window,
  double textScale = 1,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  addTearDown(tester.view.reset);
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  final session = TestSession();
  addTearDown(session.controller.close);
  await tester.pumpWidget(
    SpecimenDigitizationApp(session: session, repository: repository),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('the three review views retain their original filters', (
    tester,
  ) async {
    final repository = _ReadViewsRepository();
    await _pumpQueue(tester, repository, window: const Size(800, 1200));
    expect(repository.requests.single, {'disposition': 'needs_human_review'});
    for (final entry in {
      'Needs a human': 'needs_human_review',
      'Deferred': 'deferred',
      'Cleared': 'cleared',
    }.entries) {
      await pickSpecimenQueue(tester, entry.key);
      expect(find.text(entry.key), findsOneWidget);
      expect(repository.requests.last, {'disposition': entry.value});
      expect(find.text(_blocked.id), findsNothing);
      expect(find.text(_pending.id), findsNothing);
    }
    expect(repository.mutations, isEmpty);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  for (final layout in [
    (name: 'desktop', window: const Size(1440, 900), scale: 1.0),
    (name: 'compact', window: const Size(390, 844), scale: 1.0),
    (name: 'compact at 200 percent', window: const Size(390, 844), scale: 2.0),
  ]) {
    testWidgets(
      '${layout.name}: core views remain below search without overflow',
      (tester) async {
        final repository = _ReadViewsRepository();
        await _pumpQueue(
          tester,
          repository,
          window: layout.window,
          textScale: layout.scale,
        );
        expect(repository.requests.single, {
          'disposition': 'needs_human_review',
        });
        expect(find.text('No specimens need a human'), findsOneWidget);
        expect(find.text(_blocked.id), findsNothing);
        expect(find.text(_pending.id), findsNothing);
        expect(uiMenuTrigger('Specimen list actions'), findsNothing);
        expect(uiIconButton('Done selecting'), findsNothing);
        for (final entry in {
          'Needs a human': 'needs_human_review',
          'Deferred': 'deferred',
          'Cleared': 'cleared',
        }.entries) {
          final filter = find.byKey(
            ValueKey<String>('queue-filter-${entry.value}'),
          );
          expect(filter, findsOneWidget);
          expect(
            tester.getTopLeft(filter).dy,
            greaterThanOrEqualTo(
              tester.getBottomLeft(uiField('Search by full specimen ID')).dy,
            ),
          );
          await pickSpecimenQueue(tester, entry.key);
          expect(repository.requests.last, {'disposition': entry.value});
          expect(find.text(_blocked.id), findsNothing);
          expect(find.text(_pending.id), findsNothing);
        }
        expect(find.text('All specimens'), findsNothing);
        expect(find.text('Blocked'), findsNothing);
        expect(repository.mutations, isEmpty);
        expect(_blocked.disposition, isNull);
        expect(_pending.disposition, isNull);
        expect(_blocked.revision, 1);
        expect(_pending.revision, 1);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
      },
    );
  }
}
