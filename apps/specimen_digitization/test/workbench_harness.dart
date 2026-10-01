// Shared scaffolding for the workbench and panel tests.
//
// Every workbench surface reads the product `ThemeExtension`s, so a test that
// pumps a bare Material theme is not testing the widget that ships. This is
// the same rule `test/widgets/harness.dart` applies to the component library,
// applied to the screen.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/workbench.dart'
    show evidenceScrollKey;
import 'package:specimen_ui/specimen_ui.dart';

import 'ui_finders.dart';

/// Representative widths for the constraint-based review layouts.
const Size compactWindow = Size(390, 844);

/// A portrait tablet whose actual local constraints choose the review layout.
const Size mediumWindow = Size(768, 1024);

/// A tablet in landscape: two panes.
const Size expandedWindow = Size(1000, 800);

/// A desktop window: dominant source and one bounded review inspector.
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

/// Reveals the control in its own scrollable, then taps its actual hit target.
Future<void> scrollAndTap(
  WidgetTester tester,
  Finder target, {
  Finder? scrollable,
}) async {
  if (target.evaluate().isEmpty) {
    final Finder evidenceScroll = find.descendant(
      of: find.byKey(evidenceScrollKey),
      matching: find.byType(Scrollable),
    );
    await tester.scrollUntilVisible(
      target,
      200,
      scrollable:
          scrollable ??
          (evidenceScroll.evaluate().isNotEmpty
              ? evidenceScroll.first
              : find.byType(Scrollable).first),
      maxScrolls: 24,
    );
  }
  expect(target, findsOneWidget);
  await tester.ensureVisible(target);
  await tester.pumpAndSettle();
  expect(target.hitTestable(), findsOneWidget);
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

/// Whether a real button, icon or declared menu command can be activated.
/// Missing controls throw: their absence must not masquerade as disabled.
bool controlEnabled(WidgetTester tester, String label) {
  final Finder ui = find.widgetWithText(UiButton, label);
  if (ui.evaluate().isNotEmpty) {
    expect(ui, findsOneWidget);
    return tester.widget<UiButton>(ui).onPressed != null;
  }
  final Finder icon = uiIconButton(label);
  if (icon.evaluate().isNotEmpty) {
    expect(icon, findsOneWidget);
    return tester.widget<UiIconButton>(icon).onPressed != null;
  }
  for (final UiMenuTrigger menu in tester.widgetList<UiMenuTrigger>(
    find.byType(UiMenuTrigger),
  )) {
    for (final UiMenuItem item in menu.items) {
      if (item.label == label) return item.onSelected != null;
    }
  }
  final Finder material = find.ancestor(
    of: find.text(label),
    matching: find.byWidgetPredicate((Widget w) => w is ButtonStyleButton),
  );
  if (material.evaluate().isNotEmpty) {
    expect(material, findsOneWidget);
    return tester.widget<ButtonStyleButton>(material).onPressed != null;
  }
  throw StateError('no control named "$label"');
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

/// What a record command declares: whether it can be used, and why not.
typedef RecordCommand = ({VoidCallback? onPressed, String? disabledReason});

/// The record command named [label], as the top bar declares it.
///
/// 13 section 4.1 gives the record's bar back, the identifier and refresh,
/// and puts the record's own commands in the bar's overflow menu at every
/// width, so a command is either the one disc the bar keeps or a row of the
/// menu the trigger holds. A test that wants to know whether a command is
/// available reads the command rather than hunting for whichever form it
/// took; both forms carry the callback and the reason, which is the same
/// answer a screen reader gets.
RecordCommand recordCommand(WidgetTester tester, String label) {
  final UiTopBar bar = tester.widget<UiTopBar>(find.byType(UiTopBar));
  for (final Widget action in bar.actions) {
    if (action is UiTopBarAction && action.label == label) {
      return (
        onPressed: action.onPressed,
        disabledReason: action.disabledReason,
      );
    }
    if (action is UiMenuTrigger) {
      for (final UiMenuItem item in action.items) {
        if (item.label == label) {
          return (
            onPressed: item.onSelected,
            disabledReason: item.disabledReason,
          );
        }
      }
    }
  }
  throw StateError('no record command named "$label"');
}

/// Presses the record command named [label], wherever the bar drew it.
///
/// Refresh is the one disc the record's bar keeps; every other command is a
/// row of its overflow menu (13 section 4.1), reached through the trigger.
Future<void> openRecordCommand(WidgetTester tester, String label) async {
  final RecordCommand command = recordCommand(tester, label);
  expect(command.onPressed, isNotNull, reason: command.disabledReason);
  final Finder disc = uiIconButton(label);
  if (disc.evaluate().isNotEmpty) {
    await tester.ensureVisible(disc);
    await tester.pumpAndSettle();
    expect(disc.hitTestable(), findsOneWidget);
    await tester.tap(disc);
  } else {
    final Finder trigger = find.descendant(
      of: find.byType(UiTopBar),
      matching: uiMenuTrigger(UiTopBarStyle.overflowLabel),
    );
    expect(trigger, findsOneWidget);
    await tester.tap(trigger);
    await tester.pumpAndSettle();
    final Finder row = find.byWidgetPredicate(
      (Widget widget) => widget is Pressable && widget.semanticsLabel == label,
    );
    expect(row, findsOneWidget);
    await tester.ensureVisible(row);
    await tester.pumpAndSettle();
    expect(row.hitTestable(), findsOneWidget);
    await tester.tap(row);
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
