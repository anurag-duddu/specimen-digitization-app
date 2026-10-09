import 'dart:async';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'screens/field_review_test.dart' as field_fixture;
import 'ui_finders.dart';
import 'widget_test.dart' show TestRepository, TestSession, fixture;
import 'workbench_harness.dart';

class LiveRepository extends TestRepository {
  int pageReads = 0;
  int detailReads = 0;
  Specimen current = fixture;
  Completer<SpecimenPage>? heldPage;
  Completer<Specimen>? heldDetail;
  Completer<Specimen>? heldReview;

  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async => heldReview?.future ?? current;
  @override
  Future<SpecimenPage> specimenPage(
    CollectionScope scope, {
    Map<String, String> filters = const {},
    String? cursor,
  }) async {
    pageReads++;
    if (heldPage != null) return heldPage!.future;
    return cursor == null
        ? SpecimenPage([current], nextCursor: 'second-page')
        : SpecimenPage([
            const Specimen({'specimen_id': 'second', 'revision': 1}),
          ]);
  }

  @override
  Future<Specimen> specimen(CollectionScope scope, String id) async {
    detailReads++;
    return heldDetail?.future ?? current;
  }
}

Future<WorkspaceController> started(
  WidgetTester tester,
  LiveRepository repository,
  TestSession session,
) async {
  final controller = WorkspaceController(
    repository: repository,
    session: session,
  );
  controller.start();
  controller.setForeground(true);
  await tester.pumpAndSettle();
  return controller;
}

void main() {
  test(
    'full field basis catches lock/evidence changes and ignores map order',
    () {
      final original = <String, dynamic>{
        'field_key': 'country',
        'literal_value': null,
        'normalized': 'Country A',
        'canonical_binding': {
          'state': 'machine',
          'evidence_ids': ['e1'],
        },
      };
      final pending = PendingFieldChange(
        fieldKey: 'country',
        displayName: 'Country',
        state: 'not_present',
        baseFieldBasis: fieldBasis(original),
      );
      final reordered = <String, dynamic>{
        'canonical_binding': {
          'evidence_ids': ['e1'],
          'state': 'machine',
        },
        'normalized': 'Country A',
        'literal_value': null,
        'field_key': 'country',
      };
      Specimen withField(Json field) => Specimen({
        'fields': [field],
      });
      expect(reapply([pending], withField(reordered)).keep, [pending]);
      for (final changed in [
        {...original, 'normalized': 'Country B'},
        {
          ...original,
          'canonical_binding': {
            'state': 'preserved_human',
            'evidence_ids': ['e1'],
          },
        },
        {
          ...original,
          'canonical_binding': {
            'state': 'machine',
            'evidence_ids': ['e2'],
          },
        },
      ]) {
        expect(reapply([pending], withField(changed)).stale, [pending]);
      }
    },
  );
  testWidgets(
    'an open editor keeps typed text and its original basis during canonical refresh',
    (tester) async {
      useWindow(tester, largeWindow);
      var shown = Specimen({
        ...field_fixture.specimen.data,
        'available_actions': ['field'],
      });
      late StateSetter update;
      await tester.pumpWidget(
        workbenchHost(
          StatefulBuilder(
            builder: (context, setState) {
              update = setState;
              return ReviewWorkbench(
                specimen: shown,
                onChange: (_) async => false,
                onRetry: (_) async {},
                onRefresh: () {},
              );
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Specimen data'));
      await tester.pumpAndSettle();
      await openFieldEditor(tester, 0);
      expect(uiField('As written'), findsOneWidget);
      await tester.ensureVisible(uiField('As written'));
      await tester.pumpAndSettle();
      await tester.enterText(uiField('As written'), 'USA draft');
      update(() {
        shown = Specimen({
          ...shown.data,
          'revision': 2,
          'fields': [
            {
              ...shown.fields.first,
              'normalized': 'Changed machine interpretation',
            },
            ...shown.fields.skip(1),
          ],
        });
      });
      await tester.pumpAndSettle();
      expect(
        tester.widget<UiField>(uiField('As written')).controller!.text,
        'USA draft',
      );
      await scrollAndTap(tester, uiButton('Keep this correction'));
      expect(
        tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
        isEmpty,
      );
      final stale = tester
          .widget<WorkbenchStatusStrip>(find.byType(WorkbenchStatusStrip))
          .staleChanges;
      expect(stale.single.literal, 'USA draft');
      expect(
        stale.single.baseFieldBasis,
        fieldBasis(field_fixture.specimen.fields.first),
      );
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets(
    'foreground selected record refresh survives queue pagination without losing loaded rows',
    (tester) async {
      final repository = LiveRepository();
      final session = TestSession();
      final controller = await started(tester, repository, session);
      try {
        await controller.openSpecimen(fixture.id);
        await controller.loadMore();
        final rows = controller.items.map((row) => row.id).toList();
        repository.current = Specimen({
          ...fixture.data,
          'revision': 4,
          'operational_state': 'running',
        });
        await tester.pump(queuePollInterval);
        await tester.pumpAndSettle();
        expect(controller.selected?.revision, 4);
        expect(repository.detailReads, 2);
        expect(
          repository.pageReads,
          2,
          reason: 'the paginated queue must stay intact',
        );
        expect(controller.items.map((row) => row.id), rows);
      } finally {
        controller.dispose();
        await session.controller.close();
      }
    },
  );
  testWidgets(
    'inactive or submitting workspaces do not fetch, and concurrent detail reads coalesce',
    (tester) async {
      final repository = LiveRepository();
      final session = TestSession();
      final controller = await started(tester, repository, session);
      try {
        await controller.openSpecimen(fixture.id);
        await controller.loadMore();
        controller.setForeground(false);
        await tester.pump(queuePollInterval);
        expect(repository.detailReads, 1);
        controller.setForeground(true);
        final owner = Object();
        controller.setPollingPaused(owner, true);
        await tester.pump(queuePollInterval);
        expect(repository.detailReads, 1);
        controller.setPollingPaused(owner, false);

        final saving = Completer<Specimen>();
        repository.heldReview = saving;
        final saved = controller.mutate({'kind': 'field'}, null);
        await tester.pump(queuePollInterval);
        await controller.refreshSelected();
        expect(repository.detailReads, 1);
        repository.current = Specimen({...fixture.data, 'revision': 4});
        saving.complete(repository.current);
        expect(await saved, isTrue);

        final detail = Completer<Specimen>();
        repository.heldDetail = detail;
        await tester.pump(queuePollInterval);
        final manual = controller.refreshSelected();
        await tester.pump(queuePollInterval * 2);
        expect(repository.detailReads, 2);
        detail.complete(repository.current);
        await manual;
        await tester.pumpAndSettle();
        expect(controller.selected?.revision, 4);
        expect(controller.selectedRefreshEpoch, 1);
      } finally {
        controller.dispose();
        await session.controller.close();
      }
    },
  );
  testWidgets('a slow quiet poll is not overlapped by later timer ticks', (
    tester,
  ) async {
    final repository = LiveRepository();
    final session = TestSession();
    final controller = await started(tester, repository, session);
    try {
      final held = Completer<SpecimenPage>();
      repository.heldPage = held;
      await tester.pump(queuePollInterval);
      await tester.pump(queuePollInterval);
      await tester.pump(queuePollInterval);
      expect(repository.pageReads, 2);
      held.complete(
        SpecimenPage([repository.current], nextCursor: 'second-page'),
      );
      await tester.pumpAndSettle();
    } finally {
      controller.dispose();
      await session.controller.close();
    }
  });
  for (final baseChange in ['unchanged', 'literal', 'derived']) {
    testWidgets(
      'automatic canonical refresh retains human draft and reports changed base: $baseChange',
      (tester) async {
        useWindow(tester, largeWindow);
        final repository = LiveRepository();
        final session = TestSession();
        final controller = await started(tester, repository, session);
        try {
          await controller.openSpecimen(fixture.id);
          await controller.loadMore();
          await tester.pumpWidget(
            workbenchHost(
              AnimatedBuilder(
                animation: controller,
                builder: (context, _) => ReviewWorkbench(
                  specimen: controller.selected!,
                  onChange: (_) async => false,
                  onRetry: (_) async {},
                  onRefresh: () {},
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          await tester.tap(find.text('Specimen data'));
          await tester.pumpAndSettle();
          tester
              .widget<WorkbenchFields>(find.byType(WorkbenchFields))
              .onPendingChanged([
                PendingFieldChange(
                  fieldKey: 'country',
                  displayName: 'Country',
                  state: 'supported',
                  literal: 'Human draft',
                  baseLiteral: null,
                  baseFieldBasis: fieldBasis(fixture.fields.single),
                  evidenceIds: ['o1'],
                ),
              ]);
          await tester.pumpAndSettle();
          repository.current = Specimen({
            ...fixture.data,
            'revision': 4,
            'fields': [
              for (final field in fixture.fields)
                if (baseChange != 'unchanged' &&
                    field['field_key'] == 'country')
                  {
                    ...field,
                    if (baseChange == 'literal')
                      'literal_value': 'Machine verified country',
                    'normalized': 'Machine verified country',
                    'state': 'supported',
                  }
                else
                  field,
            ],
          });
          await tester.pump(queuePollInterval);
          await tester.pumpAndSettle();
          expect(controller.selected?.revision, 4);
          final fields = tester.widget<WorkbenchFields>(
            find.byType(WorkbenchFields),
          );
          final strip = tester.widget<WorkbenchStatusStrip>(
            find.byType(WorkbenchStatusStrip),
          );
          if (baseChange != 'unchanged') {
            expect(fields.pending, isEmpty);
            expect(strip.staleChanges.single.literal, 'Human draft');
          } else {
            expect(fields.pending.single.literal, 'Human draft');
            expect(strip.staleChanges, isEmpty);
          }
        } finally {
          await tester.pumpWidget(const SizedBox());
          controller.dispose();
          await session.controller.close();
        }
      },
    );
  }
}
