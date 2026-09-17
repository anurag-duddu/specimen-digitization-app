// `UiProgress` is the one control in the family whose motion survives reduced
// motion, because the motion is the information. These tests hold both halves
// of that: a determinate indicator keeps its catch up, and an indeterminate
// one stops turning and pulses in place instead.
//
// Nothing here calls `pumpAndSettle` on an indeterminate indicator: a
// repeating controller never settles, and a test that waits for one hangs
// until the suite is reaped.

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

/// The filled part of a bar, which is the `FractionallySizedBox`'s own child.
/// The box itself spans the whole track so that its factor is measured
/// against the width the bar was given.
Size _fill(WidgetTester tester) => tester.getSize(
  find.descendant(
    of: find.byType(FractionallySizedBox),
    matching: find.byType(DecoratedBox),
  ),
);

void main() {
  testWidgets('a determinate ring reads its percentage as the value', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiProgress.ring(
          semanticsLabel: 'Upload progress',
          value: 0.45,
        ),
      ),
    );
    await tester.pumpAndSettle();
    final SemanticsData data = tester
        .getSemantics(find.bySemanticsLabel('Upload progress'))
        .getSemanticsData();
    expect(data.label, 'Upload progress');
    expect(data.value, '45 percent');
    handle.dispose();
  });

  testWidgets('an indeterminate indicator has no value to read', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const TickerMode(
          enabled: false,
          child: UiProgress.ring(semanticsLabel: 'Waiting on the server'),
        ),
      ),
    );
    await tester.pump();
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Waiting on the server'))
          .getSemanticsData()
          .value,
      isEmpty,
      reason: 'a spinner that reported a percentage would be inventing one',
    );
    handle.dispose();
  });

  testWidgets('only an indicator that asks for it is a live region', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    for (final bool announce in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(
          child: UiProgress.bar(
            semanticsLabel: 'Upload progress',
            value: 0.5,
            announce: announce,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester
            .getSemantics(find.bySemanticsLabel('Upload progress'))
            .getSemanticsData()
            .flagsCollection
            .isLiveRegion,
        announce,
      );
    }
    handle.dispose();
  });

  testWidgets('the three ring sizes are the three 10 section 4.5 names', (
    WidgetTester tester,
  ) async {
    expect(
      UiProgressSize.values.map((UiProgressSize s) => s.diameter),
      <double>[16, 24, 40],
    );
    for (final UiProgressSize size in UiProgressSize.values) {
      await tester.pumpWidget(
        uiHarness(
          child: UiProgress.ring(
            semanticsLabel: 'Upload progress',
            value: 0.5,
            size: size,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.getSize(find.byType(CustomPaint).first),
        Size.square(size.diameter),
      );
    }
  });

  testWidgets('the bar is 4 dp and takes the width it is given', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 320,
          child: UiProgress.bar(semanticsLabel: 'Upload progress', value: 0.5),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final UiThemeData ui = UiThemeData.light();
    expect(
      tester.getSize(find.byType(UiProgress)),
      Size(320, UiProgressStyle.resolve(ui).barThickness),
    );
    expect(UiProgressStyle.resolve(ui).barThickness, ui.space.s1);
  });

  testWidgets('a value below the highest one seen is held at the highest', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    Future<void> report(double value) async {
      await tester.pumpWidget(
        uiHarness(
          child: UiProgress.bar(
            semanticsLabel: 'Upload progress',
            value: value,
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    String spoken() => tester
        .getSemantics(find.bySemanticsLabel('Upload progress'))
        .getSemanticsData()
        .value;

    await report(0.74);
    expect(spoken(), '74 percent');
    await report(0.20);
    expect(
      spoken(),
      '74 percent',
      reason:
          'a resumed upload reporting a lower server offset must not run the '
          'bar backwards (04 section 5.5)',
    );
    await report(0.80);
    expect(spoken(), '80 percent');
    handle.dispose();
  });

  testWidgets('a value outside 0 to 1 is clamped rather than drawn', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(
        child: const UiProgress.bar(
          semanticsLabel: 'Upload progress',
          value: 1.4,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Upload progress'))
          .getSemanticsData()
          .value,
      '100 percent',
    );
    handle.dispose();
  });

  testWidgets('a run opened half finished is drawn half finished', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const SizedBox(
          width: 400,
          child: UiProgress.bar(semanticsLabel: 'Upload progress', value: 0.5),
        ),
      ),
    );
    // One frame, with nothing pumped past it. A fill animation would still be
    // near zero here, and replaying history as if it were happening now is a
    // lie about when it happened (04 section 5.5).
    await tester.pump();
    expect(_fill(tester).width, closeTo(200, 0.5));
    await tester.pumpAndSettle();
  });

  testWidgets('a determinate indicator keeps its catch up under reduced '
      'motion, because the motion is the number', (WidgetTester tester) async {
    for (final bool reduced in <bool>[false, true]) {
      // A distinct key per pass, because the indicator is monotonic: without
      // one the second pass would reuse the first pass's state and hold at
      // the value it had already reached. This is the escape hatch the class
      // names, and a retry that starts again uses it the same way.
      await tester.pumpWidget(
        uiHarness(
          disableAnimations: reduced,
          child: SizedBox(
            width: 400,
            child: UiProgress.bar(
              key: ValueKey<bool>(reduced),
              semanticsLabel: 'Upload progress',
              value: 0.2,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.pumpWidget(
        uiHarness(
          disableAnimations: reduced,
          child: SizedBox(
            width: 400,
            child: UiProgress.bar(
              key: ValueKey<bool>(reduced),
              semanticsLabel: 'Upload progress',
              value: 1,
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(
        _fill(tester).width,
        lessThan(400),
        reason:
            'the bar is still catching up half way through, whether or not '
            'motion is reduced (04 sections 1.5 and 2.5)',
      );
      await tester.pumpAndSettle();
      expect(_fill(tester).width, 400);
    }
  });

  testWidgets('a determinate indicator holds no ticker of its own', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const UiProgress.ring(
          semanticsLabel: 'Upload progress',
          value: 0.5,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.binding.transientCallbackCount, 0);
  });

  test('the cycle turns, and pulses in place instead under reduced motion', () {
    const double floor = 0.08;
    const List<double> samples = <double>[0, 0.25, 0.5, 0.75];
    final List<UiProgressPhase> turning = <UiProgressPhase>[
      for (final double t in samples)
        UiProgressPhase.at(t, reduced: false, pulseFloor: floor),
    ];
    expect(
      turning.map((UiProgressPhase p) => p.turn),
      samples,
      reason: 'it turns once per cycle',
    );
    expect(
      turning.every((UiProgressPhase p) => p.opacity == 1),
      isTrue,
      reason: 'a turning indicator does not also fade',
    );

    final List<UiProgressPhase> pulsing = <UiProgressPhase>[
      for (final double t in samples)
        UiProgressPhase.at(t, reduced: true, pulseFloor: floor),
    ];
    expect(
      pulsing.every((UiProgressPhase p) => p.turn == 0),
      isTrue,
      reason: 'under reduced motion the arc holds still',
    );
    expect(pulsing[0].opacity, closeTo(floor, 0.0001));
    expect(pulsing[1].opacity, closeTo(floor + (1 - floor) * 0.5, 0.0001));
    expect(pulsing[2].opacity, 1, reason: 'the pulse peaks mid cycle');
    expect(
      pulsing[3].opacity,
      closeTo(pulsing[1].opacity, 0.0001),
      reason: 'a triangle wave, so it fades back rather than snapping',
    );
  });

  testWidgets('an indeterminate indicator keeps a ticker in both motion '
      'modes, because the movement is essential', (WidgetTester tester) async {
    for (final bool reduced in <bool>[false, true]) {
      await tester.pumpWidget(
        uiHarness(
          disableAnimations: reduced,
          child: const UiProgress.ring(semanticsLabel: 'Waiting on the server'),
        ),
      );
      await tester.pump();
      expect(
        tester.binding.transientCallbackCount,
        greaterThan(0),
        reason:
            'a spinner saying the server has not answered is essential '
            'movement (04 section 2.5); under reduced motion it runs as a '
            'pulse rather than as a turn',
      );
      // The painter is rebuilt frame by frame, so something visibly changes
      // over a quarter of a cycle in both modes.
      final CustomPainter first = _painterOf(tester);
      await tester.pump(
        UiProgressStyle.resolve(UiThemeData.light()).cycle ~/ 4,
      );
      expect(_painterOf(tester).shouldRepaint(first), isTrue);
      await tester.pumpWidget(uiHarness(child: const SizedBox.shrink()));
    }
  });

  testWidgets('an indeterminate arc never closes the circle', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const TickerMode(
          enabled: false,
          child: UiProgress.ring(semanticsLabel: 'Waiting on the server'),
        ),
      ),
    );
    await tester.pump();
    expect(
      UiProgressStyle.indeterminateSweep,
      lessThan(6.283),
      reason:
          'a closed arc reads as a determinate ring at 100 percent, which is '
          'the one thing an indeterminate indicator must not say',
    );
  });

  testWidgets('a ring inside a filled control takes that control foreground', (
    WidgetTester tester,
  ) async {
    final UiThemeData ui = UiThemeData.light();
    expect(UiProgressStyle.resolve(ui).arc, ui.color.ink);
    expect(
      UiProgressStyle.resolve(ui, color: ui.color.paper).arc,
      ui.color.paper,
    );
    expect(UiProgressStyle.resolve(ui).track, ui.color.hairline);
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: const SizedBox(
          width: 320,
          child: UiProgress.bar(semanticsLabel: 'Upload progress', value: 0.25),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    final Rect bar = tester.getRect(find.byType(UiProgress));
    final Rect fill = tester.getRect(
      find.descendant(
        of: find.byType(FractionallySizedBox),
        matching: find.byType(DecoratedBox),
      ),
    );
    expect(
      fill.right,
      closeTo(bar.right, 0.5),
      reason: 'the bar fills from the edge the reviewer reads from',
    );
  });
}

/// The ring's painter. Private to `progress.dart`, so a test reads it as an
/// opaque object and asks it the one question it answers publicly: whether it
/// would paint something different from the one before it.
CustomPainter _painterOf(WidgetTester tester) => tester
    .widget<CustomPaint>(
      find.descendant(
        of: find.byType(UiProgress),
        matching: find.byType(CustomPaint),
      ),
    )
    .painter!;
