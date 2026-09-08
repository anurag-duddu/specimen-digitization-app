import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'widget_test.dart' show fixture;

void main() {
  testWidgets(
    'pilot server actions permit evidence correction but never approval or geometry',
    (tester) async {
      final specimen = Specimen({
        ...fixture.data,
        'operational_state': 'processing_blocked',
        'disposition': null,
        'run': {'blocker': 'pilot_evidence_review_required'},
        'available_actions': [
          'field',
          'transcription',
          'reading_metadata',
          'coverage',
        ],
      });
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ReviewWorkbench(
              specimen: specimen,
              onChange: (_) async => fail('No mutation requested'),
              onRetry: (_) async => fail('No replay permitted'),
              onRefresh: () {},
            ),
          ),
        ),
      );
      ButtonStyleButton button(String label) =>
          tester.widget<ButtonStyleButton>(
            find
                .ancestor(
                  of: find.text(label),
                  matching: find.byWidgetPredicate(
                    (w) => w is ButtonStyleButton,
                  ),
                )
                .first,
          );
      expect(button('Correct label regions').onPressed, isNull);
      expect(button('Record review approval').onPressed, isNull);
      expect(button('Confirm label coverage').onPressed, isNotNull);
      expect(find.text('Start new run'), findsNothing);
      expect(specimen.data['disposition'], isNull);
      expect(specimen.data['observations'], fixture.data['observations']);
    },
  );

  testWidgets(
    'pilot blocker explains evidence review without offering replay',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: OperationalPanel(
              specimen: const Specimen({
                'operational_state': 'processing_blocked',
                'disposition': null,
                'run': {'blocker': 'pilot_evidence_review_required'},
                'available_actions': [
                  'field',
                  'transcription',
                  'reading_metadata',
                  'coverage',
                ],
              }),
              canOperate: true,
              busy: false,
              onAction: (_) async {
                fail('No run action authorized');
              },
            ),
          ),
        ),
      );
      expect(
        find.textContaining('Pilot evidence review needed.'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Risk is unmeasured and clearance is blocked'),
        findsOneWidget,
      );
      expect(find.text('Resume processing'), findsNothing);
      expect(find.text('Start new run'), findsNothing);
    },
  );
}
