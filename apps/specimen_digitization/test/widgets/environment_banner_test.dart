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
    expect(find.byType(Icon), findsOneWidget);
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
}
