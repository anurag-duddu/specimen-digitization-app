import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  const title = 'Save corrections to this specimen?';
  for (final sheet in [false, true]) {
    testWidgets(
      '${sheet ? "sheet" : "dialog"} leaves a bounded custom viewport below a long heading',
      (tester) async {
        for (final direction in TextDirection.values) {
          var saved = false;
          final body = ListView(
            children: [for (var i = 0; i < 20; i++) Text('Entry $i')],
          );
          final primary = UiButton(
            label: 'Save',
            onPressed: () => saved = true,
          );
          final secondary = UiButton(
            label: 'Cancel',
            variant: UiButtonVariant.secondary,
            onPressed: () {},
          );
          await tester.pumpWidget(
            uiHarness(
              textDirection: direction,
              textScaler: const TextScaler.linear(4),
              child: SizedBox(
                width: 320,
                height: 200,
                child: sheet
                    ? UiSheet(
                        title: title,
                        scrollBody: false,
                        primaryAction: primary,
                        secondaryAction: secondary,
                        child: body,
                      )
                    : UiDialog(
                        title: title,
                        scrollBody: false,
                        primaryAction: primary,
                        secondaryAction: secondary,
                        child: body,
                      ),
              ),
            ),
          );
          await tester.pump();
          expect(tester.takeException(), isNull);
          expect(tester.getSize(find.byType(ListView)).height, greaterThan(0));
          expect(
            find.ancestor(
              of: find.byType(ListView),
              matching: find.byType(SingleChildScrollView),
            ),
            findsNothing,
          );
          final scroller = tester.state<ScrollableState>(
            find.descendant(
              of: find.byType(ListView),
              matching: find.byType(Scrollable),
            ),
          );
          scroller.position.jumpTo(scroller.position.maxScrollExtent);
          await tester.pump();
          expect(scroller.position.pixels, greaterThan(0));
          await tester.ensureVisible(find.text('Save'));
          await tester.tap(find.text('Save'));
          expect(saved, isTrue);
          expect(tester.takeException(), isNull);
        }
      },
    );

    testWidgets(
      '${sheet ? "sheet" : "dialog"} keeps a complete heading and reachable actions',
      (tester) async {
        for (final direction in TextDirection.values) {
          for (final scale in [1.0, 2.0, 4.0]) {
            for (final height in [568.0, 300.0]) {
              var saved = false;
              final primary = UiButton(
                label: 'Save',
                onPressed: () => saved = true,
              );
              final secondary = UiButton(
                label: 'Cancel',
                variant: UiButtonVariant.secondary,
                onPressed: () {},
              );
              final content = Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (var i = 0; i < 12; i++) Text('Evidence row $i'),
                ],
              );
              await tester.pumpWidget(
                uiHarness(
                  textDirection: direction,
                  textScaler: TextScaler.linear(scale),
                  disableAnimations: true,
                  child: SizedBox(
                    width: 320,
                    height: height,
                    child: sheet
                        ? UiSheet(
                            title: title,
                            primaryAction: primary,
                            secondaryAction: secondary,
                            child: content,
                          )
                        : UiDialog(
                            title: title,
                            primaryAction: primary,
                            secondaryAction: secondary,
                            child: content,
                          ),
                  ),
                ),
              );
              await tester.pump();
              final heading = tester.renderObject<RenderParagraph>(
                find.descendant(
                  of: find.text(title),
                  matching: find.byType(RichText),
                ),
              );
              expect(
                heading.didExceedMaxLines,
                isFalse,
                reason:
                    '$sheet / $direction / $scale / $height: a contextual title must remain readable',
              );
              expect(
                heading.size.height,
                greaterThan(heading.preferredLineHeight),
              );
              expect(tester.takeException(), isNull);
              await tester.ensureVisible(find.text('Save'));
              await tester.tap(find.text('Save'));
              await tester.pump();
              expect(saved, isTrue);
              await tester.ensureVisible(find.text('Evidence row 11'));
              await tester.pump();
              expect(
                find.text('Evidence row 11').hitTestable(),
                findsOneWidget,
              );
              expect(tester.takeException(), isNull);
            }
          }
        }
      },
    );
  }
}
