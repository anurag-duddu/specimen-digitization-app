// Shared scaffolding for the workbench and panel tests.
//
// Every workbench surface reads the product `ThemeExtension`s, so a test that
// pumps a bare Material theme is not testing the widget that ships. This is
// the same rule `test/widgets/harness.dart` applies to the component library,
// applied to the screen.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';

/// The widths that select each of the three workbench regimes
/// (responsive and platform adaptation, 3.5).
const Size compactWindow = Size(390, 844);

/// A tablet in landscape: two panes.
const Size expandedWindow = Size(1000, 800);

/// A desktop window: three panes, History persistent.
const Size largeWindow = Size(1440, 1000);

/// Fixes the window size for one test and restores it afterwards.
void useWindow(WidgetTester tester, Size size) {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

/// Pumps [child] on the product theme, in a scaffold.
///
/// [reduceMotion] drives `MediaQuery.disableAnimationsOf`, the one
/// reduced-motion signal a widget test can set.
Widget workbenchHost(
  Widget child, {
  ThemeData? theme,
  bool reduceMotion = false,
}) => MaterialApp(
  theme: theme ?? AppTheme.light(),
  home: Builder(
    builder: (BuildContext context) => MediaQuery(
      data: MediaQuery.of(context).copyWith(disableAnimations: reduceMotion),
      child: Scaffold(body: child),
    ),
  ),
);

/// The same host, for a panel that has to scroll to be reachable.
Widget scrollingHost(Widget child, {ThemeData? theme}) => MaterialApp(
  theme: theme ?? AppTheme.light(),
  home: Scaffold(body: SingleChildScrollView(child: child)),
);

/// The first scrollable inside [of], which is the evidence pane in every
/// workbench layout.
Finder scrollableIn(Finder of) =>
    find.descendant(of: of, matching: find.byType(Scrollable)).first;

/// Scrolls [target] into view inside the evidence pane and taps it.
Future<void> scrollAndTap(
  WidgetTester tester,
  Finder target, {
  Finder? scrollable,
}) async {
  await tester.scrollUntilVisible(
    target,
    200,
    scrollable: scrollable ?? find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
  await tester.tap(target);
  await tester.pumpAndSettle();
}

/// The button that owns [label], whatever button type it is.
ButtonStyleButton buttonWithLabel(WidgetTester tester, String label) =>
    tester.widget<ButtonStyleButton>(
      find
          .ancestor(
            of: find.text(label),
            matching: find.byWidgetPredicate(
              (Widget w) => w is ButtonStyleButton,
            ),
          )
          .first,
    );
