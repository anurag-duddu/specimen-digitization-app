// `UiBanner` (10 section 4.3).

import 'dart:ui' show Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

const String _message = 'Test environment. Not approved museum records.';
const String _detail =
    'Each reading names the model and provider that produced it.';

void main() {
  testWidgets('every tone builds and takes its fill from its status', (
    WidgetTester tester,
  ) async {
    for (final UiBannerTone tone in UiBannerTone.values) {
      await tester.pumpWidget(
        uiHarness(child: UiBanner(message: _message, tone: tone)),
      );
      await tester.pumpAndSettle();
      expect(find.text(_message), findsOneWidget, reason: tone.name);

      final UiThemeData ui = UiThemeData.light();
      final UiBannerStyle style = UiBannerStyle.resolve(ui, tone);
      final DecoratedBox strip = tester.widget<DecoratedBox>(
        find.descendant(
          of: find.byType(UiBanner),
          matching: find.byType(DecoratedBox),
        ),
      );
      final BoxDecoration paint = strip.decoration as BoxDecoration;
      expect(paint.color, style.fill, reason: tone.name);
      expect(
        paint.border,
        tone == UiBannerTone.info ? isNotNull : isNull,
        reason:
            'only the informational band needs an edge: every other tone is '
            'separated by its own status fill',
      );
    }
  });

  testWidgets('the second line is behind a disclosure that reports expanded', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiBanner(
          message: _message,
          tone: UiBannerTone.synthetic,
          detail: _detail,
        ),
      ),
    );
    expect(find.text(_detail), findsNothing);

    SemanticsData control(String label) =>
        tester.getSemantics(find.bySemanticsLabel(label)).getSemanticsData();
    expect(
      control(UiBanner.defaultDetailLabel).flagsCollection.isExpanded,
      Tristate.isFalse,
    );

    await tester.tap(find.bySemanticsLabel(UiBanner.defaultDetailLabel));
    await tester.pumpAndSettle();
    expect(find.text(_detail), findsOneWidget);
    expect(
      control(UiBanner.defaultDetailLabel).flagsCollection.isExpanded,
      Tristate.isTrue,
      reason:
          'the control keeps its name in both states and moves the flag, '
          'which is the WAI-ARIA disclosure pattern',
    );

    await tester.tap(find.bySemanticsLabel(UiBanner.defaultDetailLabel));
    await tester.pumpAndSettle();
    expect(find.text(_detail), findsNothing);
    handle.dispose();
  });

  testWidgets('the dismiss control reports the condition is over', (
    WidgetTester tester,
  ) async {
    int dismissed = 0;
    await tester.pumpWidget(
      uiHarness(
        child: UiBanner(
          message: _message,
          onDismiss: () => dismissed++,
          dismissLabel: 'Hide this banner',
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('Hide this banner'));
    await tester.pumpAndSettle();
    expect(dismissed, 1);
  });

  testWidgets('the message is a live region and the second line is not', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiBanner(
          message: _message,
          tone: UiBannerTone.synthetic,
          detail: _detail,
        ),
      ),
    );
    expect(find.byType(Announcer), findsOneWidget);
    final SemanticsData data = tester
        .getSemantics(find.byType(Announcer))
        .getSemanticsData();
    expect(data.flagsCollection.isLiveRegion, isTrue);
    expect(data.label, _message);

    await tester.tap(find.bySemanticsLabel(UiBanner.defaultDetailLabel));
    await tester.pumpAndSettle();
    expect(
      tester.getSemantics(find.byType(Announcer)).getSemanticsData().label,
      _message,
      reason:
          'opening the second line must not make a screen reader read the '
          'whole band again (06 section 3)',
    );
    handle.dispose();
  });

  testWidgets('it is never glass and never more than two lines', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: const UiBanner(
          message: _message,
          tone: UiBannerTone.synthetic,
          detail: _detail,
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel(UiBanner.defaultDetailLabel));
    await tester.pumpAndSettle();

    expect(glassPaneCount(), 0, reason: 'a banner is in the page flow');
    for (final String line in <String>[_message, _detail]) {
      expect(tester.widget<Text>(find.text(line)).maxLines, 1);
    }
    expectGlassBudget(tester);
  });

  testWidgets('it builds right to left', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        child: const UiBanner(
          message: _message,
          tone: UiBannerTone.blocked,
          detail: _detail,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text(_message), findsOneWidget);
  });

  testWidgets('nothing in a banner animates', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: const UiBanner(
          message: _message,
          tone: UiBannerTone.synthetic,
          detail: _detail,
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel(UiBanner.defaultDetailLabel));
    await tester.pump();
    expect(
      tester.binding.transientCallbackCount,
      0,
      reason:
          'the band states a condition of the build, and a band that moves '
          'reads as a band reporting news (04 section 4, row 9)',
    );
  });

  testWidgets('the dismiss control satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiBanner(
        message: _message,
        tone: UiBannerTone.synthetic,
        onDismiss: () {},
        dismissLabel: 'Hide this banner',
      ),
      semanticsLabel: 'Hide this banner',
    );
  });

  testWidgets('the disclosure control satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const UiBanner(
        message: _message,
        tone: UiBannerTone.synthetic,
        detail: _detail,
      ),
      semanticsLabel: UiBanner.defaultDetailLabel,
    );
  });
}
