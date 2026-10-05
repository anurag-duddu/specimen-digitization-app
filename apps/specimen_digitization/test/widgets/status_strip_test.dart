// Review feedback keeps its minimal presentation while preserving status
// announcements, conflict recovery and unsent corrections.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/screens/workbench/pending_changes.dart';
import 'package:specimen_digitization/src/screens/workbench/status_strip.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import 'harness.dart';

const Size medium = Size(768, 1024);
const Size phone = Size(390, 844);

Specimen record({String disposition = 'needs_human_review'}) =>
    Specimen(<String, dynamic>{
      'specimen_id': 'strip-001',
      'revision': 17,
      'disposition': disposition,
      'active_run_id': 'run-42',
      'run': <String, dynamic>{'stage': 'transcribe'},
    });

const PendingFieldChange correction = PendingFieldChange(
  fieldKey: 'locality',
  displayName: 'Locality',
  state: 'supported',
  literal: 'Chicago',
);

WorkbenchStatusStrip strip(
  Specimen specimen, {
  bool saved = false,
  List<PendingFieldChange> pending = const <PendingFieldChange>[],
  List<PendingFieldChange> staleChanges = const <PendingFieldChange>[],
  int? conflictVersion,
  String? reconciliationMessage,
  VoidCallback? onRefresh,
}) => WorkbenchStatusStrip(
  specimen: specimen,
  saved: saved,
  blockers: const <ClearanceBlocker>[],
  pending: pending,
  staleChanges: staleChanges,
  conflictVersion: conflictVersion,
  reconciliationMessage: reconciliationMessage,
  onRefresh: onRefresh,
  onGoToBlocker: (ClearanceBlocker _) {},
);

void main() {
  testWidgets('tablet feedback does not repeat record status and provenance', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, strip(record()), size: medium);
    expect(find.byType(TermText), findsNothing);
    expect(find.byType(StatusChip), findsNothing);
    expect(find.text('Needs review'), findsNothing);
    expect(find.textContaining('run-42'), findsNothing);
    expect(find.text('Saved'), findsNothing);
  });

  testWidgets('opening a cleared record is not a saved decision', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      strip(record(disposition: 'cleared')),
      size: medium,
    );
    expect(find.text('Saved'), findsNothing);
  });

  testWidgets('phone feedback shows unsent corrections only while present', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      strip(record(), pending: const <PendingFieldChange>[correction]),
      size: phone,
    );
    expect(find.text('1 pending change'), findsOneWidget);
    expect(find.byType(StatusChip), findsNothing);
    expect(find.byType(TermText), findsNothing);

    await pumpComponent(tester, strip(record()), size: phone);
    expect(find.text('1 pending change'), findsNothing);
    expect(find.text('Saved'), findsNothing);
  });

  testWidgets('phone correction feedback remains readable at 200 percent', (
    WidgetTester tester,
  ) async {
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await pumpComponent(
      tester,
      strip(record(), pending: const <PendingFieldChange>[correction]),
      size: phone,
    );
    expect(find.text('1 pending change'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a phone conflict offers one working refresh action', (
    WidgetTester tester,
  ) async {
    int refreshed = 0;
    await pumpComponent(
      tester,
      strip(record(), conflictVersion: 18, onRefresh: () => refreshed++),
      size: phone,
    );
    expect(find.text(ConflictBanner.copyFor(18)), findsOneWidget);
    await tester.tap(find.text(ConflictBanner.action));
    expect(refreshed, 1);
    expect(find.byType(StatusChip), findsNothing);
  });

  testWidgets('acknowledged edits show Saved without changing disposition', (
    WidgetTester tester,
  ) async {
    await pumpComponent(tester, strip(record()), size: medium);
    expect(find.text('Saved'), findsNothing);
    await pumpComponent(tester, strip(record(), saved: true), size: medium);
    expect(find.text('Saved'), findsOneWidget);
    expect(find.byType(StatusChip), findsNothing);
    expect(find.byType(TermText), findsNothing);
    await pumpComponent(tester, strip(record()), size: medium);
    expect(find.text('Saved'), findsNothing);
  });

  testWidgets('a dropped correction retains its recovery explanation', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      strip(record(), staleChanges: const <PendingFieldChange>[correction]),
      size: phone,
    );
    expect(
      find.text(
        '1 correction was dropped because that field changed on the server. '
        'Make it again against the new version.',
      ),
      findsOneWidget,
    );
    expect(find.text('1 pending change'), findsNothing);
    expect(find.text('Saved'), findsNothing);
  });

  for (final recovery in ['pending', 'stale', 'reconciliation']) {
    testWidgets('$recovery feedback suppresses an acknowledged Saved label', (
      tester,
    ) async {
      await pumpComponent(
        tester,
        strip(
          record(),
          saved: true,
          pending: recovery == 'pending' ? const [correction] : const [],
          staleChanges: recovery == 'stale' ? const [correction] : const [],
          reconciliationMessage: recovery == 'reconciliation'
              ? 'Refresh and compare this save.'
              : null,
        ),
        size: phone,
      );
      expect(find.text('Saved'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  // Status changes remain audible once even without a permanent status chip.
  // A move the poll brings must not use the Saved cue for a decision.
  group('announcements', () {
    Specimen live(String status, {String? disposition}) =>
        Specimen(<String, dynamic>{
          'specimen_id': 'pilot-live',
          'revision': 3,
          'status': status,
          'disposition': disposition,
        });

    Widget announcing(Specimen specimen) => Builder(
      builder: (BuildContext context) => MediaQuery(
        data: MediaQuery.of(context).copyWith(supportsAnnounce: true),
        child: strip(specimen),
      ),
    );

    List<String> heard(WidgetTester tester) => tester
        .takeAnnouncements()
        .map((CapturedAccessibilityAnnouncement a) => a.message)
        .toList();

    testWidgets('a run state change is announced once', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, announcing(live('running')), size: medium);
      expect(heard(tester), isEmpty, reason: 'opening a record is not news');
      await pumpComponent(
        tester,
        announcing(live('processing_blocked')),
        size: medium,
      );
      expect(heard(tester), <String>['Run: processing blocked']);
      await pumpComponent(
        tester,
        announcing(live('processing_blocked')),
        size: medium,
      );
      expect(heard(tester), isEmpty, reason: 'once, not on every poll');
    });

    testWidgets('completed processing is announced without a fabricated save', (
      WidgetTester tester,
    ) async {
      await pumpComponent(tester, announcing(live('running')), size: medium);
      heard(tester);
      await pumpComponent(
        tester,
        announcing(live('completed', disposition: 'needs_human_review')),
        size: medium,
      );
      expect(heard(tester), <String>['Queue: needs review']);
      expect(find.text('Saved'), findsNothing);
      await pumpComponent(
        tester,
        announcing(live('completed', disposition: 'needs_human_review')),
        size: medium,
      );
      expect(heard(tester), isEmpty);
    });
  });
}
