// The top bar (10 section 4.4, `UiTopBar`).

import 'dart:ui' as dart_ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

/// A bar inside a window of [width], with the given safe area.
Widget _bar({
  Widget? leading,
  String? title,
  Widget? center,
  List<Widget> actions = const <Widget>[],
  bool? scrolledUnder,
  EdgeInsets padding = EdgeInsets.zero,
  double? width = 800,
  UiTopBarForm form = UiTopBarForm.page,
}) => Builder(
  builder: (BuildContext context) {
    final Widget bar = UiTopBar(
      leading: leading,
      title: title,
      center: center,
      actions: actions,
      scrolledUnder: scrolledUnder,
      form: form,
    );
    return MediaQuery(
      data: MediaQuery.of(context).copyWith(padding: padding),
      // A null width leaves the bar the column it was given, which is what a
      // test of the bar's own fit needs: a pinned 800 is a bar that never
      // runs out of room.
      child: width == null ? bar : SizedBox(width: width, child: bar),
    );
  },
);

/// The four commands the overflow test hands the bar.
List<UiTopBarAction> _fourActions() => <UiTopBarAction>[
  UiTopBarAction(
    icon: UiIcons.reload,
    label: 'Reload the queue',
    onPressed: () {},
  ),
  UiTopBarAction(
    icon: UiIcons.filter,
    label: 'Filter records',
    onPressed: () {},
  ),
  UiTopBarAction(
    icon: UiIcons.saveFilter,
    label: 'Save this filter',
    shortcut: 'S',
    onPressed: () {},
  ),
  UiTopBarAction(icon: UiIcons.help, label: 'Open help', onPressed: () {}),
];

void main() {
  testWidgets('it is space.topBar at touch and the hit box at pointer', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(
          density: density,
          child: _bar(title: 'Queue'),
        ),
      );
      await tester.pumpAndSettle();
      final UiThemeData ui = tester.element(find.byType(UiTopBar)).ui;
      expect(
        tester.getSize(find.byType(UiTopBar)).height,
        density == UiDensityMode.touch ? ui.space.topBar : UiDensity.hitBox,
        reason: '${density.name} density',
      );
    }
  });

  testWidgets('it is transparent at rest and matte once scrolled under', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: _bar(title: 'Queue', scrolledUnder: false)),
    );
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 0);
    expect(find.byType(GlassSurface), findsNothing);

    await tester.pumpWidget(
      uiHarness(child: _bar(title: 'Queue', scrolledUnder: true)),
    );
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 0);
    expect(
      tester.widget<GlassSurface>(find.byType(GlassSurface)).level,
      GlassLevel.flat,
    );
  });

  testWidgets('the title is set in type.title', (WidgetTester tester) async {
    await tester.pumpWidget(uiHarness(child: _bar(title: 'Queue')));
    await tester.pumpAndSettle();
    final UiThemeData ui = tester.element(find.byType(UiTopBar)).ui;
    final TextStyle style = tester.widget<Text>(find.text('Queue')).style!;
    expect(style.fontSize, ui.type.title.fontSize);
    expect(style.color, ui.color.ink);
  });

  testWidgets('leading, title and actions read start to end', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: _bar(
          leading: const SizedBox.square(
            key: ValueKey<String>('back'),
            dimension: 24,
          ),
          title: 'Queue',
          actions: const <Widget>[
            SizedBox.square(key: ValueKey<String>('reload'), dimension: 24),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();
    final double back = tester
        .getCenter(find.byKey(const ValueKey<String>('back')))
        .dx;
    final double title = tester.getCenter(find.text('Queue')).dx;
    final double reload = tester
        .getCenter(find.byKey(const ValueKey<String>('reload')))
        .dx;
    expect(back, lessThan(title));
    expect(title, lessThan(reload));
  });

  testWidgets('the order mirrors under RTL', (WidgetTester tester) async {
    await tester.pumpWidget(
      uiHarness(
        textDirection: TextDirection.rtl,
        child: _bar(
          leading: const SizedBox.square(
            key: ValueKey<String>('back'),
            dimension: 24,
          ),
          title: 'Queue',
          actions: const <Widget>[
            SizedBox.square(key: ValueKey<String>('reload'), dimension: 24),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getCenter(find.byKey(const ValueKey<String>('back'))).dx,
      greaterThan(tester.getCenter(find.text('Queue')).dx),
    );
  });

  testWidgets('the centre slot never sits on the title or the actions', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: _bar(
          title: 'Queue',
          center: const SizedBox(
            key: ValueKey<String>('switcher'),
            width: 200,
            height: 24,
          ),
          actions: const <Widget>[
            SizedBox.square(key: ValueKey<String>('reload'), dimension: 24),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();
    final Rect switcher = tester.getRect(
      find.byKey(const ValueKey<String>('switcher')),
    );
    expect(
      switcher.left,
      greaterThan(tester.getRect(find.text('Queue')).right),
    );
    expect(
      switcher.right,
      lessThan(
        tester.getRect(find.byKey(const ValueKey<String>('reload'))).left,
      ),
    );
  });

  testWidgets('it owns the top safe area so its pane reaches the edge', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _bar(title: 'Queue')));
    await tester.pumpAndSettle();
    final double plain = tester.getSize(find.byType(UiTopBar)).height;
    final double plainTitle =
        tester.getTopLeft(find.text('Queue')).dy -
        tester.getTopLeft(find.byType(UiTopBar)).dy;

    await tester.pumpWidget(
      uiHarness(
        child: _bar(title: 'Queue', padding: const EdgeInsets.only(top: 44)),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.getSize(find.byType(UiTopBar)).height, plain + 44);
    expect(
      tester.getTopLeft(find.text('Queue')).dy -
          tester.getTopLeft(find.byType(UiTopBar)).dy,
      plainTitle + 44,
      reason: 'the content clears the notch while the pane starts above it',
    );
  });

  testWidgets('it grows rather than clipping at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: _bar(title: 'Queue'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Queue'), findsOneWidget);
    expect(
      tester.getSize(find.byType(UiTopBar)).height,
      greaterThanOrEqualTo(tester.getSize(find.text('Queue')).height),
    );
  });

  testWidgets('a control in the actions slot keeps its contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => _bar(
        width: null,
        title: 'Queue',
        actions: <Widget>[
          UiTopBarAction(
            icon: UiIcons.reload,
            label: 'Reload the queue',
            onPressed: () {},
          ),
        ],
      ),
      semanticsLabel: 'Reload the queue',
      labelsNeverWrap: true,
      geometryFromType: true,
      fit: FitExpectation(
        check: (WidgetTester tester, double width) async {
          expect(
            find.text('Queue'),
            findsOneWidget,
            reason: 'the title ellipsises rather than leaving (rule 4)',
          );
        },
      ),
    );
  });

  testWidgets('the actions past the second collapse into an overflow menu', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(360, 800),
        child: _bar(
          width: 360,
          // The compact shell's own bar: the mark leads, because there is
          // neither a rail nor a sidebar to carry it at this width.
          leading: const UiIcon(UiIcons.collection),
          title: 'Queue',
          actions: _fourActions(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.bySemanticsLabel('Reload the queue'),
      findsOneWidget,
      reason: 'the first two commands stay on the bar',
    );
    expect(find.bySemanticsLabel('Filter records'), findsOneWidget);
    expect(
      find.bySemanticsLabel('Save this filter'),
      findsNothing,
      reason: 'the third and fourth are in the menu, not on the bar',
    );
    expect(
      find.bySemanticsLabel(UiTopBarStyle.overflowLabel),
      findsOneWidget,
      reason: 'and the menu has a trigger of its own',
    );

    await tester.tap(find.bySemanticsLabel(UiTopBarStyle.overflowLabel));
    await tester.pumpAndSettle();
    expect(
      find.text('Save this filter'),
      findsOneWidget,
      reason: 'the collapsed command keeps its label',
    );
    expect(
      find.text('S'),
      findsOneWidget,
      reason: 'and its shortcut, which is what the menu column is for',
    );
    expect(find.text('Open help'), findsOneWidget);
  });

  testWidgets('the overflow menu opens inside the window it is at the end of', (
    WidgetTester tester,
  ) async {
    // The trigger is the last thing on the bar, one gutter from the window's
    // edge. Its menu used to hang from the trigger's start and run 200 dp
    // past the window; the popover mirrors so the pane's end meets the
    // trigger's (10 section 3, fit).
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(360, 800);
    addTearDown(tester.view.reset);
    for (final TextDirection direction in TextDirection.values) {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(360, 800),
          textDirection: direction,
          child: _bar(
            width: 360,
            leading: const UiIcon(UiIcons.collection),
            title: 'Queue',
            actions: _fourActions(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final Finder trigger = find.bySemanticsLabel(UiTopBarStyle.overflowLabel);
      await tester.tap(trigger);
      await tester.pumpAndSettle();

      final Rect anchor = tester.getRect(trigger);
      final Rect pane = tester.getRect(find.byType(GlassSurface));
      expect(pane.left, greaterThanOrEqualTo(0), reason: direction.name);
      expect(pane.right, lessThanOrEqualTo(360), reason: direction.name);
      if (direction == TextDirection.ltr) {
        expect(pane.right, moreOrLessEquals(anchor.right, epsilon: 0.5));
      } else {
        expect(pane.left, moreOrLessEquals(anchor.left, epsilon: 0.5));
      }
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('a bar with room draws every action and no overflow', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(1400, 800),
        child: _bar(width: 1400, title: 'Queue', actions: _fourActions()),
      ),
    );
    await tester.pumpAndSettle();
    for (final UiTopBarAction action in _fourActions()) {
      expect(find.bySemanticsLabel(action.label), findsOneWidget);
    }
    expect(find.bySemanticsLabel(UiTopBarStyle.overflowLabel), findsNothing);
  });

  testWidgets('a bar given opaque widgets keeps them all', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(360, 800),
        child: _bar(
          width: 360,
          leading: const UiIcon(UiIcons.collection),
          title: 'Queue',
          actions: const <Widget>[
            UiIcon(UiIcons.reload),
            UiIcon(UiIcons.filter),
            UiIcon(UiIcons.help),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel(UiTopBarStyle.overflowLabel),
      findsNothing,
      reason:
          'a bar cannot put into a menu a control it cannot read, so it keeps '
          'what it was given and the title ellipsises instead',
    );
    expect(find.byType(UiIcon), findsNWidgets(4));
  });

  // ---------------------------------------------------------------------
  // The workspace form (10 section 4.4, amended 2026-10-17): the compact
  // shell's header, one surface with the status strip above it.
  // ---------------------------------------------------------------------
  group('workspace form', () {
    const List<Widget> discs = <Widget>[
      SizedBox.square(key: ValueKey<String>('env'), dimension: 48),
      SizedBox.square(key: ValueKey<String>('account'), dimension: 48),
    ];
    const Widget switcher = SizedBox(
      key: ValueKey<String>('switcher'),
      width: 160,
      height: 48,
    );

    Widget workspace({
      EdgeInsets padding = EdgeInsets.zero,
      bool? scrolledUnder,
      Widget leading = switcher,
      List<Widget> actions = discs,
      double? width = 390,
    }) => Align(
      // Pinned to the window's top left so positions read as a phone's do.
      alignment: Alignment.topLeft,
      child: _bar(
        form: UiTopBarForm.workspace,
        leading: leading,
        actions: actions,
        padding: padding,
        scrolledUnder: scrolledUnder,
        width: width,
      ),
    );

    /// The painted colour at [at], read from the pixels the bar produced.
    Future<dart_ui.Color> colourAt(
      WidgetTester tester,
      GlobalKey boundaryKey,
      Offset at,
    ) async {
      final RenderRepaintBoundary boundary = tester
          .renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
      return (await tester.runAsync(() async {
        final dart_ui.Image image = await boundary.toImage();
        final ByteData data = (await image.toByteData(
          format: dart_ui.ImageByteFormat.rawRgba,
        ))!;
        final int i = (at.dy.toInt() * image.width + at.dx.toInt()) * 4;
        final dart_ui.Color colour = dart_ui.Color.fromARGB(
          255,
          data.getUint8(i),
          data.getUint8(i + 1),
          data.getUint8(i + 2),
        );
        image.dispose();
        return colour;
      }))!;
    }

    for (final Brightness mode in Brightness.values) {
      for (final bool? scrolled in <bool?>[null, false, true]) {
        testWidgets(
          'paints paper under the top inset and the bar, ${mode.name}, '
          'scrolledUnder $scrolled',
          (WidgetTester tester) async {
            final GlobalKey boundary = GlobalKey();
            await tester.pumpWidget(
              uiHarness(
                brightness: mode,
                child: RepaintBoundary(
                  key: boundary,
                  child: workspace(
                    padding: const EdgeInsets.only(top: 47),
                    scrolledUnder: scrolled,
                  ),
                ),
              ),
            );
            await tester.pumpAndSettle();
            final UiThemeData ui = tester.element(find.byType(UiTopBar)).ui;
            final Rect bar = tester.getRect(find.byType(UiTopBar));
            expect(bar.top, 0);
            expect(bar.height, 47 + 64, reason: 'inset plus 8, 48 and 8');
            final dart_ui.Color paper = ui.color.paper;
            final int want = paper.toARGB32();
            // Inside the status strip, at the bar's first row, in its gutter,
            // and on its last pixel row: all one colour, and it is paper.
            for (final Offset at in <Offset>[
              const Offset(3, 1),
              const Offset(3, 23),
              const Offset(3, 46),
              const Offset(3, 47),
              const Offset(3, 80),
              Offset(bar.width - 3, 10),
              Offset(bar.width - 3, bar.height - 1),
            ]) {
              final dart_ui.Color painted = await colourAt(
                tester,
                boundary,
                at,
              );
              expect(
                painted.toARGB32(),
                want,
                reason: 'the bar is not paper at $at in ${mode.name}',
              );
            }
          },
        );
      }
    }

    testWidgets('it owns no glass: opaque ground, no blur, no pane', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: workspace(
            padding: const EdgeInsets.only(top: 24),
            scrolledUnder: true,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(GlassSurface), findsNothing);
      expect(find.byType(BackdropFilter), findsNothing);
      expect(glassPaneCount(), 0);
      final UiThemeData ui = tester.element(find.byType(UiTopBar)).ui;
      final ColoredBox ground = tester.widget<ColoredBox>(
        find
            .descendant(
              of: find.byType(UiTopBar),
              matching: find.byType(ColoredBox),
            )
            .first,
      );
      expect(ground.color, ui.color.paper);
    });

    testWidgets('the page form is not changed by it: transparent, 16 gutter', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: _bar(
            title: 'Queue',
            padding: const EdgeInsets.only(top: 47),
            scrolledUnder: false,
            leading: const SizedBox.square(
              key: ValueKey<String>('back'),
              dimension: 48,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final UiThemeData ui = tester.element(find.byType(UiTopBar)).ui;
      expect(
        find.descendant(
          of: find.byType(UiTopBar),
          matching: find.byWidgetPredicate(
            (Widget w) => w is ColoredBox && w.color == ui.color.paper,
          ),
        ),
        findsNothing,
        reason: 'the page form paints no ground over a page',
      );
      expect(tester.getSize(find.byType(UiTopBar)).height, 47 + 56);
      expect(
        tester.getTopLeft(find.byKey(const ValueKey<String>('back'))).dx,
        16,
        reason: 'the page form keeps its 16 dp gutter',
      );
    });

    for (final UiDensityMode density in UiDensityMode.values) {
      testWidgets('it is 64 dp of bar, 8 dp of air around 48 dp controls, '
          'at ${density.name} density', (WidgetTester tester) async {
        await tester.pumpWidget(
          uiHarness(
            density: density,
            child: workspace(padding: const EdgeInsets.only(top: 24)),
          ),
        );
        await tester.pumpAndSettle();
        expect(tester.getSize(find.byType(UiTopBar)), const Size(390, 24 + 64));
        final Rect lead = tester.getRect(
          find.byKey(const ValueKey<String>('switcher')),
        );
        expect(lead.left, 8, reason: 'a 8 dp gutter');
        expect(lead.top, 24 + 8, reason: '8 dp under the inset');
        final Rect env = tester.getRect(
          find.byKey(const ValueKey<String>('env')),
        );
        final Rect account = tester.getRect(
          find.byKey(const ValueKey<String>('account')),
        );
        expect(account.right, 390 - 8, reason: 'a 8 dp gutter at the end');
        expect(env.right, account.left, reason: 'the actions touch');
        expect(env.top, 24 + 8);
        expect(account.top, 24 + 8);
      });
    }

    testWidgets('it grows with a tall control and keeps 8 dp above and below', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: workspace(
            padding: const EdgeInsets.only(top: 47),
            leading: const SizedBox(
              key: ValueKey<String>('switcher'),
              width: 160,
              height: 64.25,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.getSize(find.byType(UiTopBar)).height, 47 + 8 + 64.25 + 8);
      final Rect lead = tester.getRect(
        find.byKey(const ValueKey<String>('switcher')),
      );
      expect(lead.top, 47 + 8);
      expect(
        tester.getRect(find.byType(UiTopBar)).bottom - lead.bottom,
        8,
        reason: '8 dp under the tallest control',
      );
    });

    testWidgets('side insets are inside the ground and outside the gutters', (
      WidgetTester tester,
    ) async {
      // A phone on its side: the view has to be as wide as the bar.
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(844, 390);
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        uiHarness(
          size: const Size(844, 390),
          child: workspace(
            width: 844,
            padding: const EdgeInsets.only(left: 44, right: 24),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.getRect(find.byType(UiTopBar)).left, 0);
      expect(tester.getRect(find.byType(UiTopBar)).right, 844);
      expect(
        tester.getTopLeft(find.byKey(const ValueKey<String>('switcher'))).dx,
        44 + 8,
      );
      expect(
        tester.getRect(find.byKey(const ValueKey<String>('account'))).right,
        844 - 24 - 8,
      );
    });

    testWidgets('the leading slot takes what the actions leave and is cut, '
        'not overflowed', (WidgetTester tester) async {
      final List<FlutterErrorDetails> reported = <FlutterErrorDetails>[];
      final FlutterExceptionHandler? previous = FlutterError.onError;
      FlutterError.onError = reported.add;
      await tester.pumpWidget(
        uiHarness(
          child: workspace(
            width: 360,
            leading: const SizedBox(
              key: ValueKey<String>('switcher'),
              width: 2000,
              height: 48,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      FlutterError.onError = previous;
      expect(
        reported.where(
          (FlutterErrorDetails d) => d.toString().contains('overflow'),
        ),
        isEmpty,
      );
      final Rect lead = tester.getRect(
        find.byKey(const ValueKey<String>('switcher')),
      );
      expect(lead.left, 8);
      expect(
        lead.right,
        tester.getRect(find.byKey(const ValueKey<String>('env'))).left,
        reason: 'the leading slot is bounded by the first action',
      );
    });

    testWidgets('the order mirrors under RTL', (WidgetTester tester) async {
      await tester.pumpWidget(
        uiHarness(textDirection: TextDirection.rtl, child: workspace()),
      );
      await tester.pumpAndSettle();
      expect(
        tester.getRect(find.byKey(const ValueKey<String>('switcher'))).right,
        390 - 8,
        reason: 'the switcher is at the start, which is the right in RTL',
      );
      expect(
        tester.getRect(find.byKey(const ValueKey<String>('account'))).left,
        8,
      );
    });
  });
}
