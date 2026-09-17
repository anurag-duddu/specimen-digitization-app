// Text scale and the geometry that derives from it (11 section 2).
//
// The rule these pin is that nothing which holds text is a constant height.
// The numbers below are worked through in 11 section 2.2 and are the same
// numbers a control reproduces, so a change to a role's size or line height
// shows here before it shows as a clipped label at 200 percent text.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// `body` at scale 1.0: 15 times 1.45.
const double _bodyLineBox = 21.75;

/// Reads [read] at [scale].
Future<void> _atScale(
  WidgetTester tester,
  double scale,
  void Function(BuildContext context) read,
) async {
  await tester.pumpWidget(
    uiHarness(
      textScaler: TextScaler.linear(scale),
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
  test('every role splits its leading evenly', () {
    // Flutter's default splits the leading a height multiplier adds in
    // proportion to ascent and descent, and Geist's asymmetry then floats
    // text above the centre of its box. Every role, proportional and
    // monospace, opts out (11 section 2.2).
    UiType.standard.allRoles.forEach((String name, TextStyle style) {
      expect(
        style.leadingDistribution,
        TextLeadingDistribution.even,
        reason: '$name does not centre its text in its line box',
      );
    });
  });

  testWidgets('a line box is the scaled font size times the role height', (
    WidgetTester tester,
  ) async {
    final UiType type = UiType.standard;
    late double one;
    late double large;
    await _atScale(
      tester,
      1,
      (BuildContext context) => one = UiType.lineHeightOf(type.body, context),
    );
    await _atScale(
      tester,
      2,
      (BuildContext context) => large = UiType.lineHeightOf(type.body, context),
    );
    expect(one, closeTo(_bodyLineBox, 1e-9));
    expect(large, closeTo(_bodyLineBox * 2, 1e-9));
    expect(UiType.unscaledLineHeightOf(type.body), closeTo(one, 1e-9));
  });

  test('the inset is what reproduces the density height at scale 1.0', () {
    final TextStyle body = UiType.standard.body;
    expect(
      UiType.insetFor(UiDensity.pointer, body),
      closeTo((40 - _bodyLineBox) / 2, 1e-9),
    );
    expect(
      UiType.insetFor(UiDensity.touch, body),
      closeTo((48 - _bodyLineBox) / 2, 1e-9),
    );
    // A role taller than the row sits flush rather than pulling the control
    // shorter than the text in it. `display.large` is 50.4 against a 40 dp
    // pointer row.
    expect(UiType.insetFor(UiDensity.pointer, UiType.standard.displayLarge), 0);
  });

  testWidgets('a control height is the density row until the text passes it', (
    WidgetTester tester,
  ) async {
    final TextStyle body = UiType.standard.body;
    final Map<double, double> measured = <double, double>{};
    for (final double scale in <double>[0.85, 1, 1.3, 2]) {
      await _atScale(
        tester,
        scale,
        (BuildContext context) => measured[scale] = UiType.controlHeightFor(
          UiDensity.pointer,
          body,
          context,
        ),
      );
    }
    final double inset = UiType.insetFor(UiDensity.pointer, body);
    expect(
      measured[0.85],
      40,
      reason: 'below 1.0 the density row wins, so a control never shrinks',
    );
    expect(measured[1], closeTo(40, 1e-9), reason: 'exactly the density row');
    expect(measured[1.3], closeTo(_bodyLineBox * 1.3 + 2 * inset, 1e-9));
    expect(measured[2], closeTo(_bodyLineBox * 2 + 2 * inset, 1e-9));
    expect(measured[2]!, greaterThan(measured[1.3]!));
  });

  test('a strut locks the line box to the role it was built from', () {
    final TextStyle body = UiType.standard.body;
    final StrutStyle strut = UiType.strutOf(body);
    expect(strut.forceStrutHeight, isTrue);
    expect(strut.fontSize, body.fontSize);
    expect(strut.height, body.height);
    expect(strut.leadingDistribution, TextLeadingDistribution.even);
    expect(
      strut.fontFamily,
      body.fontFamily,
      reason: 'the family is already package prefixed and stays that way',
    );
  });

  testWidgets('a mixed line takes its height from the strut, not from its '
      'tallest run', (WidgetTester tester) async {
    final UiType type = UiType.standard;
    Widget line(String key, {StrutStyle? strut}) => Text.rich(
      TextSpan(
        children: <InlineSpan>[
          TextSpan(text: '128', style: type.body),
          TextSpan(text: ' units', style: type.titleLarge),
        ],
      ),
      key: ValueKey<String>(key),
      strutStyle: strut,
    );

    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          width: 400,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(
                '128',
                key: const ValueKey<String>('plain'),
                style: type.body,
              ),
              line('locked', strut: UiType.strutOf(type.body)),
              line('loose'),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    double heightOf(String key) =>
        tester.getSize(find.byKey(ValueKey<String>(key))).height;

    expect(
      heightOf('locked'),
      heightOf('plain'),
      reason:
          'the strut holds the line at the body line box whatever else is '
          'set on it (11 section 2.2)',
    );
    expect(
      heightOf('loose'),
      greaterThan(heightOf('plain')),
      reason:
          'without the strut the tallest run on the line sets its height, '
          'which is what moves a baseline when a value changes',
    );
  });
}
