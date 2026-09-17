// Window size classes and `Adaptive` (11 section 3.1).
//
// The classes moved here from the application unchanged, so the first group
// below is the application's own test re-run against the package: same
// breakpoints, same behaviour at and around each one. The second group is the
// part that is new, and the part a scaffold will lean on.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// Reads [read] in a window [width] wide.
Future<void> _inWindow(
  WidgetTester tester,
  double width,
  void Function(BuildContext context) read,
) async {
  await tester.pumpWidget(
    uiHarness(
      size: Size(width, 800),
      child: Builder(
        builder: (BuildContext context) {
          read(context);
          return const SizedBox.shrink();
        },
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('WindowClass', () {
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
      void read(BuildContext context) => seen = WindowClass.of(context);

      await _inWindow(tester, 400, read);
      expect(seen, WindowClass.compact);
      await _inWindow(tester, 900, read);
      expect(seen, WindowClass.expanded);
      await _inWindow(tester, 1700, read);
      expect(seen, WindowClass.extraLarge);
    });

    test('the modal breakpoint is the same 600, not a second copy of it', () {
      // The primitive restated it while the classes lived in the application.
      expect(compactWindowMax, WindowClass.mediumMin);
    });
  });

  group('Adaptive', () {
    const Adaptive<int> columns = Adaptive<int>(compact: 1, expanded: 3);

    test('a class with no value of its own takes the nearest smaller one', () {
      expect(columns.resolve(WindowClass.compact), 1);
      expect(columns.resolve(WindowClass.medium), 1);
      expect(columns.resolve(WindowClass.expanded), 3);
      expect(columns.resolve(WindowClass.large), 3);
      expect(columns.resolve(WindowClass.extraLarge), 3);
    });

    test('it never resolves upward', () {
      const Adaptive<int> wideOnly = Adaptive<int>(large: 4);
      expect(wideOnly.resolve(WindowClass.compact), isNull);
      expect(wideOnly.resolve(WindowClass.expanded), isNull);
      expect(wideOnly.resolve(WindowClass.large), 4);
    });

    test('all gives every class the same value', () {
      const Adaptive<String> one = Adaptive<String>.all('pane');
      for (final WindowClass windowClass in WindowClass.values) {
        expect(one.resolve(windowClass), 'pane');
      }
    });

    test('two declarations of the same values are the same value', () {
      expect(columns, const Adaptive<int>(compact: 1, expanded: 3));
      expect(
        columns.hashCode,
        const Adaptive<int>(compact: 1, expanded: 3).hashCode,
      );
      expect(columns, isNot(const Adaptive<int>(compact: 2, expanded: 3)));
    });

    testWidgets('of resolves against the window it is read in', (
      WidgetTester tester,
    ) async {
      late int? seen;
      void read(BuildContext context) => seen = columns.of(context);

      await _inWindow(tester, 700, read);
      expect(seen, 1, reason: 'medium inherits compact');
      await _inWindow(tester, 1400, read);
      expect(seen, 3, reason: 'large inherits expanded');
    });
  });
}
