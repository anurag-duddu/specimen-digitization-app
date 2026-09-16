// The harness itself (10 section 7).
//
// `uiHarness` is what every control test and every gallery golden is measured
// through, so where it publishes the tokens is a property worth pinning. They
// sit above the app, which is above its navigator, exactly as `main.dart`
// wraps `MaterialApp.router`: a route pushed over the page reads the mode,
// the density and the motion state the test asked for rather than falling
// back to the light tokens.

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
}
