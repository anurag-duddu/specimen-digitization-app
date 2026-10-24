import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

void main() {
  testWidgets('hero keeps readable content separate from decorative gradient', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiBrandHero(
          eyebrow: 'Specimen Digitization',
          title: 'From specimens to knowledge.',
          description: 'A modern platform for museum collections.',
        ),
      ),
    );
    final Finder accent = find.byType(UiBrandAccent);
    expect(accent, findsOneWidget);
    expect(
      find.descendant(of: accent, matching: find.byType(Text)),
      findsNothing,
    );
    expect(
      tester
          .getSemantics(find.text('From specimens to knowledge.'))
          .getSemanticsData()
          .flagsCollection
          .isHeader,
      isTrue,
    );
    expect(
      tester.getRect(accent).bottom,
      lessThan(tester.getRect(find.text('Specimen Digitization')).top),
    );
    semantics.dispose();
  });

  testWidgets('hero actions remain operable at narrow width and large text', (
    WidgetTester tester,
  ) async {
    int calls = 0;
    for (final Brightness mode in Brightness.values) {
      for (final TextDirection direction in TextDirection.values) {
        for (final double width in <double>[320, 390, 768, 1180, 1440]) {
          tester.view.physicalSize = Size(width, 1200);
          tester.view.devicePixelRatio = 1;
          await tester.pumpWidget(
            uiHarness(
              brightness: mode,
              textDirection: direction,
              textScaler: const TextScaler.linear(2),
              child: SingleChildScrollView(
                child: UiBrandHero(
                  eyebrow: 'Specimen Digitization',
                  title: 'From specimens to knowledge.',
                  description:
                      'Digitize, enrich, and explore your collections.',
                  actions: <Widget>[
                    UiButton(label: 'Explore', onPressed: () => calls++),
                    UiButton(label: 'Learn more', onPressed: () {}),
                  ],
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          expect(
            tester.takeException(),
            isNull,
            reason: '$mode $direction $width',
          );
          final int before = calls;
          await tester.tap(find.text('Explore'));
          expect(calls, before + 1);
        }
      }
    }
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  });
}
