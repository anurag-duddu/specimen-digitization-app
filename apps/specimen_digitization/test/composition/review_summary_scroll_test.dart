import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/screens/workbench/decision_bar.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/workbench.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../golden/golden_harness.dart';
import '../workbench_harness.dart';

void main() {
  for (final (window, scale) in [
    (const Size(1000, 400), 1.0),
    (const Size(1000, 500), 1.0),
    (const Size(2000, 600), 2.0),
    (const Size(2000, 900), 2.0),
  ]) {
    for (final dark in [false, true]) {
      testWidgets(
        'two-pane review scrolls its summary and reaches decisions at '
        '$window, ${scale}x, dark $dark',
        (tester) async {
          useWindow(tester, window);
          final initial = goldenSpecimen();
          final record = Specimen({
            ...initial.data,
            'fields': [
              ...initial.fields,
              for (var index = 0; index < 10; index++)
                {
                  'field_key': 'review_field_$index',
                  'display_name': 'Review field $index',
                  'required': true,
                  'state': 'unknown',
                },
            ],
          });
          await tester.pumpWidget(
            workbenchHost(
              Builder(
                builder: (context) => MediaQuery(
                  data: MediaQuery.of(
                    context,
                  ).copyWith(textScaler: TextScaler.linear(scale)),
                  child: ReviewWorkbench(
                    specimen: record,
                    onChange: (_) async => false,
                    onRetry: (_) async {},
                    onRefresh: () {},
                  ),
                ),
              ),
              theme: dark ? AppTheme.dark() : AppTheme.light(),
            ),
          );
          await tester.pumpAndSettle();
          await settleImages(tester);

          final source = find.byKey(
            const ValueKey<String>('review-source-surface'),
          );
          final inspector = find.byKey(
            const ValueKey<String>('review-inspector-surface'),
          );
          expect(source, findsOneWidget);
          expect(inspector, findsOneWidget);
          final sourceBefore = tester.getRect(source);
          expect(sourceBefore.right, lessThan(tester.getRect(inspector).left));
          expect(sourceBefore.height, greaterThan(120));

          final scroll = find.byKey(evidenceScrollKey);
          expect(
            find.descendant(of: scroll, matching: find.byType(Scrollable)),
            findsOneWidget,
            reason: 'the summary and fields share one vertical scroll owner',
          );
          final overview = find.byKey(
            const ValueKey<String>('review-overview'),
          );
          final overviewBefore = tester.getTopLeft(overview);
          await tester.drag(scroll, const Offset(0, -200));
          await tester.pumpAndSettle();
          expect(tester.getTopLeft(overview).dy, lessThan(overviewBefore.dy));
          expect(tester.getRect(source), sourceBefore);

          final lastField = find.text('Review field 9');
          await tester.ensureVisible(lastField);
          await tester.pumpAndSettle();
          expect(lastField.hitTestable(), findsOneWidget);
          final decision = find.byType(WorkbenchDecisionBar);
          await tester.ensureVisible(decision);
          await tester.pumpAndSettle();
          expect(decision.hitTestable(), findsOneWidget);
          expect(
            find.widgetWithText(UiButton, 'Approve record').hitTestable(),
            findsOneWidget,
          );
          expect(tester.getRect(source), sourceBefore);
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox.shrink());
        },
      );
    }
  }
}
