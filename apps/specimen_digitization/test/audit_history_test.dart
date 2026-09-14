import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/audit_history.dart';
import 'package:specimen_digitization/src/models.dart';

import 'workbench_harness.dart';

void main() {
  const current = Specimen({'specimen_id': 's', 'revision': 3});
  Widget host(Widget child) => scrollingHost(child);
  testWidgets('history available without compaction and keeps current bound', (
    tester,
  ) async {
    final calls = <List<int>>[];
    await tester.pumpWidget(
      host(
        AuditHistoryPanel(
          specimen: current,
          loadPage: (after, through) async {
            calls.add([after, through]);
            return HistoryPage(
              items: [
                {'revision': after + 1, 'sha256': 'a' * 64},
              ],
              throughRevision: through,
              nextCursor: after == 0 ? 1 : null,
            );
          },
          loadRevision: (revision, runId, digest) async => Specimen({
            'specimen_id': 's',
            'revision': revision,
            'audit_events': [
              {
                'action': 'legacy',
                'before': {'literal': 'Retained original evidence'},
              },
            ],
          }),
        ),
      ),
    );
    await tester.tap(find.text('Browse record versions'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Version 1'));
    await tester.pumpAndSettle();
    expect(find.text('Version 1 · read only'), findsOneWidget);
    expect(
      find.textContaining('Your current review is on version 3.'),
      findsOneWidget,
    );
    expect(find.text('1 · legacy'), findsOneWidget);
    await tester.ensureVisible(find.text('Technical detail').last);
    await tester.tap(find.text('Technical detail').last);
    await tester.pumpAndSettle();
    expect(find.textContaining('Retained original evidence'), findsOneWidget);
    await tester.ensureVisible(find.text('Load more versions'));
    await tester.tap(find.text('Load more versions'));
    await tester.pumpAndSettle();
    expect(calls, [
      [0, 3],
      [1, 3],
    ]);
    expect(current.revision, 3);
    expect(find.text('Approve'), findsNothing);
  });
  testWidgets('audit reference verifies digest and preserves it on retry', (
    tester,
  ) async {
    final calls = <List<Object?>>[];
    await tester.pumpWidget(
      host(
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
    expect(
      find.textContaining('Earlier audit and run evidence through version 2'),
      findsOneWidget,
    );
    expect(find.text('31 · review'), findsOneWidget);
    await tester.ensureVisible(find.text('Open version 2'));
    await tester.tap(find.text('Open version 2'));
    await tester.pumpAndSettle();
    expect(find.text('Digest could not be verified'), findsOneWidget);
    await tester.ensureVisible(find.text('Retry loading version'));
    await tester.tap(find.text('Retry loading version'));
    await tester.pumpAndSettle();
    expect(calls, [
      [2, 'r2', 'b' * 64],
      [2, 'r2', 'b' * 64],
    ]);
    expect(find.text('Version 2 · read only'), findsOneWidget);
  });
  testWidgets('late response cannot survive scope replacement', (tester) async {
    final pending = Completer<Specimen>();
    await tester.pumpWidget(
      host(
        AuditHistoryPanel(
          key: const ValueKey('scope-a:s:3'),
          specimen: current,
          loadPage: (after, through) async => HistoryPage(
            items: [
              {'revision': 1, 'sha256': 'a' * 64},
            ],
            throughRevision: through,
          ),
          loadRevision: (revision, runId, digest) => pending.future,
        ),
      ),
    );
    await tester.tap(find.text('Browse record versions'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Version 1'));
    await tester.pump();
    await tester.pumpWidget(
      host(
        const AuditHistoryPanel(
          key: ValueKey('scope-b:other:1'),
          specimen: Specimen({'specimen_id': 'other', 'revision': 1}),
        ),
      ),
    );
    pending.complete(
      const Specimen({
        'specimen_id': 's',
        'revision': 1,
        'profile_version': 'PRIVATE_OLD_SCOPE',
      }),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('PRIVATE_OLD_SCOPE'), findsNothing);
    expect(find.text('Version 1 · read only'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
