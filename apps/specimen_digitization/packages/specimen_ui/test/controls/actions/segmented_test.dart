// Value choices use radio semantics and manual keyboard activation.
// Arrows move focus; Enter commits without changing neighboring geometry.

import 'dart:math' as math;
import 'dart:ui' show CheckedState, SemanticsFlags, Tristate;

import 'package:flutter/rendering.dart';
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

/// The same three panes, each with a glyph and under a name, so the whole
/// ladder of 11 section 3.3 is available to the track.
///
/// Measured at scale 1.0 in Geist: the words need about 251 dp, the glyphs
/// about 152, and the select needs only its hit box. The widths the tests
/// below pump at sit well inside those bands.
const List<UiSegment<_Pane>> _glyphSegments = <UiSegment<_Pane>>[
  UiSegment<_Pane>(
    value: _Pane.readings,
    label: 'Readings',
    icon: UiIcons.modelReading,
  ),
  UiSegment<_Pane>(value: _Pane.fields, label: 'Fields', icon: UiIcons.record),
  UiSegment<_Pane>(
    value: _Pane.history,
    label: 'History',
    icon: UiIcons.history,
  ),
];

/// A named track of glyph segments in a column exactly [width] wide, whose
/// value lives in the test so that collapsing it can be told from choosing.
class _PaneHost extends StatefulWidget {
  const _PaneHost({required this.width, required this.changes});

  final double width;
  final List<_Pane> changes;

  @override
  State<_PaneHost> createState() => _PaneHostState();
}

class _PaneHostState extends State<_PaneHost> {
  _Pane _value = _Pane.fields;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: widget.width,
    child: UiSegmented<_Pane>(
      label: 'Pane',
      segments: _glyphSegments,
      value: _value,
      onChanged: (_Pane next) {
        widget.changes.add(next);
        setState(() => _value = next);
      },
    ),
  );
}

/// Clause 15 for a track with no [UiSegmented.label]. The select variant is
/// not available to it, so its segments survive every width and the words in
/// them are ellipsised rather than dropped.
Future<void> _everySegmentStillReads(WidgetTester tester, double width) async {
  for (final UiSegment<_Pane> segment in _segments) {
    expect(
      find.text(segment.label),
      findsOneWidget,
      reason: '${segment.label} at $width dp',
    );
  }
}

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

/// The selected slot's painted fill, independent of semantic state.
Color _segmentFill(WidgetTester tester, String label) => tester
    .widget<ColoredBox>(
      find
          .descendant(
            of: find.byWidgetPredicate(
              (Widget widget) =>
                  widget is Pressable && widget.semanticsLabel == label,
            ),
            matching: find.byType(ColoredBox),
          )
          .first,
    )
    .color;

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
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _everySegmentStillReads),
    );
  });

  testWidgets('a disabled track satisfies the contract and states the reason', (
    WidgetTester tester,
  ) async {
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
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: const FitExpectation(check: _everySegmentStillReads),
    );
  });

  testWidgets('each segment is a radio choice with one checked option', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(child: const _Host(initial: _Pane.fields)),
    );
    await tester.pumpAndSettle();
    final SemanticsData chosen = tester
        .getSemantics(find.bySemanticsLabel('Fields'))
        .getSemanticsData();
    expect(chosen.role, SemanticsRole.none);
    expect(chosen.flagsCollection.isInMutuallyExclusiveGroup, isTrue);
    expect(chosen.flagsCollection.isChecked, CheckedState.isTrue);
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

  testWidgets('the track keeps every choice at least 48 dp high', (
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
      expect(
        style.trackHeight,
        math.max(UiDensity.hitBox, UiDensity.of(density).controlHeight),
      );
      expect(style.outerHeight, greaterThanOrEqualTo(UiDensity.hitBox));
      expect(
        tester.getSize(find.byType(UiSegmented<_Pane>)).height,
        style.outerHeight,
      );
    }
  });

  testWidgets('tapping a choice updates its fill without moving the slots', (
    WidgetTester tester,
  ) async {
    final List<_Pane> reported = <_Pane>[];
    await tester.pumpWidget(uiHarness(child: _Host(onChanged: reported.add)));
    await tester.pumpAndSettle();
    final Rect readings = tester.getRect(find.bySemanticsLabel('Readings'));
    final Rect history = tester.getRect(find.bySemanticsLabel('History'));
    final UiThemeData ui = tester.element(find.byType(_Host)).ui;
    expect(_segmentFill(tester, 'Readings'), ui.color.ink);
    expect(_segmentFill(tester, 'History'), ui.color.paper);

    await tester.tap(find.bySemanticsLabel('History'));
    await tester.pumpAndSettle();
    expect(reported, <_Pane>[_Pane.history]);
    expect(_segmentFill(tester, 'Readings'), ui.color.paper);
    expect(_segmentFill(tester, 'History'), ui.color.ink);
    expect(tester.getRect(find.bySemanticsLabel('Readings')), readings);
    expect(tester.getRect(find.bySemanticsLabel('History')), history);
  });

  testWidgets('reduced motion commits a choice with no animation', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: const _Host()),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('History'));
    await tester.pump();
    final UiThemeData ui = tester.element(find.byType(_Host)).ui;
    expect(_segmentFill(tester, 'History'), ui.color.ink);
    expect(_segmentFill(tester, 'Readings'), ui.color.paper);
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

  testWidgets('the selected choice stays at the reading start under RTL', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(textDirection: TextDirection.rtl, child: const _Host()),
    );
    await tester.pumpAndSettle();
    expect(
      _segmentFill(tester, 'Readings'),
      tester.element(find.byType(_Host)).ui.color.ink,
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

  testWidgets('the track is its widest label times the count, plus its '
      'insets', (WidgetTester tester) async {
    late double declared;
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) {
            final UiSegmentedStyle style = UiSegmentedStyle.resolve(
              context.ui,
              UiSize.md,
              textScaler: MediaQuery.textScalerOf(context),
            );
            final double widest = _segments.fold<double>(
              0,
              (double so, UiSegment<_Pane> segment) => math.max(
                so,
                measureLabel(context, segment.label, style.labelStyle).width,
              ),
            );
            declared =
                _segments.length *
                    math.max(
                      style.minSegmentWidth,
                      widest + style.segmentPadding.horizontal,
                    ) +
                2 * style.inset;
            return const _Host();
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.byType(UiSegmented<_Pane>)).width,
      closeTo(declared, 0.5),
      reason:
          'the intrinsic width of 11 section 3.3 is measured, so every '
          'segment is the widest label wide and the thumb steps evenly',
    );
  });

  testWidgets('given less room than its words need, the segments become '
      'glyphs with a tooltip each', (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(child: const _PaneHost(width: 200, changes: <_Pane>[])),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      find.text('Readings'),
      findsNothing,
      reason: 'the words are what gave way, not the track',
    );
    expect(
      find.byType(UiIcon),
      findsNWidgets(_glyphSegments.length),
      reason: 'every segment draws the glyph it carries',
    );
    expect(
      find.byType(UiTooltip),
      findsNWidgets(_glyphSegments.length),
      reason: 'a glyph on its own says nothing, so each one names itself',
    );
    for (final UiSegment<_Pane> segment in _glyphSegments) {
      expect(
        find.bySemanticsLabel(segment.label),
        findsOneWidget,
        reason: 'a screen reader still hears ${segment.label}',
      );
    }
    handle.dispose();
  });

  testWidgets('given less room still, a named track becomes a select over '
      'the same options', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(child: const _PaneHost(width: 100, changes: <_Pane>[])),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    final UiSelect<_Pane> select = tester.widget<UiSelect<_Pane>>(
      find.byType(UiSelect<_Pane>),
    );
    expect(
      select.options.map((UiSelectOption<_Pane> o) => o.value).toList(),
      _glyphSegments.map((UiSegment<_Pane> s) => s.value).toList(),
      reason: 'the same options, in the same order',
    );
    expect(
      select.options.map((UiSelectOption<_Pane> o) => o.label).toList(),
      _glyphSegments.map((UiSegment<_Pane> s) => s.label).toList(),
    );
    expect(select.label, 'Pane');
    expect(
      select.showLabel,
      isFalse,
      reason:
          'the collapse changes a shape on the screen; it does not add a '
          'word to it',
    );
  });

  testWidgets('collapsing the track changes its form and not its value', (
    WidgetTester tester,
  ) async {
    final List<_Pane> changes = <_Pane>[];
    await tester.pumpWidget(
      uiHarness(child: _PaneHost(width: 300, changes: changes)),
    );
    await tester.pumpAndSettle();
    expect(find.text('Readings'), findsOneWidget, reason: 'words at 300 dp');

    await tester.pumpWidget(
      uiHarness(child: _PaneHost(width: 100, changes: changes)),
    );
    await tester.pumpAndSettle();
    expect(
      tester.widget<UiSelect<_Pane>>(find.byType(UiSelect<_Pane>)).value,
      _Pane.fields,
      reason: 'the chosen pane is the one the segments had',
    );
    expect(
      changes,
      isEmpty,
      reason:
          'nothing was chosen. A narrower window is a change of form, and a '
          'control that reported one would be a screen re-deciding for the '
          'reviewer',
    );
  });

  testWidgets('choosing in the select reports what the segment would have', (
    WidgetTester tester,
  ) async {
    final List<_Pane> changes = <_Pane>[];
    await tester.pumpWidget(
      uiHarness(child: _PaneHost(width: 100, changes: changes)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byType(UiSelect<_Pane>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('History').last);
    await tester.pumpAndSettle();
    expect(changes, <_Pane>[_Pane.history]);
  });

  testWidgets('a track with no name keeps its segments and cuts the words '
      'short', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(child: const SizedBox(width: 100, child: _Host())),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(
      find.byType(UiSelect<_Pane>),
      findsNothing,
      reason:
          'a select needs a name to offer its options under, and a tab strip '
          'has none to give',
    );
    expect(
      tester
          .renderObjectList<RenderParagraph>(find.byType(RichText))
          .every((RenderParagraph p) => p.didExceedMaxLines),
      isTrue,
      reason: 'the last resort is an ellipsis in each segment, never a wrap',
    );
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
