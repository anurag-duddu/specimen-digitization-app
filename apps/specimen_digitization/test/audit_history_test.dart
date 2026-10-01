import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/audit_history.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'workbench_harness.dart';

void main() {
  const current = Specimen({'specimen_id': 's', 'revision': 3});

  List<String> timelineTitles(WidgetTester tester) => tester
      .widgetList<UiListRow>(find.byType(UiListRow))
      .map((row) => row.title)
      .toList();

  testWidgets(
    'history loads newest first, pages within its snapshot and previews read only',
    (tester) async {
      const snapshot = Specimen({'specimen_id': 's', 'revision': 13});
      final pageCalls = <List<int>>[];
      final revisionCalls = <int>[];
      await tester.pumpWidget(
        scrollingHost(
          AuditHistoryPanel(
            specimen: snapshot,
            embedded: true,
            loadPage: (after, through) async {
              pageCalls.add([after, through]);
              return HistoryPage(
                items: [
                  for (
                    var revision = after + 1;
                    revision <= through;
                    revision++
                  )
                    {
                      'revision': revision,
                      'action': 'review_field',
                      'actor': 'Reviewer',
                      'created_at': '2026-09-27T10:00:00Z',
                    },
                ],
                throughRevision: through,
              );
            },
            loadRevision: (revision, runId, digest) async {
              revisionCalls.add(revision);
              return Specimen({
                'specimen_id': 's',
                'revision': revision,
                'audit_events': [
                  {
                    'action': 'legacy',
                    'before': {'literal': 'Retained original evidence'},
                  },
                ],
              });
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(Surface), findsNothing);
      expect(find.text('History'), findsOneWidget);
      expect(find.text('Current version 13'), findsOneWidget);
      expect(find.text('Browse record versions'), findsNothing);
      expect(pageCalls, [
        [3, 13],
      ]);
      expect(revisionCalls, isEmpty);
      expect(timelineTitles(tester), [
        'Version 13 · current',
        for (var revision = 12; revision >= 4; revision--) 'Version $revision',
      ]);

      await tester.ensureVisible(find.text('Version 12'));
      await tester.tap(find.text('Version 12'));
      await tester.pumpAndSettle();
      expect(revisionCalls, [12]);
      expect(find.text('Changes from current version 13'), findsOneWidget);
      expect(find.text('Changes saved in this version'), findsOneWidget);
      expect(controlEnabled(tester, 'Restore this version'), false);
      expect(find.byType(EditableText), findsNothing);
      expect(find.text('Approve'), findsNothing);
      expect(find.textContaining('Retained original evidence'), findsNothing);
      await tester.ensureVisible(find.text('Retained version data'));
      await tester.tap(find.text('Retained version data'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Retained original evidence'), findsOneWidget);
      await closeUiModal(tester);
      await tester.ensureVisible(find.text('Close past version'));
      await tester.tap(find.text('Close past version'));
      await tester.pumpAndSettle();
      expect(find.text('Changes from current version 13'), findsNothing);

      await tester.ensureVisible(find.text('Load earlier versions'));
      await tester.tap(find.text('Load earlier versions'));
      await tester.pumpAndSettle();
      expect(pageCalls, [
        [3, 13],
        [0, 3],
      ]);
      expect(timelineTitles(tester), [
        'Version 13 · current',
        for (var revision = 12; revision >= 1; revision--) 'Version $revision',
      ]);
      expect(find.text('Load earlier versions'), findsNothing);
      expect(snapshot.revision, 13);
      expect(revisionCalls, [12]);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('audit reference verifies digest and preserves it on retry', (
    tester,
  ) async {
    final calls = <List<Object?>>[];
    await tester.pumpWidget(
      scrollingHost(
        AuditHistoryPanel(
          specimen: Specimen({
            ...current.data,
            'audit_offset': 30,
            'history_through_revision': 2,
            'audit_events': [
              {
                'action': 'review',
                'before': {
                  'specimen_id': 's',
                  'revision': 2,
                  'run_id': 'r2',
                  'run_sha256': 'b' * 64,
                  'history_url': 'https://untrusted.invalid',
                },
              },
            ],
          }),
          loadRevision: (revision, runId, digest) async {
            calls.add([revision, runId, digest]);
            if (calls.length == 1) {
              throw const ApiFailure('Digest could not be verified');
            }
            return const Specimen({'specimen_id': 's', 'revision': 2});
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Open version 2'));
    await tester.tap(find.text('Open version 2'));
    await tester.pumpAndSettle();
    expect(find.text('Digest could not be verified'), findsOneWidget);
    expect(find.textContaining('Changes from current version'), findsNothing);
    await tester.ensureVisible(find.text('Retry loading version'));
    await tester.tap(find.text('Retry loading version'));
    await tester.pumpAndSettle();
    expect(calls, [
      [2, 'r2', 'b' * 64],
      [2, 'r2', 'b' * 64],
    ]);
    expect(find.text('Changes from current version 3'), findsOneWidget);
    expect(find.text('Digest could not be verified'), findsNothing);
    expect(find.text('Retry loading version'), findsNothing);
  });

  for (final replaceScope in [true, false]) {
    testWidgets(
      replaceScope
          ? 'late version response cannot survive keyed scope replacement'
          : 'late version response cannot survive record replacement without key',
      (tester) async {
        final pending = Completer<Specimen>();
        Widget panel(Specimen specimen, String scope) => scrollingHost(
          AuditHistoryPanel(
            key: replaceScope ? ValueKey('$scope:${specimen.id}') : null,
            specimen: specimen,
            loadPage: (after, through) async => HistoryPage(
              items: [
                {'revision': 1},
              ],
              throughRevision: through,
            ),
            loadRevision: (revision, runId, digest) => pending.future,
          ),
        );
        await tester.pumpWidget(panel(current, 'scope-a'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Version 1'));
        await tester.pump();
        expect(find.text('Loading version 1'), findsOneWidget);
        await tester.pumpWidget(
          panel(
            const Specimen({'specimen_id': 'other', 'revision': 1}),
            'scope-b',
          ),
        );
        pending.complete(
          const Specimen({
            'specimen_id': 's',
            'revision': 1,
            'fields': [
              {'field_key': 'city', 'literal': 'PRIVATE_OLD_SCOPE'},
            ],
          }),
        );
        await tester.pumpAndSettle();
        expect(find.text('Current version 1'), findsOneWidget);
        expect(find.textContaining('PRIVATE_OLD_SCOPE'), findsNothing);
        expect(
          find.textContaining('Changes from current version'),
          findsNothing,
        );
        expect(find.text('Loading version 1'), findsNothing);
        expect(find.text('Version unavailable'), findsNothing);
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets('late page cannot enter the replacement record timeline', (
    tester,
  ) async {
    final pending = Completer<HistoryPage>();
    final calls = <String>[];
    Widget panel(Specimen specimen) => scrollingHost(
      AuditHistoryPanel(
        specimen: specimen,
        loadPage: (after, through) {
          calls.add('${specimen.id}:$after:$through');
          if (specimen.id == 's') return pending.future;
          return Future.value(
            HistoryPage(
              items: [
                {'revision': 5, 'actor': 'Current scope'},
              ],
              throughRevision: through,
            ),
          );
        },
      ),
    );
    await tester.pumpWidget(panel(current));
    await tester.pump();
    expect(find.text('Loading versions'), findsOneWidget);
    await tester.pumpWidget(
      panel(const Specimen({'specimen_id': 'other', 'revision': 5})),
    );
    await tester.pumpAndSettle();
    pending.complete(
      const HistoryPage(
        items: [
          {'revision': 2, 'actor': 'PRIVATE_OLD_SCOPE'},
        ],
        throughRevision: 3,
      ),
    );
    await tester.pumpAndSettle();
    expect(calls, ['s:0:3', 'other:0:5']);
    expect(timelineTitles(tester), ['Version 5 · current']);
    expect(find.textContaining('PRIVATE_OLD_SCOPE'), findsNothing);
    expect(find.text('Version 2'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'preview maps the historical disposition rather than current status',
    (tester) async {
      const cleared = Specimen({
        'specimen_id': 's',
        'revision': 3,
        'disposition': 'cleared',
        'operational_state': 'completed',
      });
      await tester.pumpWidget(
        scrollingHost(
          AuditHistoryPanel(
            specimen: cleared,
            loadPage: (after, through) async => HistoryPage(
              items: [
                {'revision': 2},
              ],
              throughRevision: through,
            ),
            loadRevision: (revision, runId, digest) async => const Specimen({
              'specimen_id': 's',
              'revision': 2,
              'disposition': 'needs_human_review',
              'operational_state': 'retry_scheduled',
            }),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Version 2'));
      await tester.pumpAndSettle();
      expect(find.text('Changes from current version 3'), findsOneWidget);
      expect(find.text('Status: Needs review'), findsOneWidget);
      expect(find.text('Status: Cleared'), findsNothing);
      expect(find.text('Status: Retry scheduled'), findsNothing);
      expect(find.text('Status: State unknown'), findsNothing);
      expect(cleared.disposition, 'cleared');
      expect(cleared.state, 'completed');
      expect(tester.takeException(), isNull);
    },
  );
}
