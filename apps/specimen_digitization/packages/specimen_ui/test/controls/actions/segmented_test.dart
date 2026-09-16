// `UiSegmented` carries signature motion 1, the glide, and the WAI-ARIA
// manual activation pattern: arrows move, Enter selects, and arrowing past a
// segment does not switch the pane under the reviewer on the way through.

import 'dart:ui' show SemanticsFlags, Tristate;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

enum _Pane { readings, fields, history }

const List<UiSegment<_Pane>> _segments = <UiSegment<_Pane>>[
  UiSegment<_Pane>(value: _Pane.readings, label: 'Readings'),
  UiSegment<_Pane>(value: _Pane.fields, label: 'Fields'),
  UiSegment<_Pane>(value: _Pane.history, label: 'History'),
];

/// A track whose value lives in the test, so the thumb really moves.
class _Host extends StatefulWidget {
  const _Host({this.initial = _Pane.readings, this.onChanged});

  final _Pane initial;
  final ValueChanged<_Pane>? onChanged;

  @override
  State<_Host> createState() => _HostState();
}

class _HostState extends State<_Host> {
  late _Pane _value = widget.initial;

  @override
  Widget build(BuildContext context) => UiSegmented<_Pane>(
    segments: _segments,
    value: _value,
    onChanged: (_Pane next) {
      setState(() => _value = next);
      widget.onChanged?.call(next);
    },
  );
}

/// Where the gliding thumb is now.
double _thumbCentre(WidgetTester tester) =>
    tester.getCenter(find.byType(FractionallySizedBox)).dx;

void main() {
  setUp(() {
    FocusManager.instance.highlightStrategy =
        FocusHighlightStrategy.alwaysTraditional;
  });
  tearDown(() {
    FocusManager.instance.highlightStrategy = FocusHighlightStrategy.automatic;
  });

  testWidgets('a segment satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiSegmented<_Pane>(
        segments: _segments,
        value: _Pane.readings,
        onChanged: (_Pane next) {},
      ),
      semanticsLabel: 'Fields',
      hasRole: (SemanticsFlags flags) => flags.isSelected != Tristate.none,
    );
  });

  testWidgets('a disabled track satisfies the contract and states the reason',
      (WidgetTester tester) async {
    await expectControlContract(
      tester,
      (BuildContext context) => const UiSegmented<_Pane>(
        segments: _segments,
        value: _Pane.readings,
        onChanged: null,
        disabledReason: 'This run produced one pane of evidence.',
      ),
      semanticsLabel: 'Fields',
      disabledWithReason: true,
    );
  });

  testWidgets('each segment is a tab, and only the chosen one is selected', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: const _Host(initial: _Pane.fields)));
    await tester.pumpAndSettle();
    final SemanticsData chosen = tester
        .getSemantics(find.bySemanticsLabel('Fields'))
        .getSemanticsData();
    expect(chosen.role, SemanticsRole.tab);
    expect(chosen.flagsCollection.isSelected, Tristate.isTrue);
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('History'))
          .getSemanticsData()
          .flagsCollection
          .isSelected,
      Tristate.isFalse,
    );
    handle.dispose();
  });

  testWidgets('the segments are equal and each clears the hit box', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: const _Host()));
    await tester.pumpAndSettle();
    final List<Size> sizes = <Size>[
      for (final UiSegment<_Pane> segment in _segments)
        tester.getSize(find.bySemanticsLabel(segment.label)),
    ];
    for (final Size size in sizes) {
      expect(size.width, closeTo(sizes.first.width, 0.5));
      expect(size.width, greaterThanOrEqualTo(UiDensity.hitBox));
      expect(size.height, greaterThanOrEqualTo(UiDensity.hitBox));
    }
  });

  testWidgets('the track draws at the density height inside a 48 dp row', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(density: density, child: const _Host()),
      );
      await tester.pumpAndSettle();
      final UiSegmentedStyle style = UiSegmentedStyle.resolve(
        UiThemeData.light(density: UiDensity.of(density)),
        UiSize.md,
      );
      expect(style.trackHeight, UiDensity.of(density).controlHeight);
      expect(style.outerHeight, greaterThanOrEqualTo(UiDensity.hitBox));
      expect(
        tester.getSize(find.byType(UiSegmented<_Pane>)).height,
        style.outerHeight,
      );
    }
  });

  testWidgets('tapping a segment chooses it and the thumb glides there', (
    WidgetTester tester,
  ) async {
    final List<_Pane> reported = <_Pane>[];
    await tester.pumpWidget(uiHarness(child: _Host(onChanged: reported.add)));
    await tester.pumpAndSettle();
    final double start = _thumbCentre(tester);

    await tester.tap(find.bySemanticsLabel('History'));
    await tester.pump();
    expect(reported, <_Pane>[_Pane.history]);
    final double midway = _thumbCentre(tester);
    expect(
      midway,
      closeTo(start, 1),
      reason: 'the glide has not started travelling on the first frame',
    );

    await tester.pump(MotionTokens.mediumRaw ~/ 2);
    expect(
      _thumbCentre(tester),
      greaterThan(start),
      reason: 'the thumb is between the two segments partway through',
    );

    await tester.pumpAndSettle();
    expect(
      _thumbCentre(tester),
      closeTo(tester.getCenter(find.bySemanticsLabel('History')).dx, 2),
    );
  });

  testWidgets('under reduced motion the thumb appears at the new segment', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: const _Host()),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('History'));
    await tester.pump();
    expect(
      _thumbCentre(tester),
      closeTo(tester.getCenter(find.bySemanticsLabel('History')).dx, 2),
    );
    expect(tester.binding.transientCallbackCount, 0);
  });

  testWidgets('arrows move focus without choosing, and Enter chooses', (
    WidgetTester tester,
  ) async {
    final List<_Pane> reported = <_Pane>[];
    await tester.pumpWidget(uiHarness(child: _Host(onChanged: reported.add)));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'Readings');

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
    await tester.pumpAndSettle();
    expect(FocusManager.instance.primaryFocus?.debugLabel, 'History');
    expect(
      reported,
      isEmpty,
      reason:
          'manual activation: arrowing past a segment must not switch the '
          'pane under the reviewer',
    );

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(reported, <_Pane>[_Pane.history]);
  });

  testWidgets('the thumb starts at the reading start under RTL', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(textDirection: TextDirection.rtl, child: const _Host()),
    );
    await tester.pumpAndSettle();
    expect(
      _thumbCentre(tester),
      closeTo(tester.getCenter(find.bySemanticsLabel('Readings')).dx, 2),
    );
    expect(
      tester.getCenter(find.bySemanticsLabel('Readings')).dx,
      greaterThan(tester.getCenter(find.bySemanticsLabel('History')).dx),
    );
  });

  testWidgets('a disabled track chooses nothing', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        child: const UiSegmented<_Pane>(
          segments: _segments,
          value: _Pane.readings,
          onChanged: null,
          disabledReason: 'This run produced one pane of evidence.',
        ),
      ),
    );
    await tester.tap(find.bySemanticsLabel('History'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('it builds at 200 percent text', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        size: const Size(600, 600),
        child: const _Host(),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('a track outside two to five segments is a defect', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: UiSegmented<_Pane>(
          segments: _segments.take(1).toList(growable: false),
          value: _Pane.readings,
          onChanged: (_Pane next) {},
        ),
      ),
    );
    expect(tester.takeException(), isAssertionError);
  });
}
