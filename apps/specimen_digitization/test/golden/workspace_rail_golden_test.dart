// Real application composition on synthetic data, with explicit input platforms.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../ui_finders.dart';
import 'golden_harness.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  for (final brightness in Brightness.values) {
    testWidgets(
      'pointer rail and docked collection header ${brightness.name}',
      (tester) async {
        await pumpGoldenApp(
          tester,
          window: const Size(1440, 900),
          brightness: brightness,
          location: goldenSpecimenLocation,
        );
        final rail = find.byType(UiRail);
        expect(rail, findsOneWidget);
        expect(
          find.descendant(of: rail, matching: find.text('Specimens')),
          findsNothing,
        );
        expect(uiIconButton('Hide queue').hitTestable(), findsOneWidget);
        expect(tester.takeException(), isNull);
        await expectGolden(tester, 'workspace-rail-pointer-${brightness.name}');
      },
      variant: TargetPlatformVariant({TargetPlatform.macOS}),
    );
  }

  for (final scale in [1.0, 2.0]) {
    for (final open in [false, true]) {
      testWidgets(
        'touch rail and collection header at text $scale open $open',
        (tester) async {
          await pumpGoldenApp(
            tester,
            // Large text switches a 1024 px window to compact navigation.
            // Exercise the rail above its scaled docking threshold instead.
            window: Size(scale == 1.0 ? 1024 : 1600, 1180),
            brightness: Brightness.light,
            textScale: scale,
            location: goldenSpecimenLocation,
          );
          final rail = find.byType(UiRail);
          for (final label in ['Specimens', 'Intake', 'Account']) {
            expect(
              find.descendant(of: rail, matching: find.text(label)),
              findsOneWidget,
            );
          }
          expect(tester.takeException(), isNull);
          if (open) {
            await tester.tap(uiIconButton('Show queue'));
            await tester.pumpAndSettle();
            expect(uiIconButton('Hide queue').hitTestable(), findsOneWidget);
            expect(tester.takeException(), isNull);
          }
          await expectGolden(
            tester,
            open
                ? 'workspace-rail-touch-panel-text$scale'
                : 'workspace-rail-touch-text$scale',
          );
        },
        variant: TargetPlatformVariant({TargetPlatform.android}),
      );
    }
  }
}
