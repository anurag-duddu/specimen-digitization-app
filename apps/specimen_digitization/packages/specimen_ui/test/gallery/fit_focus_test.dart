import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/src/gallery/gallery_shell.dart';
import 'package:specimen_ui/src/gallery/pages/fit_page.dart';

import '../harness/control_contract.dart';

void main() {
  testWidgets(
    'fit examples follow the controls actual keyboard focus contour',
    (tester) async {
      FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.alwaysTraditional;
      addTearDown(() {
        FocusManager.instance.highlightStrategy =
            FocusHighlightStrategy.automatic;
      });
      for (final density in UiDensityMode.values) {
        for (final scale in [1.0, 2.0]) {
          await tester.pumpWidget(
            uiHarness(
              density: density,
              textScaler: TextScaler.linear(scale),
              child: const SingleChildScrollView(
                child: Builder(builder: buildFitPage),
              ),
            ),
          );
          await tester.pumpAndSettle();
          for (final type in [UiButton, UiChip]) {
            final section = find.byWidgetPredicate(
              (widget) => widget is GallerySection && widget.title == '$type',
            );
            final controls = find.descendant(
              of: section,
              matching: find.byType(type),
            );
            expect(controls, findsNWidgets(8));
            // Each column draws the resting control, then the focus specimen.
            for (var i = 1; i < controls.evaluate().length; i += 2) {
              final control = controls.at(i);
              final nativeRing = find.descendant(
                of: control,
                matching: find.byType(FocusRing),
              );
              final cell = find
                  .ancestor(of: control, matching: find.byType(Stack))
                  .first;
              final displayedRing = find
                  .descendant(
                    of: cell,
                    matching: find.byWidgetPredicate(
                      (widget) => widget is FocusRing && widget.visible,
                    ),
                  )
                  .last;
              final displayed = tester.widget<FocusRing>(displayedRing);
              final displayedBounds = tester.getRect(displayedRing);
              Focus.of(tester.element(nativeRing)).requestFocus();
              await tester.pumpAndSettle();
              final native = tester.widget<FocusRing>(nativeRing);
              expect(native.visible, isTrue);
              expect(displayed.shape, native.shape);
              expect(displayed.radius, native.radius);
              expect(
                displayedBounds.size,
                tester.getRect(nativeRing).size,
                reason:
                    '$type at $scale in $density must ring paint, not hit slop',
              );
              expect(tester.getRect(displayedRing), tester.getRect(nativeRing));
              final scroll = find
                  .ancestor(
                    of: displayedRing,
                    matching: find.byType(SingleChildScrollView),
                  )
                  .first;
              final viewport = tester.getRect(scroll);
              final ui = tester.element(nativeRing).ui;
              final painted = tester
                  .getRect(displayedRing)
                  .inflate(ui.shape.stroke.focusGap + ui.shape.stroke.focus);
              expect(painted.top, greaterThanOrEqualTo(viewport.top));
              expect(painted.bottom, lessThanOrEqualTo(viewport.bottom));
              if (i == 1) {
                expect(painted.left, greaterThanOrEqualTo(viewport.left));
              }
              expect(tester.takeException(), isNull);
            }
          }
        }
      }
    },
  );
}
