import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

void main() {
  testWidgets('the bar scrolls up to the top and then stays there', (
    WidgetTester tester,
  ) async {
    const double extent = 48;
    final ScrollController controller = ScrollController();
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: CustomScrollView(
          controller: controller,
          slivers: <Widget>[
            const SliverToBoxAdapter(child: SizedBox(height: 300)),
            const UiStickyBar(
              extent: extent,
              child: Center(child: Text('Readings')),
            ),
            const SliverToBoxAdapter(child: SizedBox(height: 2000)),
          ],
        ),
      ),
    );
    expect(tester.getTopLeft(find.text('Readings')).dy, greaterThan(300));
    controller.jumpTo(800);
    await tester.pump();
    // The sliver itself is not a box; its painted surface is.
    final Rect bar = tester.getRect(
      find.descendant(
        of: find.byType(UiStickyBar),
        matching: find.byType(DecoratedBox),
      ),
    );
    expect(bar.top, 0, reason: 'once scrolled past, the bar pins to the top');
    expect(bar.height, extent);
    // The marker reports the extent the chrome budget counts.
    final Element marker = tester.element(find.byType(PinnedChrome));
    expect(PinnedChrome.extentOf(marker), extent);
  });

  /// The colour the bar paints behind its row right now, or null for none.
  Color? fill(WidgetTester tester) {
    final DecoratedBox box = tester.widget<DecoratedBox>(
      find.descendant(
        of: find.byType(UiStickyBar),
        matching: find.byType(DecoratedBox),
      ),
    );
    return (box.decoration as BoxDecoration).color;
  }

  testWidgets('paints nothing in the flow and its ground once stuck', (
    WidgetTester tester,
  ) async {
    final ScrollController controller = ScrollController();
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      uiHarness(
        child: CustomScrollView(
          controller: controller,
          slivers: <Widget>[
            const SliverToBoxAdapter(child: SizedBox(height: 300)),
            const UiStickyBar(
              extent: 48,
              child: Center(child: Text('Readings')),
            ),
            const SliverToBoxAdapter(child: SizedBox(height: 2000)),
          ],
        ),
      ),
    );
    final Color ground = tester
        .element(find.byType(UiStickyBar))
        .ui
        .color
        .ground;

    // In the flow the bar is a row of the page and lets the sky through
    // (13 section 3.5): the queue's search row drew a band of ground across
    // the home sky while nothing was stuck.
    expect(fill(tester), isNull);

    controller.jumpTo(299);
    await tester.pump();
    expect(
      fill(tester),
      isNull,
      reason: 'a pixel short of the top, still in the flow',
    );

    controller.jumpTo(301);
    await tester.pump();
    expect(
      fill(tester),
      ground,
      reason: 'stuck, the fill is there at the threshold and does not fade in',
    );
    expect(tester.binding.transientCallbackCount, 0);

    controller.jumpTo(0);
    await tester.pump();
    expect(
      fill(tester),
      isNull,
      reason: 'and it goes when the bar is free again',
    );
  });

  testWidgets('stuck under a pinned header it takes its fill at the edge', (
    WidgetTester tester,
  ) async {
    // The record: the segments scroll up to the collapsed header and stick
    // under it, held by the header's overlap before the bar has scrolled past
    // the top of the viewport at all.
    const Size phone = Size(390, 844);
    final ScrollController controller = ScrollController();
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      uiHarness(
        size: phone,
        child: SizedBox.fromSize(
          size: phone,
          child: CustomScrollView(
            controller: controller,
            slivers: <Widget>[
              const UiCollapsingHeader(
                content: ColoredBox(color: Color(0xFF000000)),
                chrome: <Widget>[Text('Labels')],
              ),
              const SliverToBoxAdapter(child: SizedBox(height: 40)),
              const UiStickyBar(
                extent: 48,
                child: Center(child: Text('Readings')),
              ),
              SliverList.builder(
                itemCount: 30,
                itemBuilder: (BuildContext context, int index) =>
                    const SizedBox(height: 80),
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final Color ground = tester
        .element(find.byType(UiStickyBar))
        .ui
        .color
        .ground;
    expect(fill(tester), isNull);

    controller.jumpTo(controller.position.maxScrollExtent);
    await tester.pumpAndSettle();
    final double headerBottom = phone.height * 0.40;
    expect(
      tester.getRect(find.text('Readings')).top,
      greaterThanOrEqualTo(headerBottom - 0.5),
      reason: 'the bar sticks under the pinned header, not at the top',
    );
    expect(fill(tester), ground);
  });
}
