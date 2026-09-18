// `UiBanner` (10 section 4.3).

import 'dart:ui' show Tristate;

import 'package:flutter/rendering.dart';
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
        uiHarness(
          child: UiBanner(message: _message, tone: tone),
        ),
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

  testWidgets('a band offers its recovery beside the words when they fit', (
    WidgetTester tester,
  ) async {
    int taken = 0;
    await tester.pumpWidget(
      uiHarness(
        size: const Size(900, 600),
        child: SizedBox(
          width: 900,
          child: UiBanner(
            message: _message,
            tone: UiBannerTone.blocked,
            actionLabel: 'Retry upload',
            onAction: () => taken++,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final double wordsBottom = tester.getBottomLeft(find.text(_message)).dy;
    final double actionTop = tester
        .getTopLeft(find.bySemanticsLabel('Retry upload'))
        .dy;
    expect(
      actionTop,
      lessThan(wordsBottom),
      reason: 'a 900 dp band has room for both on one line',
    );

    await tester.tap(find.bySemanticsLabel('Retry upload'));
    await tester.pumpAndSettle();
    expect(taken, 1);
  });

  testWidgets('a band moves its recovery under the words when they do not', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(280, 600),
        child: SizedBox(
          width: 280,
          child: UiBanner(
            message: _message,
            tone: UiBannerTone.blocked,
            actionLabel: 'Retry upload',
            onAction: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      tester.getTopLeft(find.bySemanticsLabel('Retry upload')).dy,
      greaterThanOrEqualTo(tester.getBottomLeft(find.text(_message)).dy),
      reason:
          '11 section 3.3: the action moves under the text rather than the '
          'text being squeezed, because the text is content',
    );
    expect(
      find.text(_message),
      findsOneWidget,
      reason: 'and the sentence is still whole',
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
      labelsNeverWrap: true,
      // The band's sentence is content and wraps: 11 section 3.3 makes that
      // the last resort for this row, capped at the two lines the band has
      // promised since finding V-15.
      wrappingContent: <String>{_message},
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          expect(find.text(_message), findsOneWidget);
          expect(find.bySemanticsLabel('Hide this banner'), findsOneWidget);
        },
      ),
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
      labelsNeverWrap: true,
      wrappingContent: <String>{_message, _detail},
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          expect(
            find.bySemanticsLabel(UiBanner.defaultDetailLabel),
            findsOneWidget,
          );
        },
      ),
    );
  });

  group('UiBanner.strip', () {
    testWidgets('satisfies the control contract', (WidgetTester tester) async {
      // The tap is given its own callback here rather than the sheet: the
      // contract activates a control several times and never pops what it
      // opened, so a route would cover the band for every clause after the
      // keyboard one. The sheet has its own test below.
      await expectControlContract(
        tester,
        (BuildContext context) => UiBanner.strip(
          message: _message,
          sheetTitle: 'About this build',
          onTap: () {},
        ),
        semanticsLabel: _message,
        labelsNeverWrap: true,
        geometryFromType: true,
        fit: FitExpectation(
          check: (WidgetTester tester, double width) async {
            expect(find.bySemanticsLabel(_message), findsOneWidget);
          },
        ),
      );
    });

    testWidgets('is one line of label on the tint', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: SizedBox(
            width: 390,
            child: UiBanner.strip(
              message: _message,
              sheetTitle: 'About this build',
              onTap: () {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final RenderParagraph line = tester
          .renderObjectList<RenderParagraph>(find.byType(RichText))
          .firstWhere(
            (RenderParagraph paragraph) =>
                paragraph.text.toPlainText().contains('Test environment'),
          );
      expect(line.maxLines, 1);
      expect(
        line.text.style?.fontSize,
        UiThemeData.light().type.label.fontSize,
        reason: 'a label line, not the band paragraph 13 section 2.3 retires',
      );
      // 32 dp of tint, floored by the hit box of the control the whole band
      // is: the band around a control is what gives in this family, never the
      // 48 dp itself.
      expect(tester.getSize(find.byType(UiBanner)).height, UiDensity.hitBox);
    });

    testWidgets('the tap keeps the sentence and the contact', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: const SizedBox(
            width: 390,
            child: UiBanner.strip(
              message: _message,
              detail: _detail,
              sheetTitle: 'About this build',
              contact: Text('Ask the collection administrator'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(_detail), findsNothing);
      await tester.tap(find.bySemanticsLabel(_message));
      await tester.pumpAndSettle();

      expect(find.text('About this build'), findsOneWidget);
      expect(find.text(_detail), findsOneWidget);
      expect(find.text('Ask the collection administrator'), findsOneWidget);
    });

    testWidgets('the route asks for the strip and an explicit form wins', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: SizedBox(
            width: 390,
            child: UiBandForm(
              form: UiBannerForm.strip,
              child: UiBanner(
                message: _message,
                tone: UiBannerTone.synthetic,
                detail: _detail,
                sheetTitle: 'About this build',
                onTap: () {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // The shell writes one call site and the route decides which form it
      // draws (13 section 3.4).
      expect(tester.getSize(find.byType(UiBanner)).height, UiDensity.hitBox);
      expect(find.bySemanticsLabel(UiBanner.defaultDetailLabel), findsNothing);

      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: const SizedBox(
            width: 390,
            child: UiBandForm(
              form: UiBannerForm.strip,
              child: UiBanner(
                message: _message,
                tone: UiBannerTone.synthetic,
                detail: _detail,
                form: UiBannerForm.full,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.bySemanticsLabel(UiBanner.defaultDetailLabel),
        findsOneWidget,
        reason:
            'an explicit form is a decision and the ambient one is a '
            'default',
      );
    });
  });
}
