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
        matching: find.byType(ColoredBox),
      ),
    );
    expect(bar.top, 0, reason: 'once scrolled past, the bar pins to the top');
    expect(bar.height, extent);
    // The marker reports the extent the chrome budget counts.
    final Element marker = tester.element(find.byType(PinnedChrome));
    expect(PinnedChrome.extentOf(marker), extent);
  });
}
