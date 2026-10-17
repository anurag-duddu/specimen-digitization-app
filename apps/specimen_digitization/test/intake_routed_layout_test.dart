// Exercise Intake inside the real router and collection header. A bare screen
// cannot detect a safe area being consumed by both the header and scaffold.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_digitization/src/app/shell.dart';
import 'package:specimen_digitization/src/intake.dart';
import 'package:specimen_digitization/src/screens/intake/capture_card.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'golden/golden_harness.dart';
import 'ui_finders.dart';

final Finder _collection = find.byKey(
  const ValueKey<String>('collection-sheet-trigger'),
);
final Finder _title = find.descendant(
  of: find.byType(IntakeScreen),
  matching: find.text(intakeTitle),
);
final Finder _header = find.byWidgetPredicate(
  (widget) => widget is PinnedChrome && widget.region == UiPinnedRegion.topBar,
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  for (final platform in <TargetPlatform>[
    TargetPlatform.iOS,
    TargetPlatform.android,
  ]) {
    for (final scenario in <({Size window, double scale, Brightness mode})>[
      (window: const Size(390, 844), scale: 1, mode: Brightness.light),
      (window: const Size(390, 844), scale: 1.3, mode: Brightness.dark),
      (window: const Size(320, 844), scale: 2, mode: Brightness.light),
      (window: const Size(700, 1000), scale: 1, mode: Brightness.dark),
      (window: const Size(900, 1000), scale: 1.3, mode: Brightness.light),
      (window: const Size(1180, 820), scale: 2, mode: Brightness.dark),
      (window: const Size(844, 390), scale: 1, mode: Brightness.light),
    ]) {
      testWidgets('$platform routed Intake matches Specimens header spacing '
          'at ${scenario.window}, text ${scenario.scale}, ${scenario.mode}', (
        tester,
      ) async {
        final landscape = scenario.window.height < scenario.window.width;
        final insets = landscape
            ? const FakeViewPadding(left: 44, right: 24, bottom: 21)
            : const FakeViewPadding(top: 44, bottom: 34);
        tester.view.padding = insets;
        tester.view.viewPadding = insets;
        await pumpGoldenApp(
          tester,
          window: scenario.window,
          textScale: scenario.scale,
          brightness: scenario.mode,
          location: goldenIntakeLocation,
        );
        // Larger windows start in pointer density. Match the touch input used
        // for the destination tabs before comparing the two header heights.
        await tester.tap(_title);
        await tester.pumpAndSettle();
        final context = tester.element(find.byType(IntakeScreen));
        final ui = context.ui;
        final title = tester.getRect(_title);
        final collection = tester.getRect(_collection);
        final header = tester.getRect(_header);
        final intake = tester.getRect(find.byType(IntakeScreen));
        expect(AppSidebarScope.maybeOf(context)!.mobileNavigation, isTrue);
        expect(
          collection.top,
          insets.top + ui.space.s2,
          reason: 'the collection header clears the system inset once',
        );
        expect(
          intake.top,
          header.bottom,
          reason: 'no second system inset belongs below the header',
        );
        expect(title.top - header.bottom, ui.space.s2);
        expect(title.left, greaterThanOrEqualTo(insets.left));
        expect(
          title.right,
          lessThanOrEqualTo(scenario.window.width - insets.right),
        );
        final semantics = tester.ensureSemantics();
        try {
          expect(tester.getSemantics(_title).flagsCollection.isHeader, isTrue);
        } finally {
          semantics.dispose();
        }
        for (final key in <String>[
          'intake-take-photograph',
          'intake-choose-files',
        ]) {
          final control = find.byKey(ValueKey<String>(key));
          await tester.ensureVisible(control);
          await tester.pumpAndSettle();
          expect(control.hitTestable(), findsOneWidget);
          expect(
            tester.getSize(control).height,
            greaterThanOrEqualTo(ui.space.targetMin),
          );
        }

        await tester.tap(uiDestination('Specimens'));
        await tester.pumpAndSettle();
        final specimensCollection = tester.getRect(_collection);
        final search = tester.getRect(uiField('Search by specimen ID'));
        expect(specimensCollection.top, collection.top);
        expect(specimensCollection.height, collection.height);
        expect(
          title.top - collection.bottom,
          search.top - specimensCollection.bottom,
          reason: 'both first regions use the same gap below collection',
        );
        await tester.tap(uiDestination('Intake'));
        await tester.pumpAndSettle();
        final scroll = find.descendant(
          of: find.byType(IntakeScreen),
          matching: find.byType(CustomScrollView),
        );
        expect(scroll, findsOneWidget);
        await tester.drag(scroll, const Offset(0, 1600));
        await tester.pumpAndSettle();
        expect(tester.getRect(_title).top, title.top);
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
      }, variant: TargetPlatformVariant(<TargetPlatform>{platform}));
    }
  }

  testWidgets('routed desktop Intake keeps its constraint-derived gutter', (
    tester,
  ) async {
    await pumpGoldenApp(
      tester,
      window: const Size(1440, 1000),
      brightness: Brightness.light,
      location: goldenIntakeLocation,
    );
    for (final window in <Size>[
      const Size(1440, 1000),
      const Size(900, 1000),
      const Size(1700, 1200),
    ]) {
      tester.view.physicalSize = window;
      await tester.pumpAndSettle();
      final context = tester.element(find.byType(IntakeScreen));
      expect(AppSidebarScope.maybeOf(context)!.mobileNavigation, isFalse);
      final intake = tester.getRect(find.byType(IntakeScreen));
      final title = tester.getRect(_title);
      final layout = UiLayoutMetrics.fromConstraints(
        BoxConstraints.tight(intake.size),
        textScaler: MediaQuery.textScalerOf(context),
      );
      expect(title.top - intake.top, layout.gutter);
      expect(title.left - intake.left, layout.gutter);
      expect(tester.takeException(), isNull);
    }
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
