/// The shared control contract (10 section 2).
///
/// Every interactive component in the controls layer calls
/// [expectControlContract]. A control whose test file does not call it does
/// not merge (10 section 2, preamble).
///
/// Each clause below names the clause of section 2 it checks. Clauses 1 and 12
/// are not checkable here: "visually distinct in the gallery" and "appears on
/// its family page" are what the gallery goldens are for.
library;

import 'dart:ui' show CheckedState, SemanticsFlags, Tristate;

import 'package:flutter/foundation.dart';
// The delegate only. 10 section 1.3 keeps `MaterialLocalizations` as
// infrastructure: `FieldCore`'s `TextField` reads its selection toolbar
// strings from it, and the application supplies it through `MaterialApp`.
import 'package:flutter/material.dart' show DefaultMaterialLocalizations;
import 'package:flutter/gestures.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

/// Wraps [child] in the minimum tree a component needs.
///
/// `WidgetsApp` rather than `MaterialApp`: a control that only works inside a
/// `MaterialApp` has a Material dependency the layering gate would not catch.
/// It is here rather than a hand-built `Shortcuts` stack because Tab
/// traversal, the activation shortcuts and the default actions are what a real
/// application provides, and a harness that provides different ones tests a
/// different control.
Widget uiHarness({
  required Widget child,
  Brightness brightness = Brightness.light,
  UiDensityMode density = UiDensityMode.touch,
  TextScaler textScaler = TextScaler.noScaling,
  TextDirection textDirection = TextDirection.ltr,
  bool disableAnimations = false,
  Size size = const Size(800, 600),
}) {
  final UiThemeData ui = brightness == Brightness.dark
      ? UiThemeData.dark()
      : UiThemeData.light();
  return WidgetsApp(
    color: ui.color.ground,
    debugShowCheckedModeBanner: false,
    localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
      DefaultMaterialLocalizations.delegate,
      DefaultWidgetsLocalizations.delegate,
    ],
    // A route, so the harness has what an application has: a navigator, an
    // overlay for `OverlayPortal` to hang from, and a focus scope that takes
    // focus on the first frame. Without a route nothing ever holds focus and
    // Tab traverses from nowhere.
    pageRouteBuilder: <T>(RouteSettings settings, WidgetBuilder builder) =>
        PageRouteBuilder<T>(
          settings: settings,
          pageBuilder:
              (
                BuildContext context,
                Animation<double> animation,
                Animation<double> secondary,
              ) => builder(context),
        ),
    home: MediaQuery(
      data: MediaQueryData(
        size: size,
        textScaler: textScaler,
        disableAnimations: disableAnimations,
      ),
      child: Directionality(
        textDirection: textDirection,
        child: Density(
          initialMode: density,
          child: UiTheme(
            data: ui,
            child: DefaultTextStyle(
              style: ui.type.body.copyWith(color: ui.color.ink),
              child: ColoredBox(
                color: ui.color.ground,
                child: Align(child: child),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

/// How the focused element of a control answers the activation keys.
///
/// Added in wave 1 by the inputs family. Clause 3 of 10 section 2 reads
/// "`Space` and `Enter` activate", which is true of every control the system
/// has except a text editor, where `Space` types a space and `Enter` submits
/// through the input action. The SDK enforces that: while an editor holds
/// focus, `DefaultTextEditingShortcuts` maps `Space` to
/// `DoNothingAndStopPropagationTextIntent`, so nothing above the editor ever
/// sees the key. A field cannot both be typable and consume the space bar.
enum ControlActivation {
  /// `Space` and `Enter` activate the control. The default, and every control
  /// that is not a text editor.
  keys,

  /// The focused element is a text editor, so the activation keys belong to
  /// it. The clause becomes the opposite assertion, and a stronger one:
  /// nothing above the editor may consume either key, because a shortcut that
  /// swallows the space bar makes the field impossible to type in.
  textEditing,
}

/// Asserts every clause of 10 section 2 that a test can check.
///
/// [build] is called with a context inside the harness, so a control can read
/// `context.ui` while it is being built. [semanticsLabel] is the label the
/// control is expected to publish. Set [disabledWithReason] when [build]
/// returns the control in its disabled state, which is the state this product
/// cares most about: a control the server forbids still has to say why. Pass
/// [hasRole] for a control whose role is not one of the six common flags.
Future<void> expectControlContract(
  WidgetTester tester,
  Widget Function(BuildContext context) build, {
  required String semanticsLabel,
  bool disabledWithReason = false,
  ControlActivation activation = ControlActivation.keys,
  bool Function(SemanticsFlags flags)? hasRole,
}) async {
  // Disposed at the end of this function rather than in a tear down:
  // `flutter_test` verifies that no handle is live when the test body
  // returns, which is before tear downs run.
  final SemanticsHandle semantics = tester.ensureSemantics();

  // Clause 2. The hit box is at least 48 by 48 in both densities. Density
  // changes the visual size and the padding; it never shrinks this.
  for (final UiDensityMode density in UiDensityMode.values) {
    await tester.pumpWidget(
      uiHarness(density: density, child: Builder(builder: build)),
    );
    await tester.pumpAndSettle();
    final Size size = tester.getSize(find.bySemanticsLabel(semanticsLabel));
    expect(
      size.width,
      greaterThanOrEqualTo(UiDensity.hitBox),
      reason: '$semanticsLabel is ${size.width} wide in ${density.name}',
    );
    expect(
      size.height,
      greaterThanOrEqualTo(UiDensity.hitBox),
      reason: '$semanticsLabel is ${size.height} tall in ${density.name}',
    );
  }

  // Clause 5. A label that stands alone, an enabled flag, and for a disabled
  // control the reason on the hint.
  await tester.pumpWidget(uiHarness(child: Builder(builder: build)));
  await tester.pumpAndSettle();
  final Finder control = find.bySemanticsLabel(semanticsLabel);
  expect(
    control,
    findsOneWidget,
    reason: 'the control publishes no node labelled "$semanticsLabel"',
  );
  final SemanticsNode node = tester.getSemantics(control);
  final SemanticsData data = node.getSemanticsData();
  final SemanticsFlags flags = data.flagsCollection;
  expect(data.label, semanticsLabel);
  expect(
    hasRole?.call(flags) ??
        (flags.isButton ||
            flags.isLink ||
            flags.isTextField ||
            flags.isChecked != CheckedState.none ||
            flags.isToggled != Tristate.none ||
            flags.isSelected != Tristate.none),
    isTrue,
    reason:
        '"$semanticsLabel" has no role flag, so a screen reader announces it '
        'as text (10 section 2 clause 5)',
  );

  if (disabledWithReason) {
    expect(
      flags.isEnabled,
      Tristate.isFalse,
      reason: 'a disabled control reports enabled false',
    );
    expect(
      data.hint,
      isNotEmpty,
      reason:
          'a disabled control in this product carries the reason the server '
          'forbids the decision (03 section 3.6)',
    );
    semantics.dispose();
    return;
  }

  // Clause 3. Focusable, and both Space and Enter go where they belong.
  //
  // Checked by whether the focused control consumed the key rather than by
  // counting callbacks, because the callback belongs to the caller. A control
  // that forgot its activation shortcuts leaves the event unhandled, which is
  // exactly the defect this clause exists to catch. A text editor is the
  // mirror image: see [ControlActivation].
  for (final LogicalKeyboardKey key in <LogicalKeyboardKey>[
    LogicalKeyboardKey.space,
    LogicalKeyboardKey.enter,
  ]) {
    await tester.pumpWidget(uiHarness(child: Builder(builder: build)));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    final BuildContext? focused = FocusManager.instance.primaryFocus?.context;
    expect(
      focused,
      isNotNull,
      reason: '"$semanticsLabel" did not take keyboard focus',
    );
    switch (activation) {
      case ControlActivation.keys:
        final Action<ActivateIntent>? action =
            Actions.maybeFind<ActivateIntent>(focused!);
        expect(
          action,
          isNotNull,
          reason: '"$semanticsLabel" has no ActivateIntent action',
        );
        expect(
          action!.isActionEnabled,
          isTrue,
          reason: '"$semanticsLabel" has a disabled ActivateIntent action',
        );
      case ControlActivation.textEditing:
        expect(
          focused!.findAncestorStateOfType<EditableTextState>(),
          isNotNull,
          reason:
              '"$semanticsLabel" declares textEditing activation, but what '
              'took focus is not a text editor',
        );
    }
    final bool handled = await simulateKeyDownEvent(key);
    await simulateKeyUpEvent(key);
    await tester.pumpAndSettle();
    expect(
      handled,
      activation == ControlActivation.keys,
      reason: switch (activation) {
        ControlActivation.keys =>
          '${key.keyLabel} was not handled by "$semanticsLabel"',
        ControlActivation.textEditing =>
          '${key.keyLabel} was consumed above the editor in '
              '"$semanticsLabel", so the reviewer cannot type it',
      },
    );
  }

  // Clause 4. The focus ring is drawn for keyboard focus and not for a
  // pointer press.
  await tester.pumpWidget(uiHarness(child: Builder(builder: build)));
  await tester.pumpAndSettle();
  FocusManager.instance.highlightStrategy =
      FocusHighlightStrategy.alwaysTraditional;
  await tester.sendKeyEvent(LogicalKeyboardKey.tab);
  await tester.pumpAndSettle();
  expect(
    _focusRings(tester),
    greaterThan(0),
    reason: 'no focus ring under FocusHighlightMode.traditional',
  );

  FocusManager.instance.highlightStrategy = FocusHighlightStrategy.alwaysTouch;
  await tester.pumpWidget(uiHarness(child: Builder(builder: build)));
  await tester.pumpAndSettle();
  final TestGesture press = await tester.startGesture(
    tester.getCenter(control),
    kind: PointerDeviceKind.touch,
  );
  await tester.pumpAndSettle();
  expect(
    _focusRings(tester),
    0,
    reason: 'a pointer press drew a focus ring (10 section 2 clause 4)',
  );
  await press.up();
  await tester.pumpAndSettle();
  FocusManager.instance.highlightStrategy =
      FocusHighlightStrategy.automatic;

  // Clause 7. Two hundred percent text with no overflow and no clipped glyph.
  final List<FlutterErrorDetails> overflows = <FlutterErrorDetails>[];
  final FlutterExceptionHandler? previous = FlutterError.onError;
  FlutterError.onError = overflows.add;
  await tester.pumpWidget(
    uiHarness(
      textScaler: const TextScaler.linear(2),
      child: Builder(builder: build),
    ),
  );
  await tester.pumpAndSettle();
  FlutterError.onError = previous;
  expect(
    overflows.where(
      (FlutterErrorDetails d) => d.exceptionAsString().contains('overflowed'),
    ),
    isEmpty,
    reason:
        '"$semanticsLabel" overflows at 200 percent text. Heights grow and '
        'widths wrap; no fixed-height text box (10 section 2 clause 7).',
  );

  // Clause 8. Under reduced motion nothing is still animating after a
  // gesture, so no ticker is left running.
  await tester.pumpWidget(
    uiHarness(disableAnimations: true, child: Builder(builder: build)),
  );
  await tester.pumpAndSettle();
  await tester.tap(control);
  await tester.pump();
  expect(
    tester.binding.transientCallbackCount,
    0,
    reason:
        'an animation is still running under reduced motion (04 section 2.5)',
  );

  // Clause 9. The control builds right to left.
  await tester.pumpWidget(
    uiHarness(textDirection: TextDirection.rtl, child: Builder(builder: build)),
  );
  await tester.pumpAndSettle();
  expect(
    find.bySemanticsLabel(semanticsLabel),
    findsOneWidget,
    reason: '"$semanticsLabel" does not build under Directionality.rtl',
  );

  // 09 section 3.3, checked here because every control test pumps one window:
  // a single control is never a reason to exceed the budget.
  expectGlassBudget(tester);

  semantics.dispose();
}

/// How many focus rings are being painted.
int _focusRings(WidgetTester tester) => tester
    .widgetList<FocusRing>(find.byType(FocusRing))
    .where((FocusRing ring) => ring.visible)
    .length;

/// Asserts the window under [tester] is inside the glass budget.
///
/// The counting lives in `package:specimen_ui/testing.dart`, which imports no
/// `flutter_test`, so the application's golden harness can build the same
/// assertion without pulling `flutter_test` into its dependency graph.
void expectGlassBudget(
  WidgetTester tester, {
  int maxPanes = UiGlass.maxPanesPerWindow,
  int maxModal = UiGlass.maxModalPanes,
  String? window,
}) {
  final String where = window == null ? '' : ' at $window';
  expect(
    glassPaneCount(),
    lessThanOrEqualTo(maxPanes),
    reason:
        'there are ${glassPaneCount()} frosted panes on screen$where and the '
        'budget is $maxPanes (09 section 3.3). Every pane is a save layer; a '
        'list whose rows are glass is the expensive way to fail this.',
  );
  expect(
    modalGlassPaneCount(),
    lessThanOrEqualTo(maxModal),
    reason:
        'there are ${modalGlassPaneCount()} modal panes on screen$where and '
        'the budget is $maxModal. Two modals at once is a question the '
        'reviewer cannot answer.',
  );
}

/// Renders one gallery page for a golden.
///
/// The family slots call this so that every family golden is captured the same
/// way: the same window, the same four combinations, the same settle.
Future<void> goldenGalleryPage(
  WidgetTester tester,
  Widget page, {
  Brightness mode = Brightness.light,
  UiDensityMode density = UiDensityMode.touch,
  Size window = galleryWindow,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    uiHarness(
      brightness: mode,
      density: density,
      size: window,
      child: SizedBox.fromSize(size: window, child: page),
    ),
  );
  await tester.pumpAndSettle();
}

/// The window every gallery golden is captured at.
const Size galleryWindow = Size(1180, 820);

/// The file name of one gallery golden.
String galleryGoldenName(
  String family,
  String page, {
  required Brightness mode,
  required UiDensityMode density,
}) =>
    '$family-$page-${mode == Brightness.dark ? 'dark' : 'light'}-'
    '${density.name}.png';
