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
// `rendering.dart` for the paragraphs clauses 13 and 14 walk. It re-exports
// `semantics.dart`, which the harness also reads.
import 'package:flutter/rendering.dart';
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
///
/// [MediaQuery], [Density] and [UiTheme] sit **above** the app, which is
/// above its navigator, exactly as `main.dart` wraps `MaterialApp.router`. A
/// route pushed over the page therefore reads the density, the motion state
/// and the tokens the test asked for. Published inside `home` they are below
/// the navigator, and every modal falls back to
/// `UiTheme._fallback(Theme.of(context).brightness)`, which in a `WidgetsApp`
/// is always light: the first dark sheet and dialog goldens came out with a
/// light pane and an inverted primary button, which read as a token defect
/// and was a harness one.
///
/// [Directionality] stays inside `home`. `WidgetsApp` builds a `Localizations`
/// that publishes its own, taken from the locale, so one lifted above the app
/// would be shadowed for everything the app builds.
///
/// The harness publishes no text style of its own. It used to, and that was
/// the third defect of 11 section 0: a harness that hands every control a
/// correct `DefaultTextStyle` is a harness in which the framework fallback
/// can never appear, so nothing caught a route that inherited it. [UiTheme]
/// publishes the product's style now (11 section 5), and this tree is the
/// proof that it reaches a control, a route and an overlay alike.
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
  return MediaQuery(
    data: MediaQueryData(
      size: size,
      textScaler: textScaler,
      disableAnimations: disableAnimations,
    ),
    child: Density(
      initialMode: density,
      child: UiTheme(
        data: ui,
        child: WidgetsApp(
          color: ui.color.ground,
          debugShowCheckedModeBanner: false,
          localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
            DefaultMaterialLocalizations.delegate,
            DefaultWidgetsLocalizations.delegate,
          ],
          // A route, so the harness has what an application has: a navigator,
          // an overlay for `OverlayPortal` to hang from, and a focus scope
          // that takes focus on the first frame. Without a route nothing ever
          // holds focus and Tab traverses from nowhere.
          pageRouteBuilder:
              <T>(RouteSettings settings, WidgetBuilder builder) =>
                  PageRouteBuilder<T>(
                    settings: settings,
                    pageBuilder:
                        (
                          BuildContext context,
                          Animation<double> animation,
                          Animation<double> secondary,
                        ) => builder(context),
                  ),
          home: Directionality(
            textDirection: textDirection,
            child: ColoredBox(
              color: ui.color.ground,
              child: Align(child: child),
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

/// What a control does with less width than it needs (clause 15).
///
/// The harness cannot know a control's compact variants: 11 section 3.3 gives
/// a different row to each control, and only the control's own test knows
/// what a segmented row collapsing to a select, or a tile stepping down a
/// display role, looks like on screen. So the harness pumps the control at
/// each declared width and hands the assertion back to the caller, having
/// already checked the part that is the same for every control: that nothing
/// overflowed on the way there.
@immutable
class FitExpectation {
  /// Runs [check] at each of [widths].
  const FitExpectation({required this.check, this.widths = fitWidths});

  /// The widths the control is pumped at, widest first.
  final List<double> widths;

  /// Asserts what the control shows when it is given [width].
  final Future<void> Function(WidgetTester tester, double width) check;
}

/// The widths clauses 13 and 15 pump a control at (11 section 6).
///
/// 480 is a comfortable column, 360 a phone, 280 a narrow pane beside a
/// source image, and 200 the width the gallery shell left for its content
/// column when it kept a 220 dp sidebar at phone width, which is where the
/// wrapping labels of 11 section 0 were first seen.
const List<double> fitWidths = <double>[480, 360, 280, 200];

/// Asserts every clause of 10 section 2 that a test can check.
///
/// [build] is called with a context inside the harness, so a control can read
/// `context.ui` while it is being built. [semanticsLabel] is the label the
/// control is expected to publish. Set [disabledWithReason] when [build]
/// returns the control in its disabled state, which is the state this product
/// cares most about: a control the server forbids still has to say why. Pass
/// [hasRole] for a control whose role is not one of the six common flags.
///
/// **Clauses 13 to 15 are off by default, and a family turns them on.** They
/// were added by 11 section 6 after the five families had shipped, so a
/// control that has not had its fit pass would fail a clause nobody had
/// written it against yet, and a harness that fails everything says nothing.
/// A family slot converting its controls passes:
///
/// ```dart
/// await expectControlContract(
///   tester,
///   (BuildContext context) => const UiChip(label: 'Needs review'),
///   semanticsLabel: 'Needs review',
///   labelsNeverWrap: true,
///   geometryFromType: true,
///   fit: FitExpectation(
///     check: (WidgetTester tester, double width) async {
///       expect(find.text('Needs review'), findsOneWidget);
///     },
///   ),
/// );
/// ```
///
/// [wrappingContent] names the strings in the control that are content rather
/// than labels, and so wrap as content should (11 section 3.3): a row's
/// subtitle, help text, a banner's sentence. Anything else that lays out two
/// lines is the defect clause 13 exists to catch.
Future<void> expectControlContract(
  WidgetTester tester,
  Widget Function(BuildContext context) build, {
  required String semanticsLabel,
  bool disabledWithReason = false,
  ControlActivation activation = ControlActivation.keys,
  bool Function(SemanticsFlags flags)? hasRole,
  bool labelsNeverWrap = false,
  Set<String> wrappingContent = const <String>{},
  bool geometryFromType = false,
  FitExpectation? fit,
}) async {
  // Released on the way out rather than in a tear down, and in a `finally`
  // rather than at the end: `flutter_test` verifies that no handle is live
  // when the test body returns, which is before tear downs run, so a contract
  // that fails a clause would otherwise report a leaked handle on top of the
  // failure it found.
  final SemanticsHandle semantics = tester.ensureSemantics();
  try {
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
      await _expectFitClauses(
        tester,
        build,
        semanticsLabel: semanticsLabel,
        labelsNeverWrap: labelsNeverWrap,
        wrappingContent: wrappingContent,
        geometryFromType: geometryFromType,
        fit: fit,
        // A disabled control is still a control the reviewer reads, so its
        // labels and its geometry are held to the same rule. Its hit box is
        // not: there is no gesture to size.
        hitBox: false,
      );
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

    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTouch;
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
      uiHarness(
        textDirection: TextDirection.rtl,
        child: Builder(builder: build),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel(semanticsLabel),
      findsOneWidget,
      reason: '"$semanticsLabel" does not build under Directionality.rtl',
    );

    await _expectFitClauses(
      tester,
      build,
      semanticsLabel: semanticsLabel,
      labelsNeverWrap: labelsNeverWrap,
      wrappingContent: wrappingContent,
      geometryFromType: geometryFromType,
      fit: fit,
    );

    // 09 section 3.3, checked here because every control test pumps one window:
    // a single control is never a reason to exceed the budget.
    expectGlassBudget(tester);
  } finally {
    semantics.dispose();
  }
}

/// Clauses 13, 14 and 15 of 10 section 2, each off unless the caller asks.
///
/// One helper rather than three, because all three pump the same control
/// through the same harness and differ only in what they vary and what they
/// then read. Called from both ends of [expectControlContract], so a disabled
/// control is held to the same rules as an enabled one.
Future<void> _expectFitClauses(
  WidgetTester tester,
  Widget Function(BuildContext context) build, {
  required String semanticsLabel,
  required bool labelsNeverWrap,
  required Set<String> wrappingContent,
  required bool geometryFromType,
  required FitExpectation? fit,
  bool hitBox = true,
}) async {
  // Clause 13. A label never wraps. Overflow is not this clause's business:
  // a control with no compact variant is wider than 200 dp by design and the
  // parent is what arranges it (11 section 3.3, rule 2). What is never
  // allowed is a label breaking onto a second line, which at 200 dp breaks it
  // between its letters.
  if (labelsNeverWrap) {
    for (final double width in fitWidths) {
      await _pumpAtWidth(tester, build, width);
      for (final RenderParagraph paragraph in _paragraphs(tester)) {
        final String text = _plainTextOf(paragraph);
        if (wrappingContent.contains(text)) continue;
        expect(
          _lineCount(paragraph),
          lessThanOrEqualTo(1),
          reason:
              '"$text" in "$semanticsLabel" lays out on more than one line at '
              '$width dp. A label is one line (10 section 2 clause 13); if '
              'this string is content rather than a label, name it in '
              'wrappingContent.',
        );
      }
    }
  }

  // Clause 14. Geometry derives from type. Nothing that holds text is a
  // constant height, so growing the text grows the control instead of
  // clipping it, and the hit box holds at 48 the whole way up.
  if (geometryFromType) {
    for (final double scale in <double>[1, 1.3, 2]) {
      final List<FlutterErrorDetails> overflows = await _pumpCollecting(
        tester,
        () => tester.pumpWidget(
          uiHarness(
            textScaler: TextScaler.linear(scale),
            child: Builder(builder: build),
          ),
        ),
      );
      expect(
        _overflowsIn(overflows),
        isEmpty,
        reason:
            '"$semanticsLabel" overflows at text scale $scale. A height that '
            'holds text is max(density height, scaled line height plus twice '
            'the inset), never a constant (10 section 2 clause 14).',
      );
      for (final RenderParagraph paragraph in _paragraphs(tester)) {
        expect(
          paragraph.didExceedMaxLines,
          isFalse,
          reason:
              '"${_plainTextOf(paragraph)}" in "$semanticsLabel" is truncated '
              'at text scale $scale with the control at its own width. A '
              'glyph is never clipped by the text growing (clause 14).',
        );
      }
      if (hitBox) {
        final Size size = tester.getSize(find.bySemanticsLabel(semanticsLabel));
        expect(
          <double>[size.width, size.height],
          everyElement(greaterThanOrEqualTo(UiDensity.hitBox)),
          reason:
              '"$semanticsLabel" is ${size.width} by ${size.height} at text '
              'scale $scale. The hit box is 48 dp at every scale (clause 14).',
        );
      }
    }
  }

  // Clause 15. Fit is declared. The harness owns the half that is the same
  // for every control, that it reaches each width without overflowing, and
  // the control's own test owns the half that is not.
  if (fit != null) {
    for (final double width in fit.widths) {
      final List<FlutterErrorDetails> overflows = await _pumpCollecting(
        tester,
        () => _pumpAtWidth(tester, build, width),
      );
      expect(
        _overflowsIn(overflows),
        isEmpty,
        reason:
            '"$semanticsLabel" overflows at $width dp. A control that '
            'declares its fit switches to its compact variant and then '
            'ellipsises; it never overflows the width it was given '
            '(10 section 2 clause 15).',
      );
      await fit.check(tester, width);
    }
  }
}

/// Pumps [build] in a column exactly [width] wide, in a window that narrow.
///
/// Both, because a control reads its constraints and anything around it reads
/// the window: a control given 280 dp in a 1400 dp window is not the case the
/// gallery found the wrapping labels in.
Future<void> _pumpAtWidth(
  WidgetTester tester,
  Widget Function(BuildContext context) build,
  double width,
) async {
  await tester.pumpWidget(
    uiHarness(
      size: Size(width, 800),
      child: SizedBox(width: width, child: Builder(builder: build)),
    ),
  );
  await tester.pumpAndSettle();
}

/// Runs [pump] with the framework's error handler diverted, and returns what
/// it reported.
///
/// A layout error is reported rather than thrown, so the only way to assert
/// on one is to catch it here and let the caller decide whether this clause
/// cares about it.
Future<List<FlutterErrorDetails>> _pumpCollecting(
  WidgetTester tester,
  Future<void> Function() pump,
) async {
  final List<FlutterErrorDetails> reported = <FlutterErrorDetails>[];
  final FlutterExceptionHandler? previous = FlutterError.onError;
  FlutterError.onError = reported.add;
  try {
    await pump();
    await tester.pumpAndSettle();
  } finally {
    FlutterError.onError = previous;
  }
  return reported;
}

/// The overflow reports among [reported].
Iterable<FlutterErrorDetails> _overflowsIn(
  List<FlutterErrorDetails> reported,
) => reported.where(
  (FlutterErrorDetails d) => d.exceptionAsString().contains('overflowed'),
);

/// Every paragraph on screen, once each.
///
/// `allRenderObjects` walks elements rather than render objects, so every
/// widget between a `Text` and its paragraph reports the same one again.
List<RenderParagraph> _paragraphs(WidgetTester tester) =>
    tester.allRenderObjects.whereType<RenderParagraph>().toSet().toList();

/// The characters [paragraph] was given, without the semantics substitutions
/// that never reach the screen.
String _plainTextOf(RenderParagraph paragraph) =>
    paragraph.text.toPlainText(includeSemanticsLabels: false);

/// How many lines [paragraph] laid out.
///
/// Counted from the boxes the paragraph reports for its own text rather than
/// from its height, because a height tells you nothing without knowing which
/// role each run in the line is set in. Boxes on one line share a top edge;
/// rounding to a quarter pixel absorbs the subpixel difference between two
/// runs of different sizes on the same line.
int _lineCount(RenderParagraph paragraph) {
  final String plain = _plainTextOf(paragraph);
  if (plain.isEmpty) return 0;
  final List<TextBox> boxes = paragraph.getBoxesForSelection(
    TextSelection(baseOffset: 0, extentOffset: plain.length),
  );
  return <int>{for (final TextBox box in boxes) (box.top * 4).round()}.length;
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
