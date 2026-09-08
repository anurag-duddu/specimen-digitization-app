import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/review_context.dart';
import 'package:specimen_digitization/src/operational_panel.dart';

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
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: FilledButton(
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
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: OperationalPanel(
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
          ),
        ),
      );
      expect(find.textContaining('Its outcome is unknown'), findsOneWidget);
      expect(find.textContaining('Actual cost: Not measured'), findsOneWidget);
      final resume = find.ancestor(
        of: find.text('Resume processing'),
        matching: find.byWidgetPredicate((w) => w is OutlinedButton),
      );
      expect(tester.widget<OutlinedButton>(resume).onPressed, isNull);
      expect(action, isNull);
      await tester.ensureVisible(find.text('Pause processing'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Pause processing'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(FilledButton));
      await tester.pumpAndSettle();
      expect(action, isNull);
      expect(find.text('A reason is required.'), findsOneWidget);
      await tester.enterText(
        find.byType(TextFormField),
        'Reconcile synthetic unknown request',
      );
      await tester.tap(find.byType(FilledButton));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(milliseconds: 300));
      expect(action!['action'], 'pause');
    },
  );
}
