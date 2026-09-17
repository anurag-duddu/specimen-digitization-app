// Shared scaffolding for the workbench and panel tests.
//
// Every workbench surface reads the product `ThemeExtension`s, so a test that
// pumps a bare Material theme is not testing the widget that ships. This is
// the same rule `test/widgets/harness.dart` applies to the component library,
// applied to the screen.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

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

/// The button that owns [label].
///
/// Every button on these screens is a `UiButton`, which carries its label as
/// a property and draws it through a `UiLabel`, so the widget is what a test
/// reads `onPressed` and `disabledReason` off.
UiButton buttonWithLabel(WidgetTester tester, String label) =>
    tester.widget<UiButton>(find.widgetWithText(UiButton, label).first);

/// Whether the control labelled [label] can be used.
///
/// Reads a `UiButton` or, for a control on a screen another slot has not
/// migrated yet, the Material button it still is. One helper, so a test that
/// spans two slots does not have to know which wave a control is in.
bool controlEnabled(WidgetTester tester, String label) {
  final Finder ui = find.widgetWithText(UiButton, label);
  if (ui.evaluate().isNotEmpty) {
    return tester.widget<UiButton>(ui.first).onPressed != null;
  }
  final Finder material = find
      .ancestor(
        of: find.text(label),
        matching: find.byWidgetPredicate((Widget w) => w is ButtonStyleButton),
      )
      .first;
  return tester.widget<ButtonStyleButton>(material).onPressed != null;
}

/// Why the control labelled [label] cannot be used, as it publishes it.
///
/// `UiButton` and `UiIconButton` carry the sentence on the control itself,
/// which is what a screen reader reads (accessibility, section 3.2).
String? disabledReasonOf(WidgetTester tester, String label) {
  final Finder ui = find.widgetWithText(UiButton, label);
  if (ui.evaluate().isEmpty) return null;
  return tester.widget<UiButton>(ui.first).disabledReason;
}

/// Closes the modal on screen by dismissing its scrim.
///
/// A modal route covers the page, so a test that opened one and then reaches
/// for a control behind it taps the scrim instead. This is how it puts the
/// page back.
Future<void> closeUiModal(WidgetTester tester) async {
  await tester.tapAt(Offset.zero);
  await tester.pumpAndSettle();
}
