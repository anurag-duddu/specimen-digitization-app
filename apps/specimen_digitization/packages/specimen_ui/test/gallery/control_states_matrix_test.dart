import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/gallery.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

void main() {
  for (final width in [390.0, 768.0, 1180.0, 1440.0]) {
    for (final brightness in Brightness.values) {
      for (final scale in [1.0, 2.0]) {
        for (final reduced in [false, true]) {
          testWidgets(
            'runtime states $width $brightness scale$scale reduced$reduced',
            (tester) async {
              tester.view.physicalSize = Size(width, 900);
              tester.view.devicePixelRatio = 1;
              addTearDown(tester.view.reset);
              final ui = brightness == Brightness.dark
                  ? UiThemeData.dark()
                  : UiThemeData.light();
              await tester.pumpWidget(
                uiHarness(
                  brightness: brightness,
                  density: width < 1000
                      ? UiDensityMode.touch
                      : UiDensityMode.pointer,
                  textScaler: TextScaler.linear(scale),
                  textDirection: reduced
                      ? TextDirection.rtl
                      : TextDirection.ltr,
                  disableAnimations: reduced,
                  size: Size(width, 900),
                  child: UiTheme(
                    data: ui,
                    child: const SingleChildScrollView(
                      child: Padding(
                        padding: EdgeInsets.all(24),
                        child: UiControlStatesPage(),
                      ),
                    ),
                  ),
                ),
              );
              await tester.pumpAndSettle();
              expect(tester.takeException(), isNull);
              expect(find.byType(BackdropFilter), findsNothing);
              expect(
                find.bySemanticsLabel('Clear original reading'),
                findsNothing,
              );
              final choice = find.byWidgetPredicate(
                (widget) =>
                    widget is Pressable &&
                    widget.semanticsLabel == 'Needs review',
              );
              expect(tester.getSize(choice).height, greaterThanOrEqualTo(48));
              for (final ring in tester.widgetList<FocusRing>(
                find.byType(FocusRing),
              )) {
                expect(ring.radius ?? 0, greaterThanOrEqualTo(0));
              }
            },
          );
        }
      }
    }
  }
}
