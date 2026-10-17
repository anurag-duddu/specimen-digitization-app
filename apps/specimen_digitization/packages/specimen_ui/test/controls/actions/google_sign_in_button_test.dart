// `UiGoogleSignInButton` is Google's button, so what it draws is Google's page
// (https://developers.google.com/identity/branding-guidelines, the custom
// button section, updated 2026-07-07), and what the design system adds to it is
// the control contract. The figures below are written out here from the page
// rather than read back from `GoogleSignInBrand`, so a change to the brand
// class that drifts from the page fails a test instead of passing one.
//
// The owner's decision that the button looks the same on every platform is the
// last group: every `TargetPlatform` draws the same pixels, and the component's
// source names no platform.

import 'dart:io';
import 'dart:ui' as ui show Image;
import 'dart:ui' show Tristate;

import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

const String _label = 'Sign in with Google';

/// What the page's table gives each theme, as the integers it prints.
const Color _lightFill = Color(0xFFFFFFFF);
const Color _lightStroke = Color(0xFF747775);
const Color _lightText = Color(0xFF1F1F1F);
const Color _darkFill = Color(0xFF131314);
const Color _darkStroke = Color(0xFF8E918F);
const Color _darkText = Color(0xFFE3E3E3);

void _noop() {}

/// The button with a callback that does nothing.
const Widget _plain = UiGoogleSignInButton(onPressed: _noop);

/// [_plain], in the form the contract's `build` callback takes.
Widget _button(BuildContext context) => _plain;

/// Clause 15. 11 section 3.3 gives Google's button no compact variant: the
/// label is whole at every width, wrapped when it must be, never cut.
Future<void> _stillWhole(WidgetTester tester, double width) async {
  expect(find.byType(UiGoogleSignInButton), findsOneWidget, reason: '$width');
  expect(find.text(_label), findsOneWidget, reason: 'at $width dp');
  expect(
    tester.renderObject<RenderParagraph>(find.text(_label)).didExceedMaxLines,
    isFalse,
    reason: 'the label is wrapped, not cut, at $width dp',
  );
  expect(
    tester.getSize(find.byType(UiGoogleSignInButton)).width,
    lessThanOrEqualTo(width),
    reason: 'the button fits the $width dp it was given',
  );
}

/// The painted button: the box that carries the fill and the outline, not the
/// 48 dp target around it and not the state layer over it.
Finder _face(Color fill) => find.byWidgetPredicate(
  (Widget widget) =>
      widget is DecoratedBox &&
      widget.decoration is ShapeDecoration &&
      (widget.decoration as ShapeDecoration).color == fill,
);

ShapeDecoration _decoration(WidgetTester tester, Finder face) =>
    tester.widget<DecoratedBox>(face).decoration as ShapeDecoration;

/// The paragraph the label is drawn in.
RenderParagraph _paragraph(WidgetTester tester) =>
    tester.renderObject<RenderParagraph>(find.text(_label));

/// How many lines the label laid out on.
int _lines(WidgetTester tester) {
  final RenderParagraph paragraph = _paragraph(tester);
  return <int>{
    for (final TextBox box in paragraph.getBoxesForSelection(
      const TextSelection(baseOffset: 0, extentOffset: _label.length),
    ))
      (box.top * 4).round(),
  }.length;
}

/// One drawing of the button: its box, its semantics and its pixels.
class _Drawn {
  const _Drawn(this.size, this.semantics, this.pixels);

  final Size size;
  final String semantics;
  final Uint8List pixels;
}

/// Pumps the button on [platform] and reads back what it drew.
Future<_Drawn> _draw(
  WidgetTester tester, {
  required TargetPlatform? platform,
  required Brightness brightness,
}) async {
  debugDefaultTargetPlatformOverride = platform;
  final GlobalKey key = GlobalKey();
  final SemanticsHandle semantics = tester.ensureSemantics();
  try {
    await tester.pumpWidget(
      uiHarness(
        brightness: brightness,
        child: RepaintBoundary(
          key: key,
          child: const UiGoogleSignInButton(onPressed: _noop),
        ),
      ),
    );
    // The "G" is decoded off the frame loop, so a pixel read has to wait for
    // it or it reads the button without its logo.
    await tester.runAsync(() async {
      for (final Element element in tester.elementList(find.byType(Image))) {
        await precacheImage((element.widget as Image).image, element);
      }
    });
    await tester.pumpAndSettle();
    final RenderRepaintBoundary boundary =
        key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final Uint8List pixels = (await tester.runAsync(() async {
      final ui.Image image = await boundary.toImage(pixelRatio: 3);
      final ByteData? bytes = await image.toByteData();
      image.dispose();
      return bytes!.buffer.asUint8List();
    }))!;
    return _Drawn(
      tester.getSize(find.byType(UiGoogleSignInButton)),
      tester
          .getSemantics(find.bySemanticsLabel(_label))
          .getSemanticsData()
          .toString(),
      pixels,
    );
  } finally {
    semantics.dispose();
    debugDefaultTargetPlatformOverride = null;
  }
}

void main() {
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
    debugDefaultTargetPlatformOverride = null;
  });

  group('the control contract', () {
    testWidgets('it satisfies the control contract', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        _button,
        semanticsLabel: _label,
        // Clause 13 is not claimed: Google's call to action wraps rather than
        // ending in an ellipsis. The test further down says what it does
        // instead.
        geometryFromType: true,
        fit: const FitExpectation(check: _stillWhole),
      );
    });

    testWidgets('a disabled button satisfies the contract and states the '
        'reason', (WidgetTester tester) async {
      await expectControlContract(
        tester,
        (BuildContext context) => const UiGoogleSignInButton(
          disabledReason: 'Email sign-in is already in progress.',
        ),
        semanticsLabel: _label,
        disabledWithReason: true,
        geometryFromType: true,
        fit: const FitExpectation(check: _stillWhole),
      );
    });

    testWidgets('a busy button satisfies the contract with its action absent', (
      WidgetTester tester,
    ) async {
      // Busy is disabled to the semantics tree and to the keyboard, and it
      // still has to say why: the caller's reason is its hint.
      await expectControlContract(
        tester,
        (BuildContext context) => const UiGoogleSignInButton(
          busy: true,
          disabledReason: 'Finish or cancel in the Google sign-in window.',
        ),
        semanticsLabel: _label,
        disabledWithReason: true,
        geometryFromType: true,
        fit: const FitExpectation(check: _stillWhole),
      );
    });
  });

  group("Google's figures", () {
    testWidgets('it is the pill of Google drawing: 40 high, paddings 12, 10 '
        'and 12, a 20 by 20 G', (WidgetTester tester) async {
      await tester.pumpWidget(uiHarness(child: _plain));
      await tester.pumpAndSettle();
      final Finder face = _face(_lightFill);
      final Rect button = tester.getRect(face);
      final Rect logo = tester.getRect(find.byType(Image));
      final Rect text = tester.getRect(find.text(_label));
      expect(button.height, 40, reason: 'the button is 40 high at scale 1.0');
      expect(logo.size, const Size(20, 20), reason: 'the G is 20 by 20');
      expect(logo.left - button.left, 12, reason: '12 before the G');
      expect(text.left - logo.right, 10, reason: '10 between the G and text');
      expect(button.right - text.right, 12, reason: '12 after the text');
      expect(
        logo.center.dy,
        button.center.dy,
        reason: 'the G is centred on the button',
      );
      expect(text.height, 20, reason: 'the label sits in the 20 of 14/20');
      expect(
        button.width,
        12 + 20 + 10 + text.width + 12,
        reason: 'the button takes the width its content needs',
      );
    });

    testWidgets('its edge is a capsule with a 1 dp outline drawn inside', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(uiHarness(child: _plain));
      await tester.pumpAndSettle();
      final ShapeDecoration painted = _decoration(tester, _face(_lightFill));
      expect(painted.shape, isA<StadiumBorder>());
      expect((painted.shape as StadiumBorder).side.width, 1);
      expect(
        (painted.shape as StadiumBorder).side.strokeAlign,
        BorderSide.strokeAlignInside,
        reason: 'the page says "1px, inside"',
      );
    });

    testWidgets("light and dark are Google's two themes, whatever the "
        'platform', (WidgetTester tester) async {
      final Map<Brightness, (Color, Color, Color)> themes =
          <Brightness, (Color, Color, Color)>{
            Brightness.light: (_lightFill, _lightStroke, _lightText),
            Brightness.dark: (_darkFill, _darkStroke, _darkText),
          };
      for (final MapEntry<Brightness, (Color, Color, Color)> theme
          in themes.entries) {
        final (Color fill, Color stroke, Color text) = theme.value;
        await tester.pumpWidget(
          uiHarness(brightness: theme.key, child: _plain),
        );
        await tester.pumpAndSettle();
        final ShapeDecoration painted = _decoration(tester, _face(fill));
        expect(
          (painted.shape as StadiumBorder).side.color,
          stroke,
          reason: '${theme.key.name} stroke',
        );
        expect(
          _paragraph(tester).text.style!.color,
          text,
          reason: '${theme.key.name} label',
        );
      }
    });

    testWidgets('the label is Google Sans Medium 14/20, set in nothing else', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(uiHarness(child: _plain));
      await tester.pumpAndSettle();
      final TextStyle style = _paragraph(tester).text.style!;
      expect(style.fontFamily, 'packages/specimen_ui/GoogleSignInSans');
      expect(style.fontSize, 14);
      expect(style.fontWeight, FontWeight.w500);
      expect(style.height! * style.fontSize!, closeTo(20, 0.001));
      expect(
        style.inherit,
        isFalse,
        reason: 'the product face and its tracking are not inherited',
      );
    });

    testWidgets("the call to action is one of Google's three, not Google "
        'alone', (WidgetTester tester) async {
      expect(
        GoogleSignInBrand.label,
        isIn(const <String>[
          'Sign in with Google',
          'Sign up with Google',
          'Continue with Google',
        ]),
      );
      await tester.pumpWidget(uiHarness(child: _plain));
      expect(find.text(GoogleSignInBrand.label), findsOneWidget);
      expect(find.text(_label), findsOneWidget);
    });

    test("the files Google's button draws with are in the package", () {
      for (final String asset in <String>[
        GoogleSignInBrand.logoAsset,
        GoogleSignInBrand.fontAsset,
        'assets/google-sign-in/OFL.txt',
        'assets/google-sign-in/README.md',
      ]) {
        expect(File(asset).existsSync(), isTrue, reason: '$asset is missing');
      }
      final String pubspec = File('pubspec.yaml').readAsStringSync();
      expect(pubspec, contains('family: ${GoogleSignInBrand.fontFamily}'));
      expect(pubspec, contains(GoogleSignInBrand.fontAsset));
      expect(pubspec, contains('assets/google-sign-in/'));
    });

    testWidgets('the G is Google\'s file, drawn in colour at 20 by 20', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(uiHarness(child: _plain));
      final Image logo = tester.widget<Image>(find.byType(Image));
      expect(
        (logo.image as AssetImage).assetName,
        'assets/google-sign-in/google-g.png',
      );
      expect((logo.image as AssetImage).package, 'specimen_ui');
      expect(logo.color, isNull, reason: 'the page forbids a monochrome G');
      expect(logo.fit, BoxFit.contain, reason: 'the G is never stretched');
      expect(logo.excludeFromSemantics, isTrue);
    });
  });

  group('size', () {
    testWidgets('the 40 dp button sits inside the 48 dp hit box in both '
        'densities', (WidgetTester tester) async {
      for (final UiDensityMode density in UiDensityMode.values) {
        await tester.pumpWidget(uiHarness(density: density, child: _plain));
        await tester.pumpAndSettle();
        expect(
          tester.getSize(_face(_lightFill)).height,
          40,
          reason: 'the visual does not follow the density (${density.name})',
        );
        expect(
          tester.getSize(find.bySemanticsLabel(_label)).height,
          UiDensity.hitBox,
          reason: 'the target is 48 in ${density.name}',
        );
      }
    });

    testWidgets('text size grows the height and nothing else of the G', (
      WidgetTester tester,
    ) async {
      final Map<double, double> expected = <double, double>{
        1: 40,
        1.3: 46,
        2: 60,
      };
      for (final MapEntry<double, double> scale in expected.entries) {
        await tester.pumpWidget(
          uiHarness(textScaler: TextScaler.linear(scale.key), child: _plain),
        );
        await tester.pumpAndSettle();
        expect(
          tester.getSize(_face(_lightFill)).height,
          closeTo(scale.value, 0.01),
          reason: 'max(40, scaled 20 + 2 * 10) at ${scale.key}',
        );
        expect(
          tester.getSize(find.byType(Image)),
          const Size(20, 20),
          reason: 'the page says the G does not change size',
        );
        expect(
          tester.getSize(find.bySemanticsLabel(_label)).height,
          greaterThanOrEqualTo(UiDensity.hitBox),
        );
      }
    });

    testWidgets('given less than it needs, the label wraps whole rather than '
        'ending in an ellipsis', (WidgetTester tester) async {
      final List<FlutterErrorDetails> errors = <FlutterErrorDetails>[];
      final FlutterExceptionHandler? previous = FlutterError.onError;
      FlutterError.onError = errors.add;
      try {
        for (final double width in <double>[280, 200]) {
          await tester.pumpWidget(
            uiHarness(
              size: Size(width, 800),
              textScaler: const TextScaler.linear(2),
              child: SizedBox(width: width, child: _plain),
            ),
          );
          await tester.pumpAndSettle();
          final RenderParagraph paragraph = _paragraph(tester);
          expect(paragraph.maxLines, isNull, reason: 'at $width dp');
          expect(paragraph.didExceedMaxLines, isFalse, reason: 'at $width dp');
          expect(paragraph.text.toPlainText(), _label, reason: 'at $width dp');
          expect(
            _lines(tester),
            greaterThan(1),
            reason: 'at 200 percent text in $width dp the label needs lines',
          );
          expect(
            tester.getSize(find.byType(UiGoogleSignInButton)).width,
            lessThanOrEqualTo(width),
          );
          expect(tester.getSize(find.byType(Image)), const Size(20, 20));
        }
      } finally {
        FlutterError.onError = previous;
      }
      expect(
        errors.where((FlutterErrorDetails d) => '$d'.contains('overflowed')),
        isEmpty,
      );
    });

    testWidgets('the window does not stretch it: the same button in a phone '
        'and in a desktop browser', (WidgetTester tester) async {
      addTearDown(tester.view.reset);
      tester.view.devicePixelRatio = 1;
      final Set<Size> faces = <Size>{};
      for (final double width in <double>[320, 390, 768, 1024, 1440]) {
        tester.view.physicalSize = Size(width, 900);
        final GlobalKey column = GlobalKey();
        await tester.pumpWidget(
          uiHarness(
            size: Size(width, 900),
            child: SizedBox(
              width: width - 32,
              child: Column(
                key: column,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                mainAxisSize: MainAxisSize.min,
                children: const <Widget>[_plain],
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(tester.getSize(find.byKey(column)).width, width - 32);
        faces.add(tester.getSize(_face(_lightFill)));
        expect(
          tester.getCenter(_face(_lightFill)).dx,
          closeTo(tester.getCenter(find.byKey(column)).dx, 0.01),
          reason: 'it is centred in the column it is given at $width dp',
        );
      }
      expect(faces, hasLength(1), reason: 'one size at every window width');
    });

    testWidgets('it builds right to left with the G at the start', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(textDirection: TextDirection.rtl, child: _plain),
      );
      await tester.pumpAndSettle();
      final Rect button = tester.getRect(_face(_lightFill));
      expect(
        button.right - tester.getRect(find.byType(Image)).right,
        12,
        reason: 'the 12 before the G is on the right in a right to left script',
      );
    });
  });

  group('states', () {
    testWidgets('it activates by tap, Space and Enter', (
      WidgetTester tester,
    ) async {
      int pressed = 0;
      await tester.pumpWidget(
        uiHarness(child: UiGoogleSignInButton(onPressed: () => pressed++)),
      );
      await tester.tap(find.byType(UiGoogleSignInButton));
      await tester.pumpAndSettle();
      expect(pressed, 1);
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.sendKeyEvent(LogicalKeyboardKey.space);
      await tester.pumpAndSettle();
      expect(pressed, 2);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(pressed, 3);
    });

    testWidgets('pressed lifts the button toward its label colour at the '
        "contract's 12 percent and changes none of Google's colours", (
      WidgetTester tester,
    ) async {
      late UiThemeData ui;
      await tester.pumpWidget(
        uiHarness(
          child: Builder(
            builder: (BuildContext context) {
              ui = context.ui;
              return _button(context);
            },
          ),
        ),
      );
      final TestGesture press = await tester.startGesture(
        tester.getCenter(find.byType(UiGoogleSignInButton)),
      );
      await tester.pump(const Duration(milliseconds: 200));
      final StateLayer layer = tester.widget<StateLayer>(
        find.byType(StateLayer),
      );
      expect(layer.states, contains(WidgetState.pressed));
      final AnimatedContainer paint = tester.widget<AnimatedContainer>(
        find.descendant(
          of: find.byType(StateLayer),
          matching: find.byType(AnimatedContainer),
        ),
      );
      final ShapeDecoration overlay = paint.decoration! as ShapeDecoration;
      expect(
        overlay.color,
        _lightText.withValues(alpha: ui.color.pressedOpacity),
      );
      expect(ui.color.pressedOpacity, 0.12);
      expect(overlay.shape, isA<StadiumBorder>());
      expect(
        _face(_lightFill),
        findsOneWidget,
        reason: 'the fill is unchanged',
      );
      await press.up();
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<StateLayer>(find.byType(StateLayer))
            .states
            .contains(WidgetState.pressed),
        isFalse,
      );
    });

    testWidgets('hover lifts it at 8 percent in light and 10 in dark', (
      WidgetTester tester,
    ) async {
      final TestGesture pointer = await tester.createGesture(
        kind: PointerDeviceKind.mouse,
      );
      await pointer.addPointer(location: Offset.zero);
      addTearDown(pointer.removePointer);
      for (final Brightness mode in Brightness.values) {
        final Color text = mode == Brightness.dark ? _darkText : _lightText;
        await pointer.moveTo(Offset.zero);
        await tester.pumpWidget(uiHarness(brightness: mode, child: _plain));
        await tester.pumpAndSettle();
        await pointer.moveTo(
          tester.getCenter(find.byType(UiGoogleSignInButton)),
        );
        await tester.pump(const Duration(milliseconds: 200));
        final ShapeDecoration overlay =
            tester
                    .widget<AnimatedContainer>(
                      find.descendant(
                        of: find.byType(StateLayer),
                        matching: find.byType(AnimatedContainer),
                      ),
                    )
                    .decoration!
                as ShapeDecoration;
        expect(
          overlay.color,
          text.withValues(alpha: mode == Brightness.dark ? 0.10 : 0.08),
          reason: mode.name,
        );
      }
    });

    testWidgets('keyboard focus rings the capsule, and a pointer press does '
        'not', (WidgetTester tester) async {
      await tester.pumpWidget(uiHarness(child: _plain));
      expect(
        tester.widget<FocusRing>(find.byType(FocusRing)).visible,
        isFalse,
        reason: 'nothing is focused yet',
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      final FocusRing ring = tester.widget<FocusRing>(find.byType(FocusRing));
      expect(ring.visible, isTrue);
      expect(
        ring.shape,
        FocusRingShape.stadium,
        reason: 'a capsule is ringed by a stadium, concentric with its edge',
      );

      FocusManager.instance.primaryFocus?.unfocus();
      FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.alwaysTouch;
      await tester.pumpAndSettle();
      final TestGesture touch = await tester.startGesture(
        tester.getCenter(find.byType(UiGoogleSignInButton)),
        kind: PointerDeviceKind.touch,
      );
      await tester.pumpAndSettle();
      expect(
        tester.widget<FocusRing>(find.byType(FocusRing)).visible,
        isFalse,
        reason: 'the ring is for the keyboard (10 section 2 clause 4)',
      );
      await touch.up();
    });

    testWidgets('a disabled button fades to 38 percent, refuses a press and '
        'says why on its hint and on a tooltip', (WidgetTester tester) async {
      final SemanticsHandle semantics = tester.ensureSemantics();
      await tester.pumpWidget(
        uiHarness(
          child: const UiGoogleSignInButton(
            disabledReason: 'Email sign-in is already in progress.',
          ),
        ),
      );
      await tester.pumpAndSettle();
      final Finder fade = find.descendant(
        of: find.byType(UiGoogleSignInButton),
        matching: find.byType(Opacity),
      );
      expect(tester.widget<Opacity>(fade).opacity, 0.38);
      final SemanticsData data = tester
          .getSemantics(find.bySemanticsLabel(_label))
          .getSemanticsData();
      expect(data.flagsCollection.isEnabled, Tristate.isFalse);
      expect(data.hint, 'Email sign-in is already in progress.');
      expect(
        find.text('Email sign-in is already in progress.'),
        findsNothing,
        reason: 'the reason is not on screen until it is asked for',
      );
      await tester.tap(find.byType(UiGoogleSignInButton));
      await tester.pumpAndSettle();
      expect(
        find.text('Email sign-in is already in progress.'),
        findsOneWidget,
        reason:
            'a press on a disabled control gives the reason a place to show',
      );
      semantics.dispose();
    });

    testWidgets('an enabled button is not faded', (WidgetTester tester) async {
      await tester.pumpWidget(uiHarness(child: _plain));
      expect(
        find.descendant(
          of: find.byType(UiGoogleSignInButton),
          matching: find.byType(Opacity),
        ),
        findsNothing,
      );
    });

    testWidgets('busy keeps the enabled paint, refuses a second press and '
        'keeps focus where it was', (WidgetTester tester) async {
      int pressed = 0;
      final FocusNode node = FocusNode(debugLabel: 'google');
      addTearDown(node.dispose);
      Widget build({required bool busy}) => uiHarness(
        child: UiGoogleSignInButton(
          onPressed: () => pressed++,
          busy: busy,
          focusNode: node,
          disabledReason: busy
              ? 'Finish or cancel in the Google window.'
              : null,
        ),
      );
      await tester.pumpWidget(build(busy: false));
      node.requestFocus();
      await tester.pumpAndSettle();
      expect(node.hasPrimaryFocus, isTrue);

      await tester.pumpWidget(build(busy: true));
      await tester.pumpAndSettle();
      expect(
        find.descendant(
          of: find.byType(UiGoogleSignInButton),
          matching: find.byType(Opacity),
        ),
        findsNothing,
        reason: 'a button that is working is busy, not forbidden',
      );
      expect(node.hasPrimaryFocus, isTrue, reason: 'focus stays put');
      await tester.tap(find.byType(UiGoogleSignInButton));
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(pressed, 0, reason: 'busy refuses activation');
    });

    testWidgets('one semantics node: the label, a button, no second G', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle semantics = tester.ensureSemantics();
      await tester.pumpWidget(uiHarness(child: _plain));
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel(_label), findsOneWidget);
      final SemanticsData data = tester
          .getSemantics(find.bySemanticsLabel(_label))
          .getSemanticsData();
      expect(data.label, _label);
      expect(data.flagsCollection.isButton, isTrue);
      expect(data.flagsCollection.isEnabled, Tristate.isTrue);
      expect(
        data.hasAction(SemanticsAction.tap),
        isTrue,
        reason: 'a screen reader can activate it',
      );
      semantics.dispose();
    });
  });

  group('motion', () {
    testWidgets('the press layer follows the motion tokens, so reduced motion '
        'snaps it', (WidgetTester tester) async {
      Duration layerDuration() => tester
          .widget<AnimatedContainer>(
            find.descendant(
              of: find.byType(StateLayer),
              matching: find.byType(AnimatedContainer),
            ),
          )
          .duration;

      await tester.pumpWidget(uiHarness(child: _plain));
      await tester.pumpAndSettle();
      final TestGesture press = await tester.startGesture(
        tester.getCenter(find.byType(UiGoogleSignInButton)),
      );
      await tester.pump();
      expect(
        layerDuration(),
        MotionTokens.pressInRaw,
        reason: 'with animations on, the press fades in over 60 ms',
      );
      await press.up();
      await tester.pumpAndSettle();

      await tester.pumpWidget(
        uiHarness(disableAnimations: true, child: _plain),
      );
      await tester.pumpAndSettle();
      final TestGesture quick = await tester.startGesture(
        tester.getCenter(find.byType(UiGoogleSignInButton)),
      );
      await tester.pump();
      expect(
        layerDuration(),
        Duration.zero,
        reason: 'MediaQuery.disableAnimations collapses the press fade',
      );
      expect(
        tester.binding.transientCallbackCount,
        0,
        reason: 'no ticker is left running under reduced motion',
      );
      await quick.up();
      await tester.pump();
      expect(tester.binding.transientCallbackCount, 0);
    });

    testWidgets('the button starts no animation of its own', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(uiHarness(child: _plain));
      await tester.pumpAndSettle();
      expect(tester.binding.transientCallbackCount, 0);
    });
  });

  group(
    'identity does not vary with the platform (09 section 2, principle 5)',
    () {
      testWidgets('every platform draws the same size, the same semantics and '
          'the same pixels, in both modes', (WidgetTester tester) async {
        for (final Brightness mode in Brightness.values) {
          final _Drawn reference = await _draw(
            tester,
            platform: null,
            brightness: mode,
          );
          int saturated = 0;
          int ink = 0;
          for (int i = 0; i < reference.pixels.length; i += 4) {
            final int r = reference.pixels[i];
            final int g = reference.pixels[i + 1];
            final int b = reference.pixels[i + 2];
            final int spread =
                <int>[r, g, b].reduce((int a, int c) => a > c ? a : c) -
                <int>[r, g, b].reduce((int a, int c) => a < c ? a : c);
            if (spread > 120) saturated++;
            if (mode == Brightness.light
                ? r < 80 && g < 80 && b < 80
                : r > 180) {
              ink++;
            }
          }
          expect(
            saturated,
            greaterThan(100),
            reason:
                'the colour G is in the pixels (${mode.name}), so equality '
                'below compares a button with its logo and not a blank',
          );
          expect(ink, greaterThan(100), reason: 'the label is in the pixels');

          for (final TargetPlatform platform in TargetPlatform.values) {
            final _Drawn drawn = await _draw(
              tester,
              platform: platform,
              brightness: mode,
            );
            expect(
              drawn.size,
              reference.size,
              reason: '$platform ${mode.name}',
            );
            expect(
              drawn.semantics,
              reference.semantics,
              reason: '$platform ${mode.name}',
            );
            expect(
              listEquals(drawn.pixels, reference.pixels),
              isTrue,
              reason: '$platform ${mode.name} drew different pixels',
            );
          }
        }
      });

      test('the component and its brand class read no platform', () {
        final RegExp platform = RegExp(
          r'kIsWeb|kIsWasm|defaultTargetPlatform|TargetPlatform|'
          r'\bPlatform\b|\.platform\b|dart:io|dart\.library|Cupertino',
        );
        for (final String path in <String>[
          'lib/src/controls/actions/google_sign_in_button.dart',
          'lib/src/foundation/google_sign_in_brand.dart',
        ]) {
          final String code = File(path)
              .readAsStringSync()
              .split('\n')
              .where((String line) => !line.trimLeft().startsWith('//'))
              .join('\n');
          expect(
            platform.allMatches(code).map((RegExpMatch m) => m.group(0)),
            isEmpty,
            reason: '$path decides something from the platform',
          );
        }
      });
    },
  );
}
