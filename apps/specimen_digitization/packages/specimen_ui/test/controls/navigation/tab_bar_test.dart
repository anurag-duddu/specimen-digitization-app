// The brand bottom tab bar (10 section 4.4, `UiTabBar`).
//
// The bar is one component on every platform, so nothing in this file names a
// platform: the only thing that varies is the system inset under it, and that
// is a `MediaQuery` the test sets.

import 'dart:math' as math;
import 'dart:ui' show Tristate;

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';
import 'destinations.dart';

/// A bar whose selection is real, inside the system inset and pixel density a
/// test asks for, so a tap and a key press change the control rather than
/// only calling back.
class _BarHost extends StatefulWidget {
  const _BarHost({
    required this.destinations,
    this.onSelect,
    this.inset = 0,
    this.devicePixelRatio = 1,
    this.initial = 0,
  });

  final List<UiNavDestination> destinations;
  final ValueChanged<int>? onSelect;
  final double inset;
  final double devicePixelRatio;
  final int initial;

  @override
  State<_BarHost> createState() => _BarHostState();
}

class _BarHostState extends State<_BarHost> {
  late int _current = widget.initial;

  /// Chooses a destination without a pointer, for a bar narrow enough that
  /// the destination it is choosing is off screen.
  void choose(int index) => setState(() => _current = index);

  @override
  Widget build(BuildContext context) => MediaQuery(
    data: MediaQuery.of(context).copyWith(
      viewPadding: EdgeInsets.only(bottom: widget.inset),
      devicePixelRatio: widget.devicePixelRatio,
    ),
    child: UiTabBar(
      destinations: widget.destinations,
      currentIndex: _current,
      iconKeyOf: (int index) =>
          ValueKey<String>('icon-${widget.destinations[index].label}'),
      onSelect: (int index) {
        widget.onSelect?.call(index);
        setState(() => _current = index);
      },
    ),
  );
}

/// How opaque each layer of a destination's glyph is drawn right now.
///
/// The glyph is two layers, the `regular` form and the `fill` form, and each
/// is wrapped in the `AnimatedOpacity` that cross-fades it. The animated value
/// lives on the `FadeTransition` it builds, not on the widget, which only
/// holds the target.
({double regular, double fill}) _glyphOpacity(
  WidgetTester tester,
  UiNavDestination destination,
) {
  final Finder layers = find.descendant(
    of: find.byKey(ValueKey<String>('icon-${destination.label}')),
    matching: find.byType(FadeTransition),
  );
  expect(layers, findsNWidgets(2));
  double opacityOf(Finder layer) =>
      tester.widget<FadeTransition>(layer).opacity.value;
  return (regular: opacityOf(layers.at(0)), fill: opacityOf(layers.at(1)));
}

/// The one rendered size of the bar, which is what the shell lays out.
Size _barSize(WidgetTester tester) => tester.getSize(find.byType(UiTabBar));

/// The colour a destination's label is painted in right now.
Color? _labelColour(WidgetTester tester, String label) {
  final RenderParagraph paragraph = tester.renderObject<RenderParagraph>(
    find.descendant(of: find.byType(UiTabBar), matching: find.text(label)),
  );
  return paragraph.text.style?.color;
}

Future<void> _pumpBar(
  WidgetTester tester, {
  List<UiNavDestination> destinations = twoDestinations,
  ValueChanged<int>? onSelect,
  double inset = 0,
  double devicePixelRatio = 1,
  TextScaler textScaler = TextScaler.noScaling,
  Brightness brightness = Brightness.light,
  UiDensityMode density = UiDensityMode.touch,
  bool disableAnimations = false,
  TextDirection textDirection = TextDirection.ltr,
  Size size = const Size(390, 844),
  int initial = 0,
}) async {
  // The harness publishes `size` to `MediaQuery` but lays out in the test
  // view, which is 800 by 600 unless it is told otherwise.
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = size;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    uiHarness(
      size: size,
      textScaler: textScaler,
      brightness: brightness,
      density: density,
      disableAnimations: disableAnimations,
      textDirection: textDirection,
      child: _BarHost(
        destinations: destinations,
        onSelect: onSelect,
        inset: inset,
        devicePixelRatio: devicePixelRatio,
        initial: initial,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('selection', () {
    testWidgets('a pointer selects the destination it lands on', (
      WidgetTester tester,
    ) async {
      final List<int> selected = <int>[];
      await _pumpBar(
        tester,
        destinations: threeDestinations,
        onSelect: selected.add,
      );

      await tester.tap(find.bySemanticsLabel('Sources'));
      await tester.pumpAndSettle();
      expect(selected, <int>[2]);

      await tester.tap(find.bySemanticsLabel('Intake'));
      await tester.pumpAndSettle();
      expect(selected, <int>[2, 1]);
    });

    testWidgets('pressing the current destination still reports it', (
      WidgetTester tester,
    ) async {
      final List<int> selected = <int>[];
      await _pumpBar(tester, onSelect: selected.add);
      await tester.tap(find.bySemanticsLabel('Queue'));
      await tester.pumpAndSettle();
      expect(selected, <int>[0], reason: 'what it does is the screen\'s call');
    });

    testWidgets('the label draws, and a tap on the label selects too', (
      WidgetTester tester,
    ) async {
      final List<int> selected = <int>[];
      await _pumpBar(tester, onSelect: selected.add);
      expect(find.text('Queue'), findsOneWidget, reason: 'labels are drawn');
      expect(find.text('Intake'), findsOneWidget);
      await tester.tap(find.text('Intake'));
      await tester.pumpAndSettle();
      expect(selected, <int>[1]);
    });

    testWidgets('a destination count outside two to five is an error', (
      WidgetTester tester,
    ) async {
      await _pumpBar(tester, destinations: fiveDestinations);
      expect(tester.takeException(), isNull);
      expect(find.byType(UiTabBar), findsOneWidget);

      await tester.pumpWidget(
        uiHarness(
          child: UiTabBar(
            destinations: const <UiNavDestination>[
              UiNavDestination(label: 'Queue', icon: UiIcons.queue),
            ],
            currentIndex: 0,
            onSelect: (int _) {},
          ),
        ),
      );
      expect(tester.takeException(), isAssertionError);
    });
  });

  group('semantics', () {
    testWidgets('every cell is a labelled tab and exactly one is selected', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await _pumpBar(tester, destinations: threeDestinations, initial: 1);

      for (final MapEntry<int, UiNavDestination> entry
          in threeDestinations.asMap().entries) {
        final SemanticsData data = tester
            .getSemantics(find.bySemanticsLabel(entry.value.label))
            .getSemanticsData();
        expect(data.label, entry.value.label);
        expect(
          data.role,
          SemanticsRole.tab,
          reason: '${entry.value.label} is not a tab',
        );
        expect(
          data.flagsCollection.isSelected,
          entry.key == 1 ? Tristate.isTrue : Tristate.isFalse,
          reason: '${entry.value.label} selected state',
        );
        expect(
          data.hasAction(SemanticsAction.tap),
          isTrue,
          reason: '${entry.value.label} cannot be activated by a screen reader',
        );
      }
      handle.dispose();
    });

    testWidgets('the tabs sit inside one tab list, and nothing else does', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await _pumpBar(tester, destinations: threeDestinations);

      final Finder list = find.byWidgetPredicate(
        (Widget widget) =>
            widget is Semantics &&
            widget.properties.role == SemanticsRole.tabBar,
      );
      expect(list, findsOneWidget);
      final SemanticsNode node = tester.getSemantics(list);
      final List<SemanticsNode> children = <SemanticsNode>[];
      node.visitChildren((SemanticsNode child) {
        children.add(child);
        return true;
      });
      expect(children, hasLength(threeDestinations.length));
      expect(
        children.map((SemanticsNode child) => child.getSemanticsData().role),
        everyElement(SemanticsRole.tab),
        reason: 'a tab list may only hold tabs (10 section 2 clause 5)',
      );
      handle.dispose();
    });

    testWidgets('the label is read once, as the tab, not again as text', (
      WidgetTester tester,
    ) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await _pumpBar(tester);
      expect(find.bySemanticsLabel('Queue'), findsOneWidget);
      expect(find.bySemanticsLabel('Intake'), findsOneWidget);
      handle.dispose();
    });
  });

  group('geometry', () {
    testWidgets('every cell is at least 48 by 48 and is all hit box', (
      WidgetTester tester,
    ) async {
      for (final UiDensityMode density in UiDensityMode.values) {
        for (final double scale in <double>[1, 1.3, 2]) {
          for (final List<UiNavDestination> destinations
              in <List<UiNavDestination>>[
                twoDestinations,
                threeDestinations,
                fiveDestinations,
              ]) {
            await _pumpBar(
              tester,
              destinations: destinations,
              density: density,
              textScaler: TextScaler.linear(scale),
              inset: 34,
            );
            for (final UiNavDestination destination in destinations) {
              final Size size = tester.getSize(
                find.bySemanticsLabel(destination.label),
              );
              expect(
                size.width,
                greaterThanOrEqualTo(UiDensity.hitBox),
                reason:
                    '${destination.label}: ${size.width} wide at '
                    '${destinations.length} destinations, ${density.name}, '
                    'scale $scale',
              );
              expect(
                size.height,
                greaterThanOrEqualTo(UiDensity.hitBox),
                reason:
                    '${destination.label}: ${size.height} tall at scale '
                    '$scale',
              );
            }
          }
        }
      }
    });

    testWidgets('a tap on any corner of a cell selects that cell', (
      WidgetTester tester,
    ) async {
      final List<int> selected = <int>[];
      await _pumpBar(
        tester,
        destinations: threeDestinations,
        onSelect: selected.add,
        inset: 34,
      );
      for (int index = 0; index < threeDestinations.length; index++) {
        final Rect cell = tester.getRect(
          find.bySemanticsLabel(threeDestinations[index].label),
        );
        expect(
          cell.width,
          closeTo(390 / threeDestinations.length, 0.001),
          reason: 'cells are equal and together fill the bar',
        );
        for (final Alignment corner in <Alignment>[
          Alignment.topLeft,
          Alignment.topRight,
          Alignment.bottomLeft,
          Alignment.bottomRight,
        ]) {
          selected.clear();
          await tester.tapAt(corner.withinRect(cell.deflate(1)));
          await tester.pumpAndSettle();
          expect(selected, <int>[index], reason: '$corner of cell $index');
        }
      }
    });

    for (final double inset in <double>[0, 24, 34]) {
      testWidgets('the bar is its content plus a $inset dp inset', (
        WidgetTester tester,
      ) async {
        await _pumpBar(tester, inset: inset);
        final Size size = _barSize(tester);
        expect(size.width, 390, reason: 'full width');
        expect(size.height, 56 + inset);
        // The cells stop where the inset starts, and the ground carries on
        // under it, so the bar's content is never pushed into the gesture bar.
        final Rect cell = tester.getRect(find.bySemanticsLabel('Queue'));
        expect(cell.height, 56);
        expect(
          tester.getRect(find.byType(UiTabBar)).bottom - cell.bottom,
          inset,
        );
      });
    }

    testWidgets('the bar docks flush to the bottom edge of its window', (
      WidgetTester tester,
    ) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(390, 844);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: const SizedBox(
            width: 390,
            height: 844,
            child: Column(
              children: <Widget>[
                Expanded(child: SizedBox.expand()),
                _BarHost(destinations: twoDestinations, inset: 34),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final Rect bar = tester.getRect(find.byType(UiTabBar));
      expect(bar.bottom, 844, reason: 'flush to the bottom edge');
      expect(bar.left, 0);
      expect(bar.right, 390);
    });

    testWidgets('the height it reports is the height it draws', (
      WidgetTester tester,
    ) async {
      late double content;
      late double whole;
      await tester.pumpWidget(
        uiHarness(
          textScaler: const TextScaler.linear(2),
          child: Builder(
            builder: (BuildContext context) => MediaQuery(
              data: MediaQuery.of(
                context,
              ).copyWith(viewPadding: const EdgeInsets.only(bottom: 24)),
              child: Builder(
                builder: (BuildContext context) {
                  content = UiTabBar.contentHeightOf(context);
                  whole = UiTabBar.heightOf(context);
                  return UiTabBar(
                    destinations: twoDestinations,
                    currentIndex: 0,
                    onSelect: (int _) {},
                  );
                },
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(content, 68);
      expect(whole, 68 + 24);
      expect(_barSize(tester).height, whole);
    });

    testWidgets('the content height is 56 at normal text, as the iPhone bar '
        'had, and grows with the label and the gap under it', (
      WidgetTester tester,
    ) async {
      // `max(56, 32 + scaled 16 + 4)`. At normal text the resting height
      // governs and it is the 56 the owner approved on the iPhone bar. Above
      // it the 4 dp the cell pads under the label is counted, which the first
      // version of the formula left out (2026-10-17 correction): at 200
      // percent the bar is 68 dp, not 64.
      await _pumpBar(tester);
      final UiThemeData ui = tester.element(find.byType(UiTabBar)).ui;
      final UiTabBarStyle style = UiTabBarStyle.resolve(ui);
      // The resting height is a token, `space.tabBar`, and not a number
      // written in the control; it sits beside `space.topBar` and the two are
      // decided separately.
      expect(ui.space.tabBar, 56);
      expect(style.restingHeight, ui.space.tabBar);
      expect(style.restingHeight, 56);
      expect(style.glyphBand, 32);
      expect(style.labelAllowance, 16);
      expect(style.labelGap, 4);
      expect(style.glyphSize, 24);
      for (final double scale in <double>[0.8, 1, 1.15, 1.3, 1.5, 2, 3]) {
        final TextScaler scaler = TextScaler.linear(scale);
        expect(
          style.contentHeightOf(scaler),
          math.max(56, 32 + scaler.scale(16) + 4),
          reason: 'scale $scale',
        );
      }
      expect(style.contentHeightOf(TextScaler.noScaling), 56);
      expect(style.contentHeightOf(const TextScaler.linear(2)), 68);
    });

    testWidgets('the glyph keeps its air at every text scale: 4 dp above it '
        'and 4 dp between it and the label', (WidgetTester tester) async {
      for (final double scale in <double>[1, 1.15, 1.3, 1.5, 2, 3]) {
        await _pumpBar(
          tester,
          destinations: threeDestinations,
          textScaler: TextScaler.linear(scale),
          inset: 34,
        );
        final Rect bar = tester.getRect(find.byType(UiTabBar));
        for (final UiNavDestination destination in threeDestinations) {
          final Rect glyph = tester.getRect(
            find.byKey(ValueKey<String>('icon-${destination.label}')),
          );
          final Rect label = tester.getRect(find.text(destination.label));
          expect(
            glyph.top - bar.top,
            greaterThanOrEqualTo(4),
            reason:
                'the glyph of "${destination.label}" is ${glyph.top - bar.top} '
                'dp under the bar\'s top edge at scale $scale',
          );
          expect(
            label.top - glyph.bottom,
            greaterThanOrEqualTo(4),
            reason:
                'the label of "${destination.label}" is '
                '${label.top - glyph.bottom} dp under its glyph at scale '
                '$scale (a negative number is an overlap)',
          );
          expect(
            glyph.bottom,
            lessThanOrEqualTo(label.top),
            reason: 'the label overlaps the glyph at scale $scale',
          );
          expect(
            (bar.bottom - 34) - label.bottom,
            greaterThanOrEqualTo(4),
            reason: 'the label sits under 4 dp from the inset at scale $scale',
          );
        }
      }
    });

    testWidgets('the bar grows with the text and its labels are not cut', (
      WidgetTester tester,
    ) async {
      final Map<double, double> heights = <double, double>{};
      for (final double scale in <double>[1, 1.3, 2]) {
        final List<FlutterErrorDetails> reported = <FlutterErrorDetails>[];
        final FlutterExceptionHandler? previous = FlutterError.onError;
        FlutterError.onError = reported.add;
        await _pumpBar(
          tester,
          destinations: threeDestinations,
          textScaler: TextScaler.linear(scale),
          inset: 34,
        );
        FlutterError.onError = previous;
        expect(
          reported.where(
            (FlutterErrorDetails d) =>
                d.exceptionAsString().contains('overflowed'),
          ),
          isEmpty,
          reason: 'overflow at text scale $scale',
        );
        heights[scale] = _barSize(tester).height - 34;
        for (final UiNavDestination destination in threeDestinations) {
          final RenderParagraph paragraph = tester
              .renderObject<RenderParagraph>(find.text(destination.label));
          expect(
            paragraph.didExceedMaxLines,
            isFalse,
            reason:
                '"${destination.label}" is cut at scale $scale on a 390 dp '
                'phone',
          );
          final Rect label = tester.getRect(find.text(destination.label));
          final Rect glyph = tester.getRect(
            find.byKey(ValueKey<String>('icon-${destination.label}')),
          );
          expect(
            glyph.bottom,
            lessThanOrEqualTo(label.top),
            reason: 'the glyph runs into "${destination.label}" at $scale',
          );
          expect(
            label.bottom,
            lessThanOrEqualTo(
              tester.getRect(find.byType(UiTabBar)).bottom - 34,
            ),
            reason: 'the label sinks into the inset at scale $scale',
          );
        }
      }
      expect(heights[1], 56);
      expect(
        heights[1.3],
        closeTo(56.8, 1e-9),
        reason: '32 + 20.8 + 4 is the first height over the 56 floor',
      );
      expect(heights[2], 68);
      expect(heights[2]!, greaterThan(heights[1]!), reason: 'it grows');
    });

    testWidgets('five destinations at 200 percent text do not overflow', (
      WidgetTester tester,
    ) async {
      final List<FlutterErrorDetails> reported = <FlutterErrorDetails>[];
      final FlutterExceptionHandler? previous = FlutterError.onError;
      FlutterError.onError = reported.add;
      await _pumpBar(
        tester,
        destinations: fiveDestinations,
        textScaler: const TextScaler.linear(2),
        size: const Size(360, 800),
      );
      FlutterError.onError = previous;
      expect(
        reported.where(
          (FlutterErrorDetails d) =>
              d.exceptionAsString().contains('overflowed'),
        ),
        isEmpty,
      );
      for (final UiNavDestination destination in fiveDestinations) {
        expect(
          find.bySemanticsLabel(destination.label),
          findsOneWidget,
          reason: 'every destination is still reachable, ellipsised or not',
        );
      }
    });
  });

  group('paint', () {
    testWidgets('the ground is paper and the top edge is one physical pixel '
        'of boundary', (WidgetTester tester) async {
      for (final Brightness mode in Brightness.values) {
        for (final double ratio in <double>[1, 2, 3]) {
          await _pumpBar(
            tester,
            brightness: mode,
            devicePixelRatio: ratio,
            inset: 34,
          );
          final UiThemeData ui = tester.element(find.byType(UiTabBar)).ui;
          final DecoratedBox box = tester.widget<DecoratedBox>(
            find
                .descendant(
                  of: find.byType(UiTabBar),
                  matching: find.byType(DecoratedBox),
                )
                .first,
          );
          final BoxDecoration decoration = box.decoration as BoxDecoration;
          expect(decoration.color, ui.color.paper, reason: '$mode ground');
          final Border border = decoration.border! as Border;
          expect(border.top.color, ui.color.boundary, reason: '$mode line');
          expect(
            border.top.width,
            closeTo(1 / ratio, 1e-9),
            reason: 'one physical pixel at a ratio of $ratio',
          );
          expect(border.bottom, BorderSide.none);
          expect(border.left, BorderSide.none);
          expect(border.right, BorderSide.none);
          expect(decoration.boxShadow, isNull, reason: 'no elevation');
          expect(decoration.gradient, isNull);
          expect(decoration.borderRadius, isNull, reason: 'no pill');
        }
      }
    });

    testWidgets('it is not glass: no pane, no filter, no tint', (
      WidgetTester tester,
    ) async {
      await _pumpBar(tester, destinations: fiveDestinations);
      expectGlassBudget(tester, maxPanes: 0, window: 'the tab bar on its own');
      expect(find.byType(BackdropFilter), findsNothing);
      expect(find.byType(GlassSurface), findsNothing);
    });

    for (final Brightness mode in Brightness.values) {
      testWidgets(
        'the current cell is ink and filled, the rest are secondary and '
        'regular, in ${mode.name}',
        (WidgetTester tester) async {
          await _pumpBar(
            tester,
            destinations: threeDestinations,
            brightness: mode,
            initial: 1,
          );
          final UiThemeData ui = tester.element(find.byType(UiTabBar)).ui;
          for (final MapEntry<int, UiNavDestination> entry
              in threeDestinations.asMap().entries) {
            final bool current = entry.key == 1;
            final ({double fill, double regular}) opacity = _glyphOpacity(
              tester,
              entry.value,
            );
            expect(opacity.fill, current ? 1 : 0, reason: entry.value.label);
            expect(opacity.regular, current ? 0 : 1, reason: entry.value.label);
            expect(
              _labelColour(tester, entry.value.label),
              current ? ui.color.ink : ui.color.inkSecondary,
              reason: 'label of ${entry.value.label}',
            );
            final Finder icons = find.descendant(
              of: find.byKey(ValueKey<String>('icon-${entry.value.label}')),
              matching: find.byType(UiIcon),
            );
            final UiIcon regular = tester.widget<UiIcon>(icons.at(0));
            final UiIcon fill = tester.widget<UiIcon>(icons.at(1));
            expect(regular.current, isFalse);
            expect(regular.color, ui.color.inkSecondary);
            expect(
              fill.current,
              isTrue,
              reason: 'the fill form (09 section 7)',
            );
            expect(fill.color, ui.color.ink);
            expect(regular.size, UiIconSize.action);
            expect(fill.size, UiIconSize.action);
            expect(
              entry.value.icon.resolve(current: true),
              isNot(entry.value.icon.resolve()),
              reason: 'the fill glyph is a different form from the regular one',
            );
          }
        },
      );
    }

    testWidgets('labels are label.small, one line, sentence case', (
      WidgetTester tester,
    ) async {
      await _pumpBar(tester, destinations: threeDestinations);
      final UiThemeData ui = tester.element(find.byType(UiTabBar)).ui;
      for (final UiNavDestination destination in threeDestinations) {
        final RenderParagraph paragraph = tester.renderObject<RenderParagraph>(
          find.text(destination.label),
        );
        final TextStyle style = paragraph.text.style!;
        expect(style.fontSize, ui.type.labelSmall.fontSize);
        expect(style.fontVariations, ui.type.labelSmall.fontVariations);
        expect(paragraph.maxLines, 1);
        expect(paragraph.softWrap, isFalse);
        expect(destination.label, isNot(destination.label.toUpperCase()));
      }
    });
  });

  group('motion', () {
    testWidgets('the change cross-fades over the navigation token', (
      WidgetTester tester,
    ) async {
      await _pumpBar(tester, destinations: threeDestinations);
      final UiThemeData ui = tester.element(find.byType(UiTabBar)).ui;
      expect(ui.motion.navigationGlide, greaterThan(Duration.zero));
      final Color before = _labelColour(tester, 'Intake')!;

      await tester.tap(find.bySemanticsLabel('Intake'));
      await tester.pump();
      await tester.pump(ui.motion.navigationGlide ~/ 2);
      final double fill = _glyphOpacity(tester, threeDestinations[1]).fill;
      expect(fill, greaterThan(0), reason: 'the fill form has begun to arrive');
      expect(fill, lessThan(1), reason: 'and has not yet arrived');
      final Color midway = _labelColour(tester, 'Intake')!;
      expect(midway, isNot(before));
      expect(midway, isNot(ui.color.ink));

      await tester.pumpAndSettle();
      expect(_glyphOpacity(tester, threeDestinations[1]).fill, 1);
      expect(_labelColour(tester, 'Intake'), ui.color.ink);
    });

    testWidgets('under reduced motion the change lands in one frame', (
      WidgetTester tester,
    ) async {
      await _pumpBar(
        tester,
        destinations: threeDestinations,
        disableAnimations: true,
      );
      final UiThemeData ui = tester.element(find.byType(UiTabBar)).ui;
      expect(ui.motion.navigationGlide, Duration.zero);

      await tester.tap(find.bySemanticsLabel('Intake'));
      await tester.pump();
      expect(_glyphOpacity(tester, threeDestinations[1]).fill, 1);
      expect(_glyphOpacity(tester, threeDestinations[0]).fill, 0);
      expect(_labelColour(tester, 'Intake'), ui.color.ink);
      expect(_labelColour(tester, 'Queue'), ui.color.inkSecondary);
      expect(
        tester.binding.transientCallbackCount,
        0,
        reason: 'an animation is still running under reduced motion',
      );
    });
  });

  group('keyboard and focus', () {
    testWidgets('arrows move focus, Enter and Space select, focus wraps', (
      WidgetTester tester,
    ) async {
      final List<int> selected = <int>[];
      await _pumpBar(
        tester,
        destinations: threeDestinations,
        onSelect: selected.add,
      );

      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();
      expect(selected, isEmpty, reason: 'arrows move focus and nothing else');

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(selected, <int>[2]);

      // Right from the last wraps to the first, Space selects it.
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.space);
      await tester.pumpAndSettle();
      expect(selected, <int>[2, 0]);

      // Left from the first wraps to the last.
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(selected, <int>[2, 0, 2]);
    });

    testWidgets('the arrow keys mirror under RTL', (WidgetTester tester) async {
      final List<int> selected = <int>[];
      await _pumpBar(
        tester,
        destinations: threeDestinations,
        onSelect: selected.add,
        textDirection: TextDirection.rtl,
      );
      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
      await tester.pumpAndSettle();
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(selected, <int>[
        1,
      ], reason: 'left is forward in a right to left bar');
      // And the first destination is on the right.
      expect(
        tester.getCenter(find.bySemanticsLabel('Queue')).dx,
        greaterThan(tester.getCenter(find.bySemanticsLabel('Sources')).dx),
      );
    });

    testWidgets(
      'keyboard focus rings the cell, inside it; a press draws none',
      (WidgetTester tester) async {
        FocusManager.instance.highlightStrategy =
            FocusHighlightStrategy.alwaysTraditional;
        addTearDown(
          () => FocusManager.instance.highlightStrategy =
              FocusHighlightStrategy.automatic,
        );
        await _pumpBar(tester, destinations: threeDestinations);
        List<FocusRing> rings() => tester
            .widgetList<FocusRing>(find.byType(FocusRing))
            .where((FocusRing ring) => ring.visible)
            .toList();
        expect(rings(), isEmpty, reason: 'nothing is focused yet');

        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pumpAndSettle();
        expect(rings(), hasLength(1), reason: 'one cell holds the ring');
        expect(
          rings().single.inset,
          isTrue,
          reason:
              'the bar touches the screen edge and its neighbours, so the ring '
              'is drawn inside the cell where nothing can cut it',
        );

        await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
        await tester.pumpAndSettle();
        expect(
          rings(),
          hasLength(1),
          reason: 'the ring moves, it does not copy',
        );

        FocusManager.instance.highlightStrategy =
            FocusHighlightStrategy.alwaysTouch;
        await tester.pumpAndSettle();
        final TestGesture press = await tester.startGesture(
          tester.getCenter(find.bySemanticsLabel('Sources')),
          kind: PointerDeviceKind.touch,
        );
        await tester.pumpAndSettle();
        expect(rings(), isEmpty, reason: 'a pointer press never draws a ring');
        await press.up();
        await tester.pumpAndSettle();
      },
    );

    testWidgets('a press shows the state layer on the pressed cell only', (
      WidgetTester tester,
    ) async {
      await _pumpBar(tester, destinations: threeDestinations);
      final UiThemeData ui = tester.element(find.byType(UiTabBar)).ui;
      double layer(String label) {
        final StateLayer widget = tester.widget<StateLayer>(
          find
              .descendant(
                of: find.bySemanticsLabel(label),
                matching: find.byType(StateLayer),
              )
              .first,
        );
        return StateLayer.opacityFor(widget.states, ui);
      }

      final TestGesture press = await tester.startGesture(
        tester.getCenter(find.bySemanticsLabel('Intake')),
        kind: PointerDeviceKind.touch,
      );
      await tester.pump();
      expect(layer('Intake'), ui.color.pressedOpacity);
      expect(layer('Queue'), 0);
      await press.up();
      await tester.pumpAndSettle();
    });
  });

  for (final UiNavDestination destination in threeDestinations) {
    testWidgets('control contract: ${destination.label}', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        (BuildContext context) =>
            const _BarHost(destinations: threeDestinations),
        semanticsLabel: destination.label,
        labelsNeverWrap: true,
        geometryFromType: true,
        fit: FitExpectation(
          check: (WidgetTester tester, double width) async {
            expect(
              find.bySemanticsLabel(destination.label),
              findsOneWidget,
              reason: 'every destination stays reachable at $width dp',
            );
            expect(
              tester.getSize(find.bySemanticsLabel(destination.label)).width,
              greaterThanOrEqualTo(UiDensity.hitBox),
              reason: 'a cell never shrinks under 48 dp at $width dp',
            );
          },
        ),
      );
    });
  }

  // ---------------------------------------------------------------------
  // Narrow windows (10 section 2 clause 2 and 11 section 3.3). Equal cells
  // are only equal while each keeps its 48 dp hit box; under that the bar
  // lays the cells at the floor in a row that scrolls, like UiPillNav.
  // ---------------------------------------------------------------------
  group('narrow windows', () {
    const List<double> widths = <double>[480, 360, 280, 200];

    List<UiNavDestination> first(int count) =>
        fiveDestinations.take(count).toList();

    /// Pumps [count] destinations in a window [width] wide, collecting what
    /// the framework reports instead of throwing it.
    Future<List<FlutterErrorDetails>> pumpNarrow(
      WidgetTester tester, {
      required int count,
      required double width,
      UiDensityMode density = UiDensityMode.touch,
      double scale = 1,
      int initial = 0,
    }) async {
      final List<FlutterErrorDetails> reported = <FlutterErrorDetails>[];
      final FlutterExceptionHandler? previous = FlutterError.onError;
      FlutterError.onError = reported.add;
      try {
        await _pumpBar(
          tester,
          destinations: first(count),
          density: density,
          textScaler: TextScaler.linear(scale),
          size: Size(width, 800),
          initial: initial,
        );
      } finally {
        FlutterError.onError = previous;
      }
      return reported;
    }

    Iterable<FlutterErrorDetails> overflows(List<FlutterErrorDetails> all) =>
        all.where(
          (FlutterErrorDetails d) =>
              d.exceptionAsString().contains('overflowed'),
        );

    for (final int count in <int>[2, 3, 4, 5]) {
      for (final double width in widths) {
        testWidgets(
          '$count destinations in $width dp: every cell is at least 48 by '
          '48, at both densities and text 1.0 and 2.0, with no overflow',
          (WidgetTester tester) async {
            final bool scrolls = width < UiDensity.hitBox * count;
            for (final UiDensityMode density in UiDensityMode.values) {
              for (final double scale in <double>[1, 2]) {
                final List<FlutterErrorDetails> reported = await pumpNarrow(
                  tester,
                  count: count,
                  width: width,
                  density: density,
                  scale: scale,
                );
                final String where =
                    '$count in $width dp, ${density.name}, scale $scale';
                expect(
                  overflows(reported),
                  isEmpty,
                  reason: 'overflow: $where',
                );
                expect(tester.takeException(), isNull, reason: where);
                for (final UiNavDestination destination in first(count)) {
                  final Size size = tester.getSize(
                    find.bySemanticsLabel(destination.label),
                  );
                  expect(
                    size.width,
                    greaterThanOrEqualTo(UiDensity.hitBox),
                    reason:
                        '${destination.label} is ${size.width} wide: $where',
                  );
                  expect(
                    size.height,
                    greaterThanOrEqualTo(UiDensity.hitBox),
                    reason:
                        '${destination.label} is ${size.height} tall: $where',
                  );
                  if (!scrolls) {
                    expect(
                      size.width,
                      closeTo(width / count, 0.001),
                      reason: 'equal cells: $where',
                    );
                  }
                }
                expect(
                  find.byType(SingleChildScrollView),
                  scrolls ? findsOneWidget : findsNothing,
                  reason: 'scrolls only under 48 dp a cell: $where',
                );
              }
            }
          },
        );
      }
    }

    for (final int count in <int>[3, 4, 5]) {
      testWidgets(
        '$count destinations in 120 dp: the current one is in view whichever '
        'it is on the first frame, and when it changes',
        (WidgetTester tester) async {
          for (int initial = 0; initial < count; initial++) {
            // A fresh bar, so `initial` is the destination it is built on.
            await tester.pumpWidget(const SizedBox());
            await pumpNarrow(
              tester,
              count: count,
              width: 120,
              initial: initial,
            );
            final Rect bar = tester.getRect(find.byType(UiTabBar));
            Rect cellOf(int index) => tester.getRect(
              find.bySemanticsLabel(first(count)[index].label),
            );
            expect(
              cellOf(initial).left,
              greaterThanOrEqualTo(bar.left - 0.5),
              reason: 'destination $initial of $count starts before the bar',
            );
            expect(
              cellOf(initial).right,
              lessThanOrEqualTo(bar.right + 0.5),
              reason: 'destination $initial of $count ends after the bar',
            );
            for (int next = 0; next < count; next++) {
              tester.state<_BarHostState>(find.byType(_BarHost)).choose(next);
              await tester.pumpAndSettle();
              expect(cellOf(next).left, greaterThanOrEqualTo(bar.left - 0.5));
              expect(cellOf(next).right, lessThanOrEqualTo(bar.right + 0.5));
            }
          }
        },
      );
    }

    testWidgets('a scrolling bar fades the edge there is more beyond, and an '
        'equal one has no scroller', (WidgetTester tester) async {
      await pumpNarrow(tester, count: 5, width: 200);
      expect(
        find.descendant(
          of: find.byType(UiTabBar),
          matching: find.byType(ShaderMask),
        ),
        findsOneWidget,
      );
      final ScrollableState scroller = tester.state<ScrollableState>(
        find.byType(Scrollable),
      );
      expect(scroller.position.pixels, 0);
      expect(scroller.position.extentAfter, greaterThan(0));
      await pumpNarrow(tester, count: 5, width: 390);
      expect(find.byType(Scrollable), findsNothing);
      expect(find.byType(ShaderMask), findsNothing);
    });

    testWidgets('the scrolling bar keeps its tab list, its tabs and one '
        'selected', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await pumpNarrow(tester, count: 5, width: 200, initial: 2);
      expect(tester.takeException(), isNull);
      final Finder list = find.byWidgetPredicate(
        (Widget widget) =>
            widget is Semantics &&
            widget.properties.role == SemanticsRole.tabBar,
      );
      expect(list, findsOneWidget);
      int selected = 0;
      for (final UiNavDestination destination in fiveDestinations) {
        final SemanticsData data = tester
            .getSemantics(find.bySemanticsLabel(destination.label))
            .getSemanticsData();
        expect(data.role, SemanticsRole.tab, reason: destination.label);
        expect(data.label, destination.label);
        if (data.flagsCollection.isSelected == Tristate.isTrue) selected++;
      }
      expect(selected, 1);
      expect(
        tester
            .getSemantics(find.bySemanticsLabel(fiveDestinations[2].label))
            .getSemanticsData()
            .flagsCollection
            .isSelected,
        Tristate.isTrue,
      );
      handle.dispose();
    });

    testWidgets('keyboard: arrows reach a cell that was off screen, bring it '
        'into view, ring it, and Enter selects it', (
      WidgetTester tester,
    ) async {
      FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.alwaysTraditional;
      addTearDown(
        () => FocusManager.instance.highlightStrategy =
            FocusHighlightStrategy.automatic,
      );
      final List<int> selected = <int>[];
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(200, 800);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        uiHarness(
          size: const Size(200, 800),
          child: _BarHost(
            destinations: fiveDestinations,
            onSelect: selected.add,
          ),
        ),
      );
      await tester.pumpAndSettle();
      final Rect bar = tester.getRect(find.byType(UiTabBar));
      Rect cell(int i) =>
          tester.getRect(find.bySemanticsLabel(fiveDestinations[i].label));
      expect(cell(4).right, greaterThan(bar.right), reason: 'off screen');

      await tester.sendKeyEvent(LogicalKeyboardKey.tab);
      await tester.pumpAndSettle();
      for (int i = 0; i < 4; i++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
        await tester.pumpAndSettle();
        expect(
          cell(i + 1).right,
          lessThanOrEqualTo(bar.right + 0.5),
          reason: 'the focused cell ${i + 1} is not in view',
        );
        expect(cell(i + 1).left, greaterThanOrEqualTo(bar.left - 0.5));
      }
      final List<FocusRing> rings = tester
          .widgetList<FocusRing>(find.byType(FocusRing))
          .where((FocusRing ring) => ring.visible)
          .toList();
      expect(rings, hasLength(1));
      expect(rings.single.inset, isTrue);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();
      expect(selected, <int>[4]);
      // Left from the first wraps to the last, which is in view again.
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowRight);
      await tester.pumpAndSettle();
      expect(cell(0).left, greaterThanOrEqualTo(bar.left - 0.5));
    });

    testWidgets('five destinations keep the control contract at the last one '
        'too, in every fit width', (WidgetTester tester) async {
      for (final String label in <String>['Queue', 'Account']) {
        await expectControlContract(
          tester,
          (BuildContext context) =>
              const _BarHost(destinations: fiveDestinations),
          semanticsLabel: label,
          labelsNeverWrap: true,
          geometryFromType: true,
          fit: FitExpectation(
            check: (WidgetTester tester, double width) async {
              final Size size = tester.getSize(find.bySemanticsLabel(label));
              expect(
                size.width,
                greaterThanOrEqualTo(UiDensity.hitBox),
                reason: '"$label" is ${size.width} wide at $width dp',
              );
              expect(size.height, greaterThanOrEqualTo(UiDensity.hitBox));
            },
          ),
        );
      }
    });
  });

  // ---------------------------------------------------------------------
  // A label the cell cannot hold ends in an ellipsis and carries its whole
  // word in a tooltip (10 section 2 clause 15).
  // ---------------------------------------------------------------------
  group('truncated labels', () {
    /// The labels whose paragraph ends in an ellipsis right now.
    List<String> cutLabels(WidgetTester tester) => <String>[
      for (final UiNavDestination d in fiveDestinations)
        if (tester.allRenderObjects.whereType<RenderParagraph>().any(
          (RenderParagraph p) =>
              p.text.toPlainText(includeSemanticsLabels: false) == d.label &&
              p.didExceedMaxLines,
        ))
          d.label,
    ];

    /// The tooltips: one per cut label, and none for a word that fits, so a
    /// cell that is not cut carries no second tap recognizer.
    final Finder armed = find.byType(UiTooltip);

    testWidgets('a bar whose labels all fit arms no tooltip', (
      WidgetTester tester,
    ) async {
      await _pumpBar(tester);
      expect(armed, findsNothing);
      expect(cutLabels(tester), isEmpty);
    });

    testWidgets('a cut label shows its whole word on hover, and the tab '
        'still reads once', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      await _pumpBar(
        tester,
        destinations: fiveDestinations,
        textScaler: const TextScaler.linear(2),
        size: const Size(360, 800),
      );
      final List<String> cut = cutLabels(tester);
      expect(
        cut,
        isNotEmpty,
        reason: 'five destinations at 200 percent text in 360 dp cut a word',
      );
      expect(
        armed,
        findsNWidgets(cut.length),
        reason: 'a tooltip armed for each cut label, and for no other',
      );
      // Each tab reads once: the tooltip adds no second node, and the tab
      // carries no tooltip of its own.
      for (final UiNavDestination destination in fiveDestinations) {
        expect(find.bySemanticsLabel(destination.label), findsOneWidget);
        final SemanticsData data = tester
            .getSemantics(find.bySemanticsLabel(destination.label))
            .getSemanticsData();
        expect(data.label, destination.label);
        expect(data.tooltip, isEmpty, reason: destination.label);
        // A cut cell is still a tab, with its selected state, inside the
        // tooltip's wrapper.
        expect(data.role, SemanticsRole.tab, reason: destination.label);
        expect(
          data.flagsCollection.isSelected,
          destination == fiveDestinations.first
              ? Tristate.isTrue
              : Tristate.isFalse,
          reason: destination.label,
        );
      }

      final String word = cut.first;
      expect(find.text(word), findsOneWidget, reason: 'no tooltip drawn yet');
      final TestGesture pointer = await tester.createGesture(
        kind: PointerDeviceKind.mouse,
      );
      await pointer.addPointer(location: Offset.zero);
      addTearDown(pointer.removePointer);
      await tester.pump();
      await pointer.moveTo(tester.getCenter(find.text(word)));
      await tester.pump();
      await tester.pump(UiTooltipStyle.hoverDelay);
      await tester.pumpAndSettle();
      expect(
        find.text(word),
        findsNWidgets(2),
        reason: 'the tooltip draws the whole word beside the cut label',
      );
      handle.dispose();
    });

    testWidgets('a tap on a cut label still selects its destination', (
      WidgetTester tester,
    ) async {
      final List<int> selected = <int>[];
      await _pumpBar(
        tester,
        destinations: fiveDestinations,
        textScaler: const TextScaler.linear(2),
        size: const Size(360, 800),
        onSelect: selected.add,
      );
      final String word = cutLabels(tester).first;
      await tester.tap(find.text(word));
      await tester.pumpAndSettle();
      expect(selected, <int>[
        fiveDestinations.indexWhere((UiNavDestination d) => d.label == word),
      ], reason: 'the tooltip must not take the tap from the tab');
    });
  });
}
