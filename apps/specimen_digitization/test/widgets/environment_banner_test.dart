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
    expect(find.textContaining('Test environment.'), findsOneWidget);
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

  test('the always visible headline claims nothing about the models', () {
    // UX writing 4.15: the label alone must be true for a reader who never
    // opens the disclosure. A non-production build can be wired to the real
    // routes, so the band cannot assert that readings are fixtures. Each
    // reading names its own model and provider instead.
    final String headline = EnvironmentBanner.headlineFor('synthetic');
    for (final String claim in <String>[
      'fixture',
      'fixtures',
      'not real model',
      'real model processing',
    ]) {
      expect(
        headline.toLowerCase(),
        isNot(contains(claim)),
        reason: 'the headline must not assert where a reading came from',
      );
    }
    expect(headline, contains('Not approved museum records.'));
  });

  test('the band calls a synthetic build a test environment', () {
    // The vocabulary table maps `synthetic` to "test" for the banner, and the
    // disclosure control already said "test environment".
    expect(EnvironmentBanner.nameFor('synthetic'), 'Test environment');
    expect(EnvironmentBanner.nameFor('staging'), 'Staging environment');
    expect(EnvironmentBanner.nameFor('  '), 'This environment');
  });

  test('the message is sentence case and carries no dash', () {
    final String message = EnvironmentBanner.messageFor('synthetic');
    expect(message, startsWith('Test environment.'));
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
          RegExp(r'Test environment\. Not approved museum records'),
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

    testWidgets('closed, it is two lines at most and a small fraction of the '
        'window', (WidgetTester tester) async {
      await pumpPhone(tester);
      // Two rather than one since wave G. 11 section 3.3 calls a band's
      // sentence content and lets it wrap, and the cap finding V-15 asks for
      // is on the band, not on the line: closed, the sentence may take both
      // of the band's two lines; open, it takes one and the detail takes the
      // other. The height below is the guarantee either way.
      expect(
        tester.widget<Text>(find.textContaining('Test environment.')),
        isA<Text>().having(
          (Text t) => t.maxLines,
          'maxLines',
          EnvironmentBanner.maxLines,
        ),
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
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpPhone(tester);
      final Finder line = find.textContaining('Test environment.');
      final double closed = tester
          .getSize(find.byType(EnvironmentBanner))
          .height;

      await tester.tap(find.bySemanticsLabel(EnvironmentBanner.detailLabel));
      await tester.pumpAndSettle();

      // Two lines, not one long one: the headline keeps its own line and the
      // detail takes the second, each capped, at every text scale.
      expect(
        tester.widget<Text>(line),
        isA<Text>().having((Text t) => t.maxLines, 'maxLines', 1),
      );
      expect(find.text(EnvironmentBanner.detail), findsOneWidget);
      expect(
        tester.widget<Text>(find.text(EnvironmentBanner.detail)),
        isA<Text>().having((Text t) => t.maxLines, 'maxLines', 1),
      );
      final double open = tester.getSize(find.byType(EnvironmentBanner)).height;
      expect(
        open,
        lessThanOrEqualTo(closed * EnvironmentBanner.maxLines + 1),
        reason: 'the open band is two lines at most, at any text scale',
      );
      expect(open, lessThan(844 * 0.3));
      handle.dispose();
    });

    testWidgets('the whole sentence is reachable without sight', (
      WidgetTester tester,
    ) async {
      // The v1 band put the whole sentence on one node and excluded
      // everything under it, which also excluded its own disclosure: the
      // statement was readable and the control was not. The headline is
      // announced, the control is a named target, and the second clause is a
      // node of its own once it is opened.
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpPhone(tester);
      expect(
        find.bySemanticsLabel(EnvironmentBanner.headlineFor('synthetic')),
        findsOneWidget,
      );
      expect(
        find.bySemanticsLabel(EnvironmentBanner.detail),
        findsNothing,
        reason: 'the second clause is not read before it is asked for',
      );

      await tester.tap(find.bySemanticsLabel(EnvironmentBanner.detailLabel));
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel(EnvironmentBanner.detail), findsOneWidget);
      handle.dispose();
    });

    testWidgets('the disclosure keeps a full target', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpPhone(tester);
      final Size target = tester.getSize(
        find.bySemanticsLabel(EnvironmentBanner.detailLabel),
      );
      expect(target.width, greaterThanOrEqualTo(48));
      expect(target.height, greaterThanOrEqualTo(48));
      handle.dispose();
    });
  });
}
