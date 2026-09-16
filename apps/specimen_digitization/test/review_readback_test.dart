// Regressions reproduced by the independent acknowledgement review.
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/fields_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/workspace.dart';
import 'product_acceptance_regressions_test.dart' as author;
import 'widget_test.dart' show fixture;

class ApplyingRepository extends author.ReviewRepository {
  ApplyingRepository(super.session);
  bool concurrentCollector = false;
  final List<Json> changes = [];
  @override
  Future<Specimen> review(
    CollectionScope scope,
    Specimen specimen,
    Json change,
    String key,
  ) async {
    reviewRequests++;
    keys.add(key);
    changes.add(change);
    current = Specimen({
      ...current.data,
      'revision': current.revision + 1,
      'fields': [
        for (final field in current.fields)
          if (field['field_key'] == change['target_id'])
            {
              ...field,
              'literal_value': change['value'],
              'state': change['state'],
            }
          else if (concurrentCollector &&
              reviewRequests == 1 &&
              field['field_key'] == 'collector')
            {...field, 'literal_value': 'other reviewer'}
          else
            field,
      ],
    });
    return current;
  }
}

Future<void> stage(WidgetTester tester, {bool two = false}) async {
  await tester.tap(find.text('Fields'));
  await tester.pumpAndSettle();
  tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).onPendingChanged(
    [
      const PendingFieldChange(
        fieldKey: 'country',
        displayName: 'Country',
        state: 'supported',
        literal: 'USA',
        baseLiteral: null,
        evidenceIds: ['o1'],
      ),
      if (two)
        const PendingFieldChange(
          fieldKey: 'collector',
          displayName: 'Collector',
          state: 'supported',
          literal: 'local reviewer',
          baseLiteral: null,
          evidenceIds: ['o1'],
        ),
    ],
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'acknowledged changed literal is not reported as a dropped correction',
    (tester) async {
      final session = author.MutableReviewSession();
      final repository = ApplyingRepository(session);
      await author.openReview(tester, session, repository);
      await stage(tester);
      await author.confirmReason(tester, 'Save 1 pending change');
      expect(repository.reviewRequests, 1);
      expect(repository.current.fields.single['literal_value'], 'USA');
      expect(
        tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
        isEmpty,
      );
      final warnings = find.textContaining('correction was dropped');
      expect(warnings, findsNothing);
      expect(
        tester
            .widget<WorkbenchStatusStrip>(find.byType(WorkbenchStatusStrip))
            .staleChanges,
        isEmpty,
      );
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'batch must not overwrite a later field changed in acknowledged readback',
    (tester) async {
      final session = author.MutableReviewSession();
      final repository = ApplyingRepository(session)
        ..current = Specimen({
          ...fixture.data,
          'fields': [
            ...fixture.fields,
            {
              'field_key': 'collector',
              'display_name': 'Collector',
              'state': 'unknown',
              'literal_value': null,
            },
          ],
        })
        ..concurrentCollector = true;
      await author.openReview(tester, session, repository);
      await stage(tester, two: true);
      await author.confirmReason(tester, 'Save 2 pending changes');
      expect(
        repository.reviewRequests,
        1,
        reason:
            'The first readback changed collector; it is no longer safe to replay the staged second correction.',
      );
      expect(repository.current.fields.last['literal_value'], 'other reviewer');
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'unchanged coverage acknowledgement fails and preserves identical retry key',
    (tester) async {
      final session = author.MutableReviewSession();
      final repository = author.ReviewRepository(session)
        ..returnUnchanged = true;
      await author.openReview(tester, session, repository);
      final c = WorkspaceScope.read(
        tester.element(find.byType(Navigator).first),
      );
      expect(
        await c.mutate({'kind': 'coverage', 'reason': 'reviewed'}, null),
        isFalse,
      );
      repository.returnUnchanged = false;
      expect(
        await c.mutate({'kind': 'coverage', 'reason': 'reviewed'}, null),
        isTrue,
      );
      expect(repository.keys[0], repository.keys[1]);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets('wrong record acknowledgement is refused', (tester) async {
    final session = author.MutableReviewSession();
    final repository = author.ReviewRepository(session)
      ..save = Completer<Specimen>();
    await author.openReview(tester, session, repository);
    final c = WorkspaceScope.read(tester.element(find.byType(Navigator).first));
    final save = c.mutate({'kind': 'coverage', 'reason': 'reviewed'}, null);
    repository.save!.complete(
      Specimen({
        ...fixture.data,
        'specimen_id': 'different-record',
        'revision': 9,
      }),
    );
    expect(await save, isFalse);
    expect(c.selected!.id, fixture.id);
    expect(c.selected!.revision, fixture.revision);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
    'an unchanged later field saves after the first acknowledged correction',
    (tester) async {
      final session = author.MutableReviewSession();
      final repository = ApplyingRepository(session)
        ..current = Specimen({
          ...fixture.data,
          'fields': [
            ...fixture.fields,
            {
              'field_key': 'collector',
              'display_name': 'Collector',
              'state': 'unknown',
              'literal_value': null,
            },
          ],
        });
      await author.openReview(tester, session, repository);
      await stage(tester, two: true);
      await author.confirmReason(tester, 'Save 2 pending changes');
      expect(repository.reviewRequests, 2);
      expect(repository.current.fields.map((f) => f['literal_value']), [
        'USA',
        'local reviewer',
      ]);
      expect(
        tester.widget<WorkbenchFields>(find.byType(WorkbenchFields)).pending,
        isEmpty,
      );
      expect(
        tester
            .widget<WorkbenchStatusStrip>(find.byType(WorkbenchStatusStrip))
            .staleChanges,
        isEmpty,
      );
      expect(find.text('Save not confirmed'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
