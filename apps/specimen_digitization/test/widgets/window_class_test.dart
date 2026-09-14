// The window size classes, at and around every Material 3 breakpoint.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/layout/window_class.dart';

import 'harness.dart';

void main() {
  test('the breakpoints are the published Material 3 values', () {
    expect(WindowClass.mediumMin, 600);
    expect(WindowClass.expandedMin, 840);
    expect(WindowClass.largeMin, 1200);
    expect(WindowClass.extraLargeMin, 1600);
  });

  test('each class holds from its own minimum to the next', () {
    expect(WindowClass.fromWidth(0), WindowClass.compact);
    expect(WindowClass.fromWidth(599.9), WindowClass.compact);
    expect(WindowClass.fromWidth(600), WindowClass.medium);
    expect(WindowClass.fromWidth(839.9), WindowClass.medium);
    expect(WindowClass.fromWidth(840), WindowClass.expanded);
    expect(WindowClass.fromWidth(1199.9), WindowClass.expanded);
    expect(WindowClass.fromWidth(1200), WindowClass.large);
    expect(WindowClass.fromWidth(1599.9), WindowClass.large);
    expect(WindowClass.fromWidth(1600), WindowClass.extraLarge);
    expect(WindowClass.fromWidth(4000), WindowClass.extraLarge);
  });

  test('isAtLeast orders the classes', () {
    expect(WindowClass.expanded.isAtLeast(WindowClass.medium), isTrue);
    expect(WindowClass.medium.isAtLeast(WindowClass.expanded), isFalse);
    expect(WindowClass.compact.isCompact, isTrue);
    expect(WindowClass.medium.isCompact, isFalse);
  });

  testWidgets('of reads the live window width', (WidgetTester tester) async {
    late WindowClass seen;
    Widget probe() => Builder(
      builder: (BuildContext context) {
        seen = WindowClass.of(context);
        return const SizedBox.shrink();
      },
    );

    await pumpComponent(tester, probe(), size: const Size(400, 800));
    expect(seen, WindowClass.compact);
    await pumpComponent(tester, probe(), size: const Size(900, 800));
    expect(seen, WindowClass.expanded);
    await pumpComponent(tester, probe(), size: const Size(1700, 900));
    expect(seen, WindowClass.extraLarge);
  });
}
