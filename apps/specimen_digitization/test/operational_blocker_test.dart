import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';

import 'workbench_harness.dart';

/// The processing panel judges a run whose automatic retries ran out
/// (`retry_budget_exhausted:<cause>`) by its cause, never by the word
/// "budget" in that prefix.
void main() {
  const String costLimit = 'Processing stopped at a cost limit.';
  const String sourceUnreachable =
      'An approved source could not be reached after repeated attempts. '
      'Retry later, or ask an administrator.';

  Future<void> show(WidgetTester tester, String blocker) async {
    await tester.pumpWidget(
      scrollingHost(
        OperationalPanel(
          specimen: Specimen(<String, dynamic>{
            'specimen_id': 's',
            'available_actions': <String>['reprocess'],
            'run': <String, dynamic>{
              'blocker': blocker,
              'dead_letter': blocker.startsWith('retry_budget_exhausted:'),
              'attempts': <String, dynamic>{'field_research': 3},
            },
          }),
          canOperate: true,
          busy: false,
          onAction: (_) async {},
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('retries that stopped on an unreachable source say so, '
      'never a cost limit', (tester) async {
    await show(tester, 'retry_budget_exhausted:lookup_operational_failure');
    expect(find.text(sourceUnreachable), findsOneWidget);
    expect(find.text(costLimit), findsNothing);
    expect(find.text('Automatic retries have stopped.'), findsOneWidget);
  });

  testWidgets('a real cost limit keeps its own words', (tester) async {
    await show(tester, 'cost_budget_exhausted');
    expect(find.text(costLimit), findsOneWidget);
    expect(find.text(sourceUnreachable), findsNothing);
  });

  testWidgets('retries that stopped on a model error claim neither', (
    tester,
  ) async {
    await show(tester, 'retry_budget_exhausted:field_research_model_error');
    expect(find.text(costLimit), findsNothing);
    expect(find.text(sourceUnreachable), findsNothing);
    expect(find.text('Automatic retries have stopped.'), findsOneWidget);
  });
}
