// The harness itself (10 section 7).
//
// `uiHarness` is what every control test and every gallery golden is measured
// through, so where it publishes the tokens is a property worth pinning. They
// sit above the app, which is above its navigator, exactly as `main.dart`
// wraps `MaterialApp.router`: a route pushed over the page reads the mode,
// the density and the motion state the test asked for rather than falling
// back to the light tokens.
//
// Clauses 13 to 15 are added to the same harness by 11 section 6 and are off
// until a family turns them on, which means the one thing that could go wrong
// with them is that they never fail. The group at the end of this file pumps
// a control that breaks each clause and asserts that the clause says so.

import 'dart:async' show unawaited;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'control_contract.dart';

/// The fill `GlassSurface` paints over its blur, in the pane [of] sits in.
Color _paneFill(WidgetTester tester, Finder of) {
  final DecoratedBox box = tester.widget<DecoratedBox>(
    find
        .descendant(
          of: of,
          matching: find.byWidgetPredicate(
            (Widget widget) =>
                widget is DecoratedBox && widget.decoration is BoxDecoration,
          ),
        )
        .first,
  );
  return (box.decoration as BoxDecoration).color!;
}

void main() {
  testWidgets('a route pushed under dark draws the dark glass.modal fill', (
    WidgetTester tester,
  ) async {
    late BuildContext page;
    await tester.pumpWidget(
      uiHarness(
        brightness: Brightness.dark,
        child: Builder(
          builder: (BuildContext context) {
            page = context;
            return const SizedBox(width: 160, height: 48);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    // The route outlives the test body: the dialog is still open when the
    // assertions run, so its future is deliberately not awaited.
    unawaited(
      showUiDialog<void>(
        context: page,
        semanticsLabel: 'Record a reason',
        builder: (BuildContext context) =>
            const SizedBox(width: 320, height: 200),
      ),
    );
    await tester.pumpAndSettle();

    final Finder pane = find.byType(GlassSurface);
    expect(pane, findsOneWidget, reason: 'the dialog pushed its pane');

    final UiThemeData inside = tester.element(pane).ui;
    expect(
      inside.isDark,
      isTrue,
      reason:
          'a route sits above the navigator, so it reads the harness theme '
          'rather than UiTheme._fallback, which in a WidgetsApp is light',
    );

    final Color drawn = _paneFill(tester, pane);
    expect(
      drawn,
      UiThemeData.dark().glass.modal.fillFor(GlassQuality.full),
      reason: 'the modal is painted from the dark column of the token table',
    );
    expect(
      drawn,
      isNot(UiThemeData.light().glass.modal.fillFor(GlassQuality.full)),
      reason:
          'the two columns differ, so this assertion is about the mode and '
          'not about a value the two modes happen to share',
    );
  });

  testWidgets('a route reads the density and the motion state as well', (
    WidgetTester tester,
  ) async {
    late BuildContext page;
    await tester.pumpWidget(
      uiHarness(
        density: UiDensityMode.pointer,
        disableAnimations: true,
        child: Builder(
          builder: (BuildContext context) {
            page = context;
            return const SizedBox(width: 160, height: 48);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    // The route outlives the test body: the dialog is still open when the
    // assertions run, so its future is deliberately not awaited.
    unawaited(
      showUiDialog<void>(
        context: page,
        semanticsLabel: 'Record a reason',
        builder: (BuildContext context) =>
            const SizedBox(width: 320, height: 200),
      ),
    );
    await tester.pumpAndSettle();

    final UiThemeData inside = tester.element(find.byType(GlassSurface)).ui;
    expect(inside.density.mode, UiDensityMode.pointer);
    expect(
      inside.motion.short,
      Duration.zero,
      reason:
          'a route under reduced motion collapses its own transitions too '
          '(04 section 2.5)',
    );
  });

  group('clause 13, labels never wrap', () {
    testWidgets('a label that stays on one line passes', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        (BuildContext context) => const _FitSpecimen(),
        semanticsLabel: _FitSpecimen.label,
        labelsNeverWrap: true,
      );
    });

    testWidgets('a label that wraps fails, and says which string', (
      WidgetTester tester,
    ) async {
      await expectLater(
        () => expectControlContract(
          tester,
          (BuildContext context) => const _FitSpecimen(wraps: true),
          semanticsLabel: _FitSpecimen.label,
          labelsNeverWrap: true,
        ),
        throwsA(
          isA<TestFailure>().having(
            (TestFailure failure) => failure.message,
            'message',
            allOf(
              contains('more than one line'),
              contains(_FitSpecimen.sentence),
            ),
          ),
        ),
      );
    });

    testWidgets('a string named as content is allowed to wrap', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        (BuildContext context) => const _FitSpecimen(wraps: true),
        semanticsLabel: _FitSpecimen.label,
        labelsNeverWrap: true,
        wrappingContent: <String>{_FitSpecimen.sentence},
      );
    });
  });

  group('clause 14, geometry derives from type', () {
    testWidgets('a control that grows with the text passes', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        (BuildContext context) => const _FitSpecimen(),
        semanticsLabel: _FitSpecimen.label,
        geometryFromType: true,
      );
    });

    testWidgets('a label the growing text clips fails, and names the scale', (
      WidgetTester tester,
    ) async {
      // A box the label fits in at 1.0 and 1.3 and not at 2.0. Measured
      // rather than guessed, so the test does not drift when a role does.
      final double width = await _labelWidthAt(tester, 1.6);
      await expectLater(
        () => expectControlContract(
          tester,
          (BuildContext context) => _FitSpecimen(width: width),
          semanticsLabel: _FitSpecimen.label,
          geometryFromType: true,
        ),
        throwsA(
          isA<TestFailure>().having(
            (TestFailure failure) => failure.message,
            'message',
            allOf(contains('truncated'), contains('text scale 2')),
          ),
        ),
      );
    });
  });

  group('clause 15, fit is declared', () {
    testWidgets('the caller sees every width it declared', (
      WidgetTester tester,
    ) async {
      final List<double> seen = <double>[];
      await expectControlContract(
        tester,
        (BuildContext context) => const _FitSpecimen(),
        semanticsLabel: _FitSpecimen.label,
        fit: FitExpectation(
          check: (WidgetTester tester, double width) async {
            seen.add(width);
            expect(find.text(_FitSpecimen.label), findsOneWidget);
          },
        ),
      );
      expect(seen, fitWidths);
    });

    testWidgets("a caller's own expectation is what fails", (
      WidgetTester tester,
    ) async {
      await expectLater(
        () => expectControlContract(
          tester,
          (BuildContext context) => const _FitSpecimen(),
          semanticsLabel: _FitSpecimen.label,
          fit: FitExpectation(
            widths: const <double>[280],
            check: (WidgetTester tester, double width) async =>
                expect(find.text('a compact variant'), findsOneWidget),
          ),
        ),
        throwsA(isA<TestFailure>()),
      );
    });
  });
}

/// The width [_FitSpecimen.label] needs at [scale].
Future<double> _labelWidthAt(WidgetTester tester, double scale) async {
  late double width;
  await tester.pumpWidget(
    uiHarness(
      textScaler: TextScaler.linear(scale),
      child: Builder(
        builder: (BuildContext context) {
          width = measureLabel(
            context,
            _FitSpecimen.label,
            context.ui.type.titleLarge,
          ).width;
          return const SizedBox.shrink();
        },
      ),
    ),
  );
  await tester.pumpAndSettle();
  return width;
}

/// A control shaped like the ones wave G converts, with each defect the fit
/// clauses exist to catch available as a switch.
///
/// It is built here rather than taken from a family, because a test that
/// proves a clause fails needs something that fails it, and every control in
/// the package is meant to pass.
class _FitSpecimen extends StatelessWidget {
  const _FitSpecimen({this.wraps = false, this.width});

  /// The label the contract looks for.
  static const String label = 'Confirm the reading';

  /// A second string, long enough to wrap in a narrow column.
  static const String sentence =
      'Confirm the reading and move on to the next record in the queue';

  /// Draws [sentence] as a wrapping `Text`, which is the defect clause 13
  /// catches when the string is a label rather than content.
  final bool wraps;

  /// Pins the label's box, which is the defect clause 14 catches: the box
  /// holds while the text grows, so the label ends up cut.
  final double? width;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // `title.large` rather than `label`: its line box passes the 48 dp row
    // between 1.3 and 2.0, so the geometry this specimen exercises is the
    // geometry the clause is about.
    final TextStyle style = ui.type.titleLarge;
    return Pressable(
      semanticsLabel: label,
      onPressed: () {},
      shape: ui.shape.capsule,
      builder: (BuildContext context, Set<WidgetState> states) => SizedBox(
        width: width,
        // Content text sets its own height; a label sits in the height the
        // type scale says one line of it needs.
        height: wraps
            ? null
            : UiType.controlHeightFor(ui.density, style, context),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            if (wraps)
              Text(sentence, style: style)
            else
              UiLabel(label, style: style),
          ],
        ),
      ),
    );
  }
}
