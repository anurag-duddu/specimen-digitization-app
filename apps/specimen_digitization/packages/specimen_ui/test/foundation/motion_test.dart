// Motion tokens pinned to the Material token database.
//
// `foundation/motion.dart` may not import `material.dart` (10 section 8, gate
// `layering`), and `Durations` and `Easing` are declared there, so the values
// are written out in the token file. This test does import Material, and
// asserts every one of them still equals the constant 04 section 2.2 names.
// The pin is a test rather than a reference: it fails loudly if the token
// database moves, which is the failure mode that reference was protecting
// against.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

void main() {
  test('every duration equals its Material token', () {
    expect(MotionTokens.instantRaw, Duration.zero);
    expect(MotionTokens.quickRaw, Durations.short2);
    expect(MotionTokens.shortRaw, Durations.short3);
    expect(MotionTokens.standardRaw, Durations.short4);
    expect(MotionTokens.mediumRaw, Durations.medium1);
    expect(MotionTokens.emphasizedRaw, Durations.medium3);
    expect(MotionTokens.slowRaw, Durations.long2);
  });

  test('every curve equals its Material token', () {
    expect(MotionTokens.standardCurve, Easing.standard);
    expect(MotionTokens.enterCurve, Easing.standardDecelerate);
    expect(MotionTokens.exitCurve, Easing.standardAccelerate);
    expect(MotionTokens.emphasizedEnterCurve, Easing.emphasizedDecelerate);
    expect(MotionTokens.emphasizedExitCurve, Easing.emphasizedAccelerate);
    expect(MotionTokens.progressCurve, Curves.linear);
    // There is no `Easing.emphasized`: the full emphasized curve is a
    // `ThreePointCubic` and exists only on `Curves` (04 section 2.3).
    expect(MotionTokens.emphasizedCurve, Curves.easeInOutCubicEmphasized);
    expect(MotionTokens.emphasizedCurve, isA<ThreePointCubic>());
  });

  test('the three signature motions carry the durations 09 gives them', () {
    const MotionTokens motion = MotionTokens();
    expect(motion.navigationGlide, Durations.medium1);
    expect(motion.capsuleFill, Durations.short3);
    expect(motion.numeralTick, Durations.short3);
    expect(MotionTokens.numeralTickRise, 6);
    expect(MotionTokens.capsuleCheckDelayFraction, 0.4);
  });

  test('reduced motion collapses a decorative duration to zero', () {
    const MotionTokens normal = MotionTokens();
    const MotionTokens reduced = MotionTokens(reduced: true);
    expect(normal.standard, MotionTokens.standardRaw);
    expect(reduced.standard, Duration.zero);
    expect(reduced.emphasized, Duration.zero);
    expect(reduced.navigationGlide, Duration.zero);
    expect(reduced.capsuleFill, Duration.zero);
  });

  test('motion that carries information keeps its duration', () {
    const MotionTokens reduced = MotionTokens(reduced: true);
    expect(
      reduced.meaningful(MotionTokens.standardRaw),
      MotionTokens.standardRaw,
      reason:
          'a determinate progress bar is the rendering of a number; removing '
          'its motion removes data (04 section 1.5)',
    );
  });

  test('the state layer durations are the ones the contract names', () {
    const MotionTokens motion = MotionTokens();
    expect(motion.pressIn, const Duration(milliseconds: 60));
    expect(motion.pressOut, const Duration(milliseconds: 120));
  });

  testWidgets('the in-app preference forces reduced motion', (
    WidgetTester tester,
  ) async {
    final MotionPreferenceController controller = MotionPreferenceController(
      store: MemoryMotionPreferenceStore(true),
    );
    addTearDown(controller.dispose);
    await controller.load();

    late MotionTokens seen;
    await tester.pumpWidget(
      MotionScope(
        controller: controller,
        child: Directionality(
          textDirection: TextDirection.ltr,
          child: MediaQuery(
            data: const MediaQueryData(),
            child: Builder(
              builder: (BuildContext context) {
                seen = MotionTokens.of(context);
                return const SizedBox.shrink();
              },
            ),
          ),
        ),
      ),
    );
    expect(seen.reduced, isTrue);
    expect(seen.standard, Duration.zero);
  });

  testWidgets('the platform flag forces reduced motion', (
    WidgetTester tester,
  ) async {
    late MotionTokens seen;
    await tester.pumpWidget(
      Directionality(
        textDirection: TextDirection.ltr,
        child: MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: Builder(
            builder: (BuildContext context) {
              seen = MotionTokens.of(context);
              return const SizedBox.shrink();
            },
          ),
        ),
      ),
    );
    expect(seen.reduced, isTrue);
  });
}
