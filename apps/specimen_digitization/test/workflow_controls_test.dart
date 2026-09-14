import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/review_context.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';

import 'workbench_harness.dart';

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
              child: FilledButton(
                onPressed: () async {
                  decision = await showDialog<Json>(
                    context: context,
                    builder: (_) => ClassificationDialog(
                      specimen: Specimen(fixture['workspace_before_selection']),
                      scope: scope,
                    ),
                  );
                },
                child: const Text('Classify'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Classify'));
      await tester.pumpAndSettle();
      final dropdown = find.byType(DropdownButtonFormField<String>);
      await tester.tap(dropdown);
      await tester.pumpAndSettle();
      final node = objects(
        configuration['classification_nodes'],
      ).firstWhere((n) => n['id'] == 'insects');
      await tester.tap(find.text(node['name']).last);
      await tester.pumpAndSettle();
      final save = find.byType(FilledButton).last;
      await tester.tap(save);
      await tester.pumpAndSettle();
      expect(decision, isNull);
      await tester.enterText(
        find.byType(TextFormField).last,
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
      expect(buttonWithLabel(tester, 'Resume processing').onPressed, isNull);
      expect(
        find
            .ancestor(
              of: find.text('Resume processing'),
              matching: find.byType(Tooltip),
            )
            .evaluate()
            .map((e) => (e.widget as Tooltip).message)
            .whereType<String>()
            .any((m) => m.contains('processing service')),
        isTrue,
      );
      expect(action, isNull);
      await tester.ensureVisible(find.text('Pause processing'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Pause processing'));
      await tester.pumpAndSettle();
      final confirm = find.descendant(
        of: find.byType(ReasonForm),
        matching: find.widgetWithText(FilledButton, 'Pause processing'),
      );
      expect(tester.widget<FilledButton>(confirm).onPressed, isNull);
      expect(action, isNull);
      await tester.enterText(
        find.widgetWithText(TextField, 'Reason'),
        'Reconcile synthetic unknown request',
      );
      await tester.pumpAndSettle();
      await tester.tap(confirm);
      await tester.pumpAndSettle();
      expect(action!['action'], 'pause');
    },
  );
}
