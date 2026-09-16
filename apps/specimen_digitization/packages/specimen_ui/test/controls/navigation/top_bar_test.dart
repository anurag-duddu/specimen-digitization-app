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
}) => Builder(
  builder: (BuildContext context) => MediaQuery(
    data: MediaQuery.of(context).copyWith(padding: padding),
    child: SizedBox(
      width: 800,
      child: UiTopBar(
        leading: leading,
        title: title,
        center: center,
        actions: actions,
        scrolledUnder: scrolledUnder,
      ),
    ),
  ),
);

void main() {
  testWidgets('it is space.topBar at touch and the hit box at pointer', (
    WidgetTester tester,
  ) async {
    for (final UiDensityMode density in UiDensityMode.values) {
      await tester.pumpWidget(
        uiHarness(density: density, child: _bar(title: 'Queue')),
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
    expect(switcher.left, greaterThan(tester.getRect(find.text('Queue')).right));
    expect(
      switcher.right,
      lessThan(tester.getRect(find.byKey(const ValueKey<String>('reload'))).left),
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
        child: _bar(
          title: 'Queue',
          padding: const EdgeInsets.only(top: 44),
        ),
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
        title: 'Queue',
        actions: <Widget>[
          UiButton(label: 'Reload the queue', onPressed: () {}),
        ],
      ),
      semanticsLabel: 'Reload the queue',
    );
  });
}
