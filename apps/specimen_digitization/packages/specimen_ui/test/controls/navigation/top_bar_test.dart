// The top bar (10 section 4.4, `UiTopBar`).

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
}) => Builder(
  builder: (BuildContext context) {
    final Widget bar = UiTopBar(
      leading: leading,
      title: title,
      center: center,
      actions: actions,
      scrolledUnder: scrolledUnder,
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

  testWidgets('it is transparent at rest and glass once scrolled under', (
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
    expect(glassPaneCount(), 1);
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
}
