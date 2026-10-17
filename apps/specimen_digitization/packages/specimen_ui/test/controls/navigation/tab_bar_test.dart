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
      expect(content, 64);
      expect(whole, 64 + 24);
      expect(_barSize(tester).height, whole);
    });

    testWidgets('the content height is the metric the iPhone bar had', (
      WidgetTester tester,
    ) async {
      // `max(56, 32 + scaled 16)`: the formula the shell handed
      // `CupertinoTabBar` until 2026-10-17, which the owner called perfect.
      await _pumpBar(tester);
      final UiTabBarStyle style = UiTabBarStyle.resolve(
        tester.element(find.byType(UiTabBar)).ui,
      );
      expect(style.restingHeight, 56);
      expect(style.glyphBand, 32);
      expect(style.labelAllowance, 16);
      expect(style.glyphSize, 24);
      for (final double scale in <double>[0.8, 1, 1.15, 1.3, 1.5, 2, 3]) {
        final TextScaler scaler = TextScaler.linear(scale);
        expect(
          style.contentHeightOf(scaler),
          math.max(56, 32 + scaler.scale(16)),
          reason: 'scale $scale',
        );
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
      expect(heights[1.3], 56, reason: '32 + 20.8 is still under 56');
      expect(heights[2], 64);
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
}
