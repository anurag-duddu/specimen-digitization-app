// Synthetic records with the production list payload shape. These captures
// exercise scan rhythm and field attention counts in the real app shell.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/widgets/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import 'golden_harness.dart';

List<Specimen> scanQueue() {
  final base = goldenVerifiedSpecimen();
  const issues = <Json>[
    {
      'reason_codes': ['human_approval_required'],
      'validation_findings': [
        {'severity': 'hard', 'message': 'A supported collector is required'},
      ],
    },
    {
      'reason_codes': ['mandatory_unresolved:taxon'],
    },
    {
      'validation_findings': [
        {
          'severity': 'warning',
          'message': 'Check the date against the handwritten collection label',
        },
      ],
    },
    {
      'reason_codes': ['a_future_check:internal_field'],
    },
    {
      'reason_codes': ['human_approval_required'],
    },
  ];
  return [
    for (var i = 0; i < issues.length; i++)
      Specimen({
        ...base.data,
        'specimen_id': 'scan-${i + 1}',
        'filename': 'subject_${105526321 + i}.jpeg',
        'disposition': 'needs_human_review',
        'reason_codes': <String>[],
        'validation_findings': <Json>[],
        'updated_at': '2026-10-20T13:45:00Z',
        ...issues[i],
      }),
  ];
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));
  for (final scenario in [
    (name: 'desktop', window: const Size(1440, 900), scale: 1.0),
    (name: 'desktop', window: const Size(1440, 900), scale: 2.0),
    (name: 'phone', window: const Size(390, 844), scale: 1.0),
    (name: 'phone', window: const Size(390, 844), scale: 2.0),
  ]) {
    for (final selected in [false, true]) {
      testWidgets(
        'five record queue ${scenario.name} text${scenario.scale} selected$selected',
        (tester) async {
          final records = scanQueue();
          expect(records.map(queueReason), [
            'A supported collector is required',
            'Taxon needs a supported value',
            'Check the date against the handwritten collection label',
            'Review the recorded issue',
            '',
          ]);
          await pumpGoldenApp(
            tester,
            window: scenario.window,
            textScale: scenario.scale,
            brightness: Brightness.light,
            location: goldenQueueLocation,
            repository: GoldenQueueRepository(records),
          );
          expect(find.byType(StatusChip), findsNothing);
          expect(find.textContaining('Updated '), findsNothing);
          expect(find.textContaining('mandatory_unresolved'), findsNothing);
          expect(find.text('2 fields to review · 3 missing'), findsWidgets);
          if (selected) {
            await tester.tap(uiButton('Select'));
            await tester.pumpAndSettle();
            final checkbox = find
                .descendant(
                  of: find.byType(SelectableRow),
                  matching: find.byType(UiCheckbox),
                )
                .first;
            await tester.ensureVisible(checkbox);
            await tester.tap(checkbox);
            await tester.pumpAndSettle();
            final pane = tester.getRect(find.byType(QueuePane));
            final footer = tester.getRect(
              find.byKey(const ValueKey('queue-selection-footer')),
            );
            expect(footer.bottom, pane.bottom);
            expect(footer.width, pane.width);
          }
          expect(tester.takeException(), isNull);
          await expectGolden(
            tester,
            'queue-scan__${scenario.name}__text${scenario.scale}__selected$selected',
          );
        },
      );
    }
  }
}
