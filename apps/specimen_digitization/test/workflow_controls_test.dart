import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/review_context.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import 'workbench_harness.dart';
import 'ui_finders.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_digitization/src/vocabulary.dart';

void main() {
  final fixture =
      jsonDecode(
            File(
              'test/fixtures/backend-next-wire-examples.json',
            ).readAsStringSync(),
          )
          as Json;
  testWidgets(
    'classification separates storage scope from published profile classification and requires reason',
    (tester) async {
      Json? decision;
      final configuration = objects(fixture['collections']['items']).single;
      final scope = CollectionScope(
        organizationId: 'org',
        collectionId: 'storage-uuid',
        name: 'Insects',
        configuration: configuration,
      );
      await tester.pumpWidget(
        workbenchHost(
          Builder(
            builder: (context) => Center(
              child: UiButton(
                label: 'Classify',
                onPressed: () async {
                  decision = await showClassificationForm(
                    context,
                    specimen: Specimen(fixture['workspace_before_selection']),
                    scope: scope,
                  );
                },
              ),
            ),
          ),
        ),
      );
      await tester.tap(uiButton('Classify'));
      await tester.pumpAndSettle();
      final node = objects(
        configuration['classification_nodes'],
      ).firstWhere((n) => n['id'] == 'insects');
      await pickUiSelect(
        tester,
        ClassificationDialog.nodeLabel,
        node['name'] as String,
      );
      final save = uiButton(ClassificationDialog.action);
      await tester.tap(save);
      await tester.pumpAndSettle();
      expect(decision, isNull);
      expect(find.text(reasonRequired), findsOneWidget);
      await tester.enterText(
        uiField('Reason'),
        'Synthetic profile confirmation',
      );
      await tester.tap(save);
      await tester.pumpAndSettle();
      expect(decision!['value'], 'storage-uuid');
      expect(decision!['profile_collection_id'], 'insects');
      expect(decision!['reason'], 'Synthetic profile confirmation');
    },
  );
  testWidgets(
    'outcome-unknown budget and active lease keep retry recovery deliberate',
    (tester) async {
      Json? action;
      await tester.pumpWidget(
        scrollingHost(
          OperationalPanel(
            specimen: Specimen({
              'specimen_id': 's',
              'available_actions': ['resume', 'pause', 'reprocess'],
              'run': {
                'blocker': 'external_outcome_unknown',
                'lease_until': DateTime.now()
                    .add(const Duration(hours: 1))
                    .toUtc()
                    .toIso8601String(),
                'usage': {
                  'actual_cost_micros': null,
                  'reserved_cost_micros': 250,
                },
                'profile': {
                  'execution': {'max_steps': 200},
                },
              },
            }),
            canOperate: true,
            busy: false,
            onAction: (value) async {
              action = value;
            },
          ),
        ),
      );
      expect(find.textContaining('Its result is unknown'), findsOneWidget);
      // A cost the server did not record reads as not recorded, never as
      // zero (blueprint section 8).
      expect(find.text('Not recorded'), findsWidgets);
      expect(find.text('Actual cost'), findsOneWidget);
      // A permitted action that is blocked right now is disabled with the
      // reason on it, never a silent no-op (pass criterion 5.6).
      expect(controlEnabled(tester, 'Resume processing'), isFalse);
      // The reason rides on the control's own node, which is what a screen
      // reader reads and what `Pressable` reports on a press.
      expect(
        disabledReasonOf(tester, 'Resume processing'),
        contains('processing service'),
      );
      expect(action, isNull);
      await tester.ensureVisible(find.text('Pause processing'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Pause processing'));
      await tester.pumpAndSettle();
      final confirm = find.descendant(
        of: find.byType(ReasonForm),
        matching: uiButton('Pause processing'),
      );
      expect(tester.widget<UiButton>(confirm).onPressed, isNull);
      expect(action, isNull);
      await tester.enterText(
        uiField('Reason'),
        'Reconcile synthetic unknown request',
      );
      await tester.pumpAndSettle();
      await tester.tap(confirm);
      await tester.pumpAndSettle();
      expect(action!['action'], 'pause');
    },
  );
}
