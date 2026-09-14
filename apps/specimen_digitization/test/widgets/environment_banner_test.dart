// The environment band: shown outside production, hidden inside it.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/widgets/environment_banner.dart';

import 'harness.dart';

void main() {
  testWidgets('renders a sentence for a synthetic environment', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const EnvironmentBanner(environment: 'synthetic'),
    );
    expect(find.textContaining('Synthetic environment.'), findsOneWidget);
    // The science glyph and the disclosure chevron.
    expect(find.byType(Icon), findsNWidgets(2));
  });

  testWidgets('renders nothing at all in production', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const EnvironmentBanner(environment: 'production'),
    );
    expect(find.byType(Text), findsNothing);
    expect(find.byType(Icon), findsNothing);
  });

  test('the production check ignores case and padding', () {
    expect(EnvironmentBanner.showsFor(' Production '), isFalse);
    expect(EnvironmentBanner.showsFor('staging'), isTrue);
  });

  test('the message is sentence case and carries no dash', () {
    final String message = EnvironmentBanner.messageFor('synthetic');
    expect(message, startsWith('Synthetic environment.'));
    expect(message, isNot(contains('-')));
    expect(message, isNot(equals(message.toUpperCase())));
  });

  testWidgets('the band is at least 28 logical pixels tall', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const SizedBox(
        width: 800,
        child: EnvironmentBanner(environment: 'synthetic'),
      ),
    );
    final Size size = tester.getSize(find.byType(EnvironmentBanner));
    expect(size.height, greaterThanOrEqualTo(28));
  });

  testWidgets('the whole band is one node in both themes', (
    WidgetTester tester,
  ) async {
    for (final ThemeData theme in productThemes.values) {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpComponent(
        tester,
        const EnvironmentBanner(environment: 'synthetic'),
        theme: theme,
      );
      expect(
        find.bySemanticsLabel(
          RegExp('Synthetic environment. Results here are fixtures'),
        ),
        findsOneWidget,
      );
      handle.dispose();
    }
  });

  testWidgets('meets the tap target and label guidelines', (
    WidgetTester tester,
  ) async {
    await pumpComponent(
      tester,
      const EnvironmentBanner(environment: 'synthetic'),
    );
    await expectAccessible(tester);
  });

  // Finding V-15. At 390 wide and 200 percent text the band used to wrap to
  // eleven lines and take about half the window. These four hold the cap.
  group('finding V-15, the band at 200 percent text on a phone', () {
    Future<void> pumpPhone(WidgetTester tester) async {
      tester.view.devicePixelRatio = 1.0;
      tester.view.physicalSize = const Size(390, 844);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        MaterialApp(
          theme: productThemes.values.first,
          home: const MediaQuery(
            data: MediaQueryData(textScaler: TextScaler.linear(2.0)),
            child: Scaffold(
              body: Column(
                children: <Widget>[
                  EnvironmentBanner(environment: 'synthetic'),
                  Expanded(child: SizedBox.expand()),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('closed, it is one line and a small fraction of the window', (
      WidgetTester tester,
    ) async {
      await pumpPhone(tester);
      expect(
        tester.widget<Text>(find.textContaining('Synthetic environment.')),
        isA<Text>().having((Text t) => t.maxLines, 'maxLines', 1),
      );
      expect(
        tester.getSize(find.byType(EnvironmentBanner)).height,
        lessThan(844 * 0.2),
        reason:
            'the band used to take about half a phone at this text scale; '
            'finding V-15 caps it',
      );
    });

    testWidgets('open, it is capped at two lines and still small', (
      WidgetTester tester,
    ) async {
      await pumpPhone(tester);
      final Finder line = find.textContaining('Synthetic environment.');
      // One line, measured rather than assumed, so the cap below is in the
      // same units the band actually draws at this text scale.
      final double oneLine = tester.getSize(line).height;
      await tester.tap(find.byTooltip('Show what a test environment means'));
      await tester.pumpAndSettle();
      expect(
        tester.widget<Text>(line),
        isA<Text>().having(
          (Text t) => t.maxLines,
          'maxLines',
          EnvironmentBanner.maxLines,
        ),
      );
      expect(
        tester.getSize(line).height,
        lessThanOrEqualTo(oneLine * EnvironmentBanner.maxLines + 1),
        reason: 'the open band is two lines at most, at any text scale',
      );
      expect(
        tester.getSize(find.byType(EnvironmentBanner)).height,
        lessThan(844 * 0.3),
      );
    });

    testWidgets('the whole sentence is on the tooltip and the semantics node', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpPhone(tester);
      final String message = EnvironmentBanner.messageFor('synthetic');
      expect(
        find.ancestor(
          of: find.textContaining('Synthetic environment.'),
          matching: find.byWidgetPredicate(
            (Widget w) => w is Tooltip && w.message == message,
          ),
        ),
        findsOneWidget,
      );
      expect(find.bySemanticsLabel(message), findsOneWidget);
      handle.dispose();
    });

    testWidgets('the disclosure keeps a full target', (
      WidgetTester tester,
    ) async {
      await pumpPhone(tester);
      final Size target = tester.getSize(
        find.byTooltip('Show what a test environment means'),
      );
      expect(target.width, greaterThanOrEqualTo(48));
      expect(target.height, greaterThanOrEqualTo(48));
    });
  });
}
