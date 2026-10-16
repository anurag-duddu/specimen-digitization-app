import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';
import 'workbench_harness.dart';

void main() {
  const label = 'Reassess locations';

  Future<void> show(
    WidgetTester tester, {
    bool offered = true,
    bool canOperate = true,
    DateTime? lease,
    List<Json>? sent,
  }) async {
    await tester.pumpWidget(
      scrollingHost(
        OperationalPanel(
          specimen: Specimen(<String, dynamic>{
            'specimen_id': 'retained-location-record',
            'available_actions': <String>[if (offered) 'reassess_locations'],
            'run': <String, dynamic>{
              'stage': 'finalized',
              'lease_until': lease?.toUtc().toIso8601String(),
              'attempts': <String, dynamic>{'field_research': 2},
            },
          }),
          canOperate: canOperate,
          busy: false,
          onAction: (Json change) async => sent?.add(change),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('requires server permission and an operator', (tester) async {
    await show(tester, offered: false);
    expect(uiButton(label), findsNothing);
    await show(tester, canOperate: false);
    expect(uiButton(label), findsNothing);
  });

  testWidgets('cannot reassess while an external request is leased', (
    tester,
  ) async {
    await show(tester, lease: DateTime.now().add(const Duration(hours: 1)));
    final button = tester.widget<UiButton>(uiButton(label));
    expect(button.onPressed, isNull);
    expect(button.disabledReason, contains('holds this run'));
  });

  testWidgets('explains same-run research and sends one reasoned action', (
    tester,
  ) async {
    final sent = <Json>[];
    await show(tester, sent: sent);
    await tester.tap(uiButton(label));
    await tester.pumpAndSettle();
    expect(
      find.text(
        'The location fields are researched together using saved label '
        'readings. Another processing attempt may incur a charge.',
      ),
      findsOneWidget,
    );
    expect(
      find.text(
        'Reviewer decisions, earlier evidence and recorded usage are kept. '
        'The existing spending limits still apply.',
      ),
      findsOneWidget,
    );
    final confirm = find.descendant(
      of: find.byType(ReasonForm),
      matching: uiButton(label),
    );
    expect(tester.widget<UiButton>(confirm).onPressed, isNull);
    await tester.enterText(uiField('Reason'), 'Recheck the location hierarchy');
    await tester.pumpAndSettle();
    await tester.tap(confirm);
    await tester.pumpAndSettle();
    expect(sent, <Json>[
      <String, dynamic>{
        'kind': 'run_action',
        'action': 'reassess_locations',
        'reason': 'Recheck the location hierarchy',
      },
    ]);
    expect(find.byType(ReasonForm), findsNothing);
  });
}
