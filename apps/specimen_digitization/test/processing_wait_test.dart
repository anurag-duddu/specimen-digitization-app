import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

Specimen processingRecord({
  String? status = 'running',
  Json run = const <String, dynamic>{},
  List<String> actions = const <String>['pause', 'cancel'],
}) => Specimen(<String, dynamic>{
  'specimen_id': 'processing-wait',
  'status': status,
  'available_actions': actions,
  'run': <String, dynamic>{
    'stage': 'transcribe',
    'blocker': 'external_outcome_unknown',
    'lease_until': DateTime.now()
        .add(const Duration(hours: 1))
        .toUtc()
        .toIso8601String(),
    'dead_letter': false,
    ...run,
  },
});

Future<void> showProcessing(
  WidgetTester tester,
  Specimen specimen, {
  bool disclosure = false,
}) async {
  final Widget child = disclosure
      ? ProcessingDisclosure(
          specimen: specimen,
          canOperate: true,
          busy: false,
          onAction: (_) async {},
        )
      : OperationalPanel(
          specimen: specimen,
          canOperate: true,
          busy: false,
          onAction: (_) async {},
        );
  await tester.pumpWidget(scrollingHost(child));
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull);
}

void main() {
  testWidgets('an active external intent waits without asking for recovery', (
    tester,
  ) async {
    await showProcessing(
      tester,
      processingRecord(
        actions: const <String>[
          'pause',
          'cancel',
          'reconcile',
          'resume',
          'reprocess',
        ],
      ),
    );
    expect(find.text('Waiting for external result'), findsOneWidget);
    expect(find.textContaining('Blocked:'), findsNothing);
    expect(find.textContaining('operator must reconcile'), findsNothing);
    expect(uiButton(ProcessingDetail.reconcileAction), findsNothing);
    expect(controlEnabled(tester, 'Resume processing'), isFalse);
    expect(controlEnabled(tester, 'Start new run'), isFalse);
    expect(controlEnabled(tester, 'Pause processing'), isTrue);
    expect(controlEnabled(tester, 'Cancel processing'), isTrue);
    expect(
      find.text('Reserved by the processing service until'),
      findsOneWidget,
    );
  });

  testWidgets('the closed processing summary also waits for an active intent', (
    tester,
  ) async {
    await showProcessing(tester, processingRecord(), disclosure: true);
    expect(find.text('Waiting for external result'), findsOneWidget);
    expect(find.textContaining('Processing needs attention'), findsNothing);
  });

  testWidgets(
    'field research retains the plan stage while awaiting its result',
    (tester) async {
      // Workflow.step dispatches FIELD_RESEARCH from plan, then saves intent
      // before it updates the stage. This is a normal production wire state.
      final specimen = processingRecord(
        run: <String, dynamic>{'stage': 'plan'},
      );
      await showProcessing(tester, specimen);
      expect(find.text('Waiting for external result'), findsOneWidget);
      expect(find.textContaining('Blocked:'), findsNothing);
      expect(find.textContaining('operator must reconcile'), findsNothing);
      expect(
        blockersFor(specimen).single.message,
        'Waiting for external result',
      );
      await showProcessing(tester, specimen, disclosure: true);
      expect(find.text('Waiting for external result'), findsOneWidget);
      expect(find.textContaining('Processing needs attention'), findsNothing);
    },
  );

  testWidgets('a dispatched due retry waits for its new external result', (
    tester,
  ) async {
    // A due retry clears its schedule, then persists a fresh intent while
    // retaining retry_scheduled as both stage and status until the reply.
    final specimen = Specimen(<String, dynamic>{
      ...processingRecord(
        status: 'retry_scheduled',
        run: <String, dynamic>{
          'stage': 'retry_scheduled',
          'next_retry_at': null,
        },
      ).data,
      'stage': 'retry_scheduled',
      'blocker': 'external_outcome_unknown',
      'operational_state': 'retry_scheduled',
    });
    await showProcessing(tester, specimen);
    expect(find.text('Waiting for external result'), findsOneWidget);
    expect(find.textContaining('Blocked:'), findsNothing);
    expect(find.textContaining('operator must reconcile'), findsNothing);
    expect(find.text('Next scheduled retry'), findsNothing);
    expect(uiButton('Resume processing'), findsNothing);
    expect(uiButton('Start new run'), findsNothing);
    expect(uiButton(ProcessingDetail.reconcileAction), findsNothing);
    expect(blockersFor(specimen).single.message, 'Waiting for external result');
    await showProcessing(tester, specimen, disclosure: true);
    expect(find.text('Waiting for external result'), findsOneWidget);
    expect(find.textContaining('Processing needs attention'), findsNothing);
  });

  final unsafeIntents = <String, ({String? status, Json run})>{
    'a genuine block with an active lease': (
      status: 'processing_blocked',
      run: <String, dynamic>{'stage': 'processing_blocked'},
    ),
    'a blocked stage with a conflicting running status': (
      status: 'running',
      run: <String, dynamic>{'stage': 'processing_blocked'},
    ),
    'a retry status with a conflicting normal stage': (
      status: 'retry_scheduled',
      run: <String, dynamic>{},
    ),
    'an expired lease': (
      status: 'running',
      run: <String, dynamic>{
        'lease_until': DateTime.now()
            .subtract(const Duration(hours: 1))
            .toUtc()
            .toIso8601String(),
      },
    ),
    'a missing lease': (
      status: 'running',
      run: <String, dynamic>{'lease_until': null},
    ),
    'a malformed lease': (
      status: 'running',
      run: <String, dynamic>{'lease_until': 'not an instant'},
    ),
    'a missing status': (status: null, run: <String, dynamic>{}),
    'a missing stage': (
      status: 'running',
      run: <String, dynamic>{'stage': null},
    ),
    'a dead letter': (
      status: 'running',
      run: <String, dynamic>{'dead_letter': true},
    ),
  };
  for (final entry in unsafeIntents.entries) {
    testWidgets('${entry.key} retains unknown-outcome recovery guidance', (
      tester,
    ) async {
      await showProcessing(
        tester,
        processingRecord(status: entry.value.status, run: entry.value.run),
      );
      expect(find.text('Waiting for external result'), findsNothing);
      expect(find.text('Blocked: Last request may have run'), findsOneWidget);
      expect(find.textContaining('operator must reconcile'), findsOneWidget);
    });
  }

  for (final String cause in <String>[
    'reader_worker_failed',
    'provider_deadline_outcome_unknown',
  ]) {
    for (final bool due in <bool>[false, true]) {
      final String label = due
          ? 'Waiting for automatic retry'
          : 'Retry scheduled';
      Specimen scheduled() => processingRecord(
        status: 'retry_scheduled',
        run: <String, dynamic>{
          'stage': 'retry_scheduled',
          'blocker': cause,
          'lease_until': null,
          'next_retry_at': DateTime.now()
              .add(Duration(minutes: due ? -5 : 5))
              .toUtc()
              .toIso8601String(),
        },
      );

      testWidgets(
        '${due ? 'a due' : 'a future'} $cause retry does not ask for an operator',
        (tester) async {
          await showProcessing(tester, scheduled());
          expect(find.text(label), findsOneWidget);
          expect(find.textContaining('Blocked:'), findsNothing);
          expect(find.textContaining('operator check'), findsNothing);
          expect(find.text('Next scheduled retry'), findsOneWidget);
          expect(uiButton('Resume processing'), findsNothing);
          expect(uiButton('Start new run'), findsNothing);
          expect(uiButton(ProcessingDetail.reconcileAction), findsNothing);
          expect(controlEnabled(tester, 'Pause processing'), isTrue);
          expect(controlEnabled(tester, 'Cancel processing'), isTrue);

          await showProcessing(tester, scheduled(), disclosure: true);
          expect(find.text(label), findsOneWidget);
          expect(
            find.textContaining('Processing needs attention'),
            findsNothing,
          );
        },
      );

      test(
        '${due ? 'due' : 'future'} $cause retry remains an unmet processing gate',
        () {
          final issues = blockersFor(scheduled());
          expect(issues, hasLength(1));
          expect(issues.single.message, label);
          expect(issues.single.isOperational, isTrue);
          expect(issues.single.rawCode, cause);
        },
      );
    }
  }

  test(
    'an active intent remains an unmet processing gate in shared summaries',
    () {
      final issues = blockersFor(processingRecord());
      expect(issues, hasLength(1));
      expect(issues.single.message, 'Waiting for external result');
      expect(issues.single.isOperational, isTrue);
      expect(issues.single.rawCode, 'external_outcome_unknown');
    },
  );

  final unsafeSchedules = <String, Json>{
    'missing retry time': <String, dynamic>{'next_retry_at': null},
    'invalid retry time': <String, dynamic>{'next_retry_at': 'not an instant'},
    'dead letter': <String, dynamic>{'dead_letter': true},
    'unknown effect': <String, dynamic>{'blocker': 'external_outcome_unknown'},
    'unknown intent with a retained schedule': <String, dynamic>{
      'blocker': 'external_outcome_unknown',
      'lease_until': DateTime.now()
          .add(const Duration(hours: 1))
          .toUtc()
          .toIso8601String(),
    },
    'unrecognized failure': <String, dynamic>{
      'blocker': 'future_unknown_failure',
    },
    'cost limit': <String, dynamic>{'blocker': 'cost_budget_exhausted'},
    'contradictory stage': <String, dynamic>{'stage': 'processing_blocked'},
    'retained lease': <String, dynamic>{
      'lease_until': DateTime.now()
          .add(const Duration(hours: 1))
          .toUtc()
          .toIso8601String(),
    },
  };
  for (final entry in unsafeSchedules.entries) {
    testWidgets('a schedule with ${entry.key} keeps its recovery guidance', (
      tester,
    ) async {
      final specimen = processingRecord(
        status: 'retry_scheduled',
        run: <String, dynamic>{
          'stage': 'retry_scheduled',
          'blocker': 'reader_worker_failed',
          'lease_until': null,
          'next_retry_at': DateTime.now()
              .add(const Duration(minutes: 5))
              .toUtc()
              .toIso8601String(),
          ...entry.value,
        },
      );
      await showProcessing(tester, specimen);
      expect(find.text('Retry scheduled'), findsNothing);
      expect(find.text('Waiting for automatic retry'), findsNothing);
      expect(find.textContaining('Blocked:'), findsOneWidget);
      expect(
        blockersFor(specimen).single.message,
        isNot(anyOf('Retry scheduled', 'Waiting for automatic retry')),
      );
    });
  }
}
