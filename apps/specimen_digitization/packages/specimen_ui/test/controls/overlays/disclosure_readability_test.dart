import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  for (final scale in [1.0, 2.0]) {
    for (final direction in TextDirection.values) {
      for (final withChip in [false, true]) {
        testWidgets('complete collapsed question at 320px, ${scale}x, '
            '${direction.name}, chip=$withChip', (tester) async {
          tester.view.physicalSize = const Size(320, 900);
          tester.view.devicePixelRatio = 1;
          addTearDown(tester.view.reset);
          const question =
              'Where does the evidence live after the specimen has been reviewed?';
          const answer = 'The record retains its evidence and review history.';
          final changes = <bool>[];
          await tester.pumpWidget(
            uiHarness(
              size: const Size(320, 900),
              textScaler: TextScaler.linear(scale),
              textDirection: direction,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: UiDisclosure(
                  title: question,
                  trailing: withChip ? const UiChip(label: 'Guide') : null,
                  onExpansionChanged: changes.add,
                  child: const Text(answer),
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();

          void expectCompleteQuestion() {
            final paragraph = tester.renderObject<RenderParagraph>(
              find.descendant(
                of: find.text(question),
                matching: find.byType(RichText),
              ),
            );
            final complete = TextPainter(
              text: paragraph.text,
              textDirection: direction,
              textScaler: paragraph.textScaler,
              strutStyle: paragraph.strutStyle,
            )..layout(maxWidth: paragraph.size.width);
            expect(complete.computeLineMetrics().length, greaterThan(1));
            expect(paragraph.didExceedMaxLines, isFalse);
            expect(
              paragraph.size.height,
              greaterThanOrEqualTo(complete.height - .01),
              reason: 'The complete question must be visible before opening.',
            );
            complete.dispose();
            final titleBounds = tester.getRect(find.text(question));
            final headerBounds = tester.getRect(find.byType(Pressable));
            expect(titleBounds.top, greaterThanOrEqualTo(headerBounds.top));
            expect(titleBounds.bottom, lessThanOrEqualTo(headerBounds.bottom));
            if (withChip) {
              expect(
                tester.getRect(find.byType(UiChip)).top,
                greaterThanOrEqualTo(titleBounds.bottom),
                reason:
                    'The status chip must not squeeze or cover the question.',
              );
            }
          }

          expect(find.text(answer), findsNothing);
          expectCompleteQuestion();
          await tester.tap(find.text(question));
          await tester.pumpAndSettle();
          expect(find.text(answer), findsOneWidget);
          expectCompleteQuestion();

          await tester.sendKeyEvent(LogicalKeyboardKey.tab);
          await tester.sendKeyEvent(LogicalKeyboardKey.enter);
          await tester.pumpAndSettle();
          expect(find.text(answer), findsNothing);
          expect(changes, [true, false]);
          expectCompleteQuestion();
          expect(tester.takeException(), isNull);
        });
      }
    }
  }
}
