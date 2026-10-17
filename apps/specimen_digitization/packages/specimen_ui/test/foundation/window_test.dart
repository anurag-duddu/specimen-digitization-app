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
  // The arrangement the chrome reads (05 section 2, amended 2026-10-17). The
  // values are the shell's since 2026-10-01; these pin each boundary from
  // both sides, at normal and at 200 percent text, so a change to one is a
  // decision someone has to make here rather than a literal that drifts.
  group('WindowArrangement', () {
    const TextScaler doubled = TextScaler.linear(2);

    test('the boundaries are the shell\'s, unchanged', () {
      expect(WindowArrangement.dockedMinWidth, 768);
      expect(WindowArrangement.dockedMinHeight, 600);
      expect(WindowArrangement.listDetailMinWidth, 1100);
      expect(WindowArrangement.listPaneWidth, 312);
    });

    test('width docks from 768 and opens the list from 1100', () {
      expect(
        WindowArrangement.fromSize(const Size(767.9, 1000)),
        WindowArrangement.stacked,
      );
      expect(
        WindowArrangement.fromSize(const Size(768, 1000)),
        WindowArrangement.docked,
      );
      expect(
        WindowArrangement.fromSize(const Size(1099.9, 1000)),
        WindowArrangement.docked,
      );
      expect(
        WindowArrangement.fromSize(const Size(1100, 1000)),
        WindowArrangement.listDetail,
      );
    });

    test('a window under 600 tall is stacked at any width', () {
      expect(
        WindowArrangement.fromSize(const Size(2000, 599.9)),
        WindowArrangement.stacked,
      );
      expect(
        WindowArrangement.fromSize(const Size(2000, 600)),
        WindowArrangement.listDetail,
      );
      // A phone on its side: the window class is expanded, the arrangement
      // is the phone's.
      expect(WindowClass.fromWidth(844), WindowClass.expanded);
      expect(
        WindowArrangement.fromSize(const Size(844, 390)),
        WindowArrangement.stacked,
      );
    });

    test('the widths scale with the text, held to 1 through 2', () {
      expect(
        WindowArrangement.fromSize(const Size(1535, 1000), textScaler: doubled),
        WindowArrangement.stacked,
      );
      expect(
        WindowArrangement.fromSize(const Size(1536, 1000), textScaler: doubled),
        WindowArrangement.docked,
      );
      expect(
        WindowArrangement.fromSize(const Size(2199, 1000), textScaler: doubled),
        WindowArrangement.docked,
      );
      expect(
        WindowArrangement.fromSize(const Size(2200, 1000), textScaler: doubled),
        WindowArrangement.listDetail,
      );
      // Reduced text docks no earlier, and 300 percent no later, than the
      // ends of the clamp.
      expect(
        WindowArrangement.fromSize(
          const Size(767, 1000),
          textScaler: const TextScaler.linear(0.85),
        ),
        WindowArrangement.stacked,
      );
      expect(
        WindowArrangement.fromSize(
          const Size(1536, 1000),
          textScaler: const TextScaler.linear(3),
        ),
        WindowArrangement.docked,
      );
    });

    test('the list pane grows with the text on the 8 dp grid', () {
      expect(WindowArrangement.listPaneWidthOf(TextScaler.noScaling), 312);
      expect(WindowArrangement.listPaneWidthOf(doubled), 624);
      // 312 times 1.3 is 405.6, up to the grid.
      expect(
        WindowArrangement.listPaneWidthOf(const TextScaler.linear(1.3)),
        408,
      );
    });

    test('stacked is the only arrangement that is not docked', () {
      expect(WindowArrangement.stacked.isStacked, isTrue);
      expect(WindowArrangement.stacked.isDocked, isFalse);
      expect(WindowArrangement.docked.isDocked, isTrue);
      expect(WindowArrangement.listDetail.isDocked, isTrue);
      expect(WindowArrangement.listDetail.isStacked, isFalse);
    });

    testWidgets('of reads the window and its text scale', (
      WidgetTester tester,
    ) async {
      late WindowArrangement seen;
      Future<void> pumpAt(Size size, TextScaler scaler) async {
        await tester.pumpWidget(
          uiHarness(
            size: size,
            textScaler: scaler,
            child: Builder(
              builder: (BuildContext context) {
                seen = WindowArrangement.of(context);
                return const SizedBox.shrink();
              },
            ),
          ),
        );
      }

      await pumpAt(const Size(1180, 820), TextScaler.noScaling);
      expect(seen, WindowArrangement.listDetail);
      await pumpAt(const Size(1180, 820), doubled);
      expect(seen, WindowArrangement.stacked);
      await pumpAt(const Size(844, 390), TextScaler.noScaling);
      expect(seen, WindowArrangement.stacked);
    });
  });
}
