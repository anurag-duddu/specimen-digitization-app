import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/audit_history.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'workbench_harness.dart';

Json event(int sequence, String action, int revision) => {
  'id': 'event-$sequence',
  'sequence': sequence,
  'resulting_revision': revision,
  'actor': 'Recorded actor',
  'action': action,
  'reason': 'Recorded reason $sequence',
  'created_at': '2026-09-27T10:00:00Z',
};

Future<void> press(WidgetTester tester, String label) async {
  await tester.ensureVisible(find.text(label));
  await tester.tap(find.text(label));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('current audit remains visible with a hash-only version index', (
    tester,
  ) async {
    final snapshot = Specimen({
      'specimen_id': 's',
      'revision': 3,
      'audit_offset': 0,
      'fields': [
        {'field_key': 'country', 'display_name': 'Country'},
      ],
      'audit_events': [
        event(1, 'ingest', 2),
        {
          ...event(2, 'review_field', 3),
          'target_id': 'country',
          'before': {'literal': 'Old country'},
          'after': {'literal': 'Corrected country'},
        },
      ],
    });
    await tester.pumpWidget(
      scrollingHost(
        AuditHistoryPanel(
          specimen: snapshot,
          embedded: true,
          loadPage: (after, through) async => HistoryPage(
            throughRevision: through,
            items: [
              {
                'revision': 3,
                'sha256': 'a' * 64,
                'action': 'review_approve',
                'actor': 'UNTRUSTED_INDEX_ACTOR',
                'created_at': '2026-09-27T10:00:00Z',
              },
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Edited specimen data: Country'), findsOneWidget);
    expect(find.text('Added photograph'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('Edited specimen data: Country')).dy,
      lessThan(tester.getTopLeft(find.text('Added photograph')).dy),
    );
    expect(
      find.text('As written: Old country → Corrected country'),
      findsOneWidget,
    );
    expect(find.text('Reason: Recorded reason 2'), findsOneWidget);
    expect(find.text('UNTRUSTED_INDEX_ACTOR'), findsNothing);
    expect(find.text('Approved review'), findsNothing);
    expect(find.byType(UiListRow), findsNothing);
    await press(tester, 'Saved versions');
    expect(find.text('Version 3 · current'), findsOneWidget);
    expect(find.text('Retained snapshot'), findsOneWidget);
    expect(find.textContaining('UNTRUSTED_INDEX_ACTOR'), findsNothing);
    expect(find.text('Approved review'), findsNothing);
    expect(find.byType(EditableText), findsNothing);
  });

  testWidgets('older event recovery follows at most two boundaries per click', (
    tester,
  ) async {
    final calls = <int>[];
    final current = Specimen({
      'specimen_id': 's',
      'revision': 30,
      'audit_offset': 3,
      'history_through_revision': 20,
      'audit_events': [event(4, 'workflow_step', 30)],
    });
    final older = {
      20: Specimen({
        'specimen_id': 's',
        'revision': 20,
        'audit_offset': 2,
        'history_through_revision': 10,
        'audit_events': [event(3, 'review_coverage', 20)],
      }),
      10: Specimen({
        'specimen_id': 's',
        'revision': 10,
        'audit_offset': 1,
        'history_through_revision': 2,
        'audit_events': [event(2, 'review_reading_metadata', 10)],
      }),
      2: Specimen({
        'specimen_id': 's',
        'revision': 2,
        'audit_offset': 0,
        'audit_events': [event(1, 'ingest', 2)],
      }),
    };
    await tester.pumpWidget(
      scrollingHost(
        AuditHistoryPanel(
          specimen: current,
          loadRevision: (revision, runId, digest) async {
            calls.add(revision);
            expect(runId, isNull);
            expect(digest, isNull);
            return older[revision]!;
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(calls, isEmpty, reason: 'older snapshots load only on request');
    await press(tester, 'Load older history');
    expect(calls, [20, 10]);
    expect(find.text('Processing step'), findsOneWidget);
    expect(find.text('Checked label coverage'), findsOneWidget);
    expect(find.text('Updated reading declaration'), findsOneWidget);
    expect(find.text('Added photograph'), findsNothing);
    expect(find.textContaining('Changes from current version'), findsNothing);
    await press(tester, 'Load older history');
    expect(calls, [20, 10, 2]);
    expect(find.text('Added photograph'), findsOneWidget);
    expect(find.text('Load older history'), findsNothing);
    expect(find.textContaining('could not be recovered'), findsNothing);
    expect(find.text('Edited specimen data'), findsNothing);
    expect(current.revision, 30);
    expect(find.byType(EditableText), findsNothing);
  });

  testWidgets(
    'partial recovery retains verified events and retries the failing boundary',
    (tester) async {
      final calls = <int>[];
      await tester.pumpWidget(
        scrollingHost(
          AuditHistoryPanel(
            specimen: Specimen({
              'specimen_id': 's',
              'revision': 4,
              'audit_offset': 2,
              'history_through_revision': 3,
              'audit_events': [event(3, 'review_approve', 4)],
            }),
            loadRevision: (revision, runId, digest) async {
              calls.add(revision);
              if (revision == 3) {
                return Specimen({
                  'specimen_id': 's',
                  'revision': 3,
                  'audit_offset': 1,
                  'history_through_revision': 2,
                  'audit_events': [event(2, 'review_field', 3)],
                });
              }
              if (calls.length == 2) {
                throw const ApiFailure('Retained snapshot unavailable');
              }
              return Specimen({
                'specimen_id': 's',
                'revision': 2,
                'audit_offset': 0,
                'audit_events': [event(1, 'ingest', 2)],
              });
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      await press(tester, 'Load older history');
      expect(calls, [3, 2]);
      expect(find.text('Retained snapshot unavailable'), findsOneWidget);
      expect(find.text('Edited specimen data'), findsOneWidget);
      await press(tester, 'Retry older history');
      expect(calls, [3, 2, 2]);
      expect(
        find.text('Edited specimen data'),
        findsOneWidget,
        reason: 'verified intermediate events remain visible',
      );
      expect(find.text('Added photograph'), findsOneWidget);
      expect(find.text('Retained snapshot unavailable'), findsNothing);
      expect(find.text('Retry older history'), findsNothing);
    },
  );

  testWidgets('late reconstructed events cannot enter a replacement specimen', (
    tester,
  ) async {
    final pending = Completer<Specimen>();
    await tester.pumpWidget(
      scrollingHost(
        AuditHistoryPanel(
          specimen: Specimen({
            'specimen_id': 's',
            'revision': 3,
            'audit_offset': 1,
            'history_through_revision': 2,
            'audit_events': [event(2, 'workflow_step', 3)],
          }),
          loadRevision: (revision, runId, digest) => pending.future,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Load older history'));
    await tester.tap(find.text('Load older history'));
    await tester.pump();
    expect(find.text('Loading earlier events'), findsOneWidget);
    await tester.pumpWidget(
      scrollingHost(
        const AuditHistoryPanel(
          specimen: Specimen({'specimen_id': 'other', 'revision': 1}),
        ),
      ),
    );
    pending.complete(
      const Specimen({
        'specimen_id': 's',
        'revision': 2,
        'audit_offset': 0,
        'audit_events': [
          {
            'id': 'private',
            'action': 'review_field',
            'reason': 'PRIVATE_OLD_SCOPE',
          },
        ],
      }),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('PRIVATE_OLD_SCOPE'), findsNothing);
    expect(find.text('Current version 1'), findsOneWidget);
    expect(find.text('Loading earlier events'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'missing attribution and invalid archive coverage remain explicit',
    (tester) async {
      final calls = <int>[];
      await tester.pumpWidget(
        scrollingHost(
          AuditHistoryPanel(
            specimen: const Specimen({
              'specimen_id': 's',
              'revision': 3,
              'audit_offset': 4,
              'history_through_revision': 4,
              'audit_events': [
                {'id': 'legacy'},
              ],
            }),
            loadRevision: (revision, runId, digest) async {
              calls.add(revision);
              return Specimen({'specimen_id': 's', 'revision': revision});
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Action not recorded'), findsOneWidget);
      expect(
        find.text('Actor not recorded · Time not recorded'),
        findsOneWidget,
      );
      expect(find.textContaining('event version not recorded'), findsOneWidget);
      expect(find.textContaining('could not be recovered'), findsOneWidget);
      expect(find.text('Load older history'), findsNothing);
      expect(calls, isEmpty);
    },
  );

  testWidgets(
    'long retained timelines reveal twenty events per request without fetching snapshots',
    (tester) async {
      final calls = <int>[];
      await tester.pumpWidget(
        scrollingHost(
          AuditHistoryPanel(
            specimen: Specimen({
              'specimen_id': 's',
              'revision': 50,
              'audit_offset': 0,
              'audit_events': [
                for (var i = 1; i <= 45; i++) event(i, 'workflow_step', i + 1),
              ],
            }),
            loadRevision: (revision, runId, digest) async {
              calls.add(revision);
              return Specimen({'specimen_id': 's', 'revision': revision});
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Processing step'), findsNWidgets(20));
      expect(find.text('Reason: Recorded reason 45'), findsOneWidget);
      expect(find.text('Reason: Recorded reason 25'), findsNothing);
      await press(tester, 'Load older history');
      expect(find.text('Processing step'), findsNWidgets(40));
      expect(find.text('Reason: Recorded reason 5'), findsNothing);
      await press(tester, 'Load older history');
      expect(find.text('Processing step'), findsNWidgets(45));
      expect(find.text('Load older history'), findsNothing);
      expect(calls, isEmpty);
    },
  );

  testWidgets(
    'legacy full-run evidence supplies recorded field before values',
    (tester) async {
      await tester.pumpWidget(
        scrollingHost(
          const AuditHistoryPanel(
            specimen: Specimen({
              'specimen_id': 's',
              'revision': 3,
              'audit_offset': 0,
              'fields': [
                {'field_key': 'country', 'display_name': 'Country'},
              ],
              'audit_events': [
                {
                  'id': 'field-edit',
                  'action': 'review_field',
                  'target_id': 'country',
                  'before': {
                    'fields': {
                      'country': {'literal': 'Earlier country'},
                    },
                  },
                  'after': {'literal': 'Corrected country'},
                },
              ],
            }),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        find.text('As written: Earlier country → Corrected country'),
        findsOneWidget,
      );
      expect(
        find.text('Actor not recorded · Time not recorded'),
        findsOneWidget,
      );
      expect(find.text('Field name not recorded in this event.'), findsNothing);
      expect(find.byType(EditableText), findsNothing);
    },
  );

  testWidgets('artifact summaries preserve an explicit event coverage limit', (
    tester,
  ) async {
    await tester.pumpWidget(
      scrollingHost(
        AuditHistoryPanel(
          specimen: Specimen({
            'specimen_id': 's',
            'revision': 3,
            'audit_offset': 1,
            'history_through_revision': 2,
            'audit_events': [event(2, 'workflow_step', 3)],
          }),
          loadRevision: (revision, runId, digest) async => const Specimen({
            'specimen_id': 's',
            'revision': 2,
            'artifact_receipt': {'kind': 'retained-history-summary'},
          }),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await press(tester, 'Load older history');
    expect(find.textContaining('could not be recovered'), findsOneWidget);
    expect(find.text('Load older history'), findsNothing);
    expect(find.text('Processing step'), findsOneWidget);
    expect(find.textContaining('Changes from current version'), findsNothing);
    expect(find.byType(EditableText), findsNothing);
  });
}
