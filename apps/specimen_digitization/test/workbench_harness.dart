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

import 'ui_finders.dart';

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

/// Pumps [child] on the product theme, inside the frame it ships in.
///
/// The frame is a `UiScaffold` because the record publishes its chrome into
/// one: the top bar it names itself in and the action bar its two decisions
/// sit on are `UiScaffoldSlots` asks, and a screen pumped with no frame above
/// it would be a screen with no decision bar at all (13 section 3.4).
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
      child: UiTheme(
        // The tokens the application publishes at its root, published here
        // for the same reason: without them `UiScaffold` builds its own
        // derived set on every frame, every control under it is told its
        // tokens changed, and a screen that answers that by publishing into
        // the frame never settles. `main.dart` and the golden harness both
        // do this; a screen harness that did not was measuring a tree the
        // product never draws.
        data: Theme.of(context).brightness == Brightness.dark
            ? UiThemeData.dark()
            : UiThemeData.light(),
        child: Scaffold(
          body: UiScaffold(sky: SkyPreset.none, body: child),
        ),
      ),
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

/// The record command named [label], as the top bar declares it.
///
/// 13 section 4.1 moves the record's own commands into the bar, which keeps
/// the first two as discs and puts the rest in its own overflow menu, so a
/// test that wants to know whether a command is available reads the command
/// rather than hunting for whichever of the two arrangements the width
/// earned. The same answer a screen reader gets: `UiTopBarAction` carries the
/// label, the callback and the reason into both.
UiTopBarAction recordCommand(WidgetTester tester, String label) => tester
    .widget<UiTopBar>(find.byType(UiTopBar))
    .actions
    .whereType<UiTopBarAction>()
    .firstWhere(
      (UiTopBarAction action) => action.label == label,
      orElse: () => throw StateError('no record command named "$label"'),
    );

/// Presses the record command named [label], wherever the bar drew it.
///
/// `UiTopBar` keeps the first two commands as discs and puts the rest in its
/// own overflow menu (11 section 3.3), so which of the two a test finds is a
/// property of the width rather than of the record.
Future<void> openRecordCommand(WidgetTester tester, String label) async {
  final Finder disc = uiIconButton(label);
  if (disc.evaluate().isNotEmpty) {
    await tester.tap(disc);
  } else {
    await tester.tap(uiMenuTrigger(UiTopBarStyle.overflowLabel));
    await tester.pumpAndSettle();
    await tester.tap(find.text(label).last);
  }
  await tester.pumpAndSettle();
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
