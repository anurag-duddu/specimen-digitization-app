import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/operational_panel.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'ui_finders.dart';
import 'widget_test.dart' show fixture;
import 'workbench_harness.dart';

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
      useWindow(tester, largeWindow);
      await tester.pumpWidget(
        workbenchHost(
          ReviewWorkbench(
            specimen: specimen,
            onChange: (_) async => fail('No mutation requested'),
            onRetry: (_) async => fail('No replay permitted'),
            onRefresh: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(controlEnabled(tester, 'Correct label regions'), isFalse);
      expect(controlEnabled(tester, 'Approve record'), isFalse);
      expect(controlEnabled(tester, 'Confirm label coverage'), isTrue);
      expect(find.text('Start new run'), findsNothing);
      expect(specimen.data['disposition'], isNull);
      expect(specimen.data['observations'], fixture.data['observations']);
    },
  );

  testWidgets(
    'pilot blocker explains evidence review without offering replay',
    (tester) async {
      await tester.pumpWidget(
        scrollingHost(
          OperationalPanel(
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
      );
      expect(
        find.textContaining('Pilot evidence review needed.'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Risk is not measured and clearance is blocked'),
        findsOneWidget,
      );
      expect(find.text('Resume processing'), findsNothing);
      expect(find.text('Start new run'), findsNothing);
    },
  );
}
