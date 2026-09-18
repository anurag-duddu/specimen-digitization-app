// `UiCollapsingHeader` (13 section 3.1).
//
// The header is not an interactive control: it has no role, nothing to focus
// and no hit box of its own, so the preamble of 10 section 2 scopes it out of
// the contract the way it scopes out a skeleton or a data tile. What is
// pinned here is what 13 asks of it instead: the fractions it holds, the
// chrome that shrinks to one row, the one frosted pane and where it appears,
// the extent it reports to the budget, and the promise that a reviewer who
// has asked for no motion still sees it follow their finger.

import 'package:flutter/rendering.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../harness/control_contract.dart';

/// The phone 13 section 0 measured the defect on.
const Size phone = Size(390, 844);

const String _chromeOne = 'Whole image';
const String _chromeTwo = 'Labels';
const String _beneath = 'Cleared by a reviewer';

/// Pumps a record shaped screen: the header, then rows under it.
Future<ScrollController> _pumpScreen(
  WidgetTester tester, {
  Size size = phone,
  double scale = 1,
  bool disableAnimations = false,
  List<Widget> chrome = const <Widget>[Text(_chromeOne), Text(_chromeTwo)],
  double maxFraction = UiCollapsingHeader.defaultMaxFraction,
  double minFraction = UiCollapsingHeader.defaultMinFraction,
  bool primary = true,
}) async {
  final ScrollController controller = ScrollController();
  addTearDown(controller.dispose);
  await tester.pumpWidget(
    uiHarness(
      size: size,
      textScaler: TextScaler.linear(scale),
      disableAnimations: disableAnimations,
      child: SizedBox.fromSize(
        size: size,
        child: CustomScrollView(
          controller: controller,
          slivers: <Widget>[
            UiCollapsingHeader(
              primary: primary,
              maxFraction: maxFraction,
              minFraction: minFraction,
              content: const ColoredBox(color: Color(0xFF000000)),
              chrome: chrome,
            ),
            const SliverToBoxAdapter(child: Text(_beneath)),
            SliverList.builder(
              itemCount: 20,
              itemBuilder: (BuildContext context, int index) =>
                  SizedBox(height: 80, child: Text('Reading $index')),
            ),
          ],
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return controller;
}

double _headerHeight(WidgetTester tester) => tester
    .renderObject<RenderSliver>(find.byType(SliverPersistentHeader))
    .geometry!
    .paintExtent;

void main() {
  testWidgets('holds the maximum fraction at rest and the minimum pinned', (
    WidgetTester tester,
  ) async {
    final ScrollController controller = await _pumpScreen(tester);

    expect(_headerHeight(tester), closeTo(phone.height * 0.55, 0.5));

    controller.jumpTo(controller.position.maxScrollExtent);
    await tester.pumpAndSettle();

    // Pinned, not floating: whatever is scrolled, the header holds exactly
    // the fraction it promised and never less and never nothing.
    expect(_headerHeight(tester), closeTo(phone.height * 0.40, 0.5));
  });

  testWidgets('pins at the minimum fraction at 844 dp and 2.0 text scale', (
    WidgetTester tester,
  ) async {
    final ScrollController controller = await _pumpScreen(tester, scale: 2);
    controller.jumpTo(controller.position.maxScrollExtent);
    await tester.pumpAndSettle();

    // The clause 13 asks for by name. Doubling the text grows the chrome row,
    // and 40 percent of 844 is 337.6, which is room enough for it: the
    // fraction still decides the extent and nothing overflows getting there.
    expect(_headerHeight(tester), closeTo(phone.height * 0.40, 0.5));
    expect(tester.takeException(), isNull);
  });

  testWidgets('the fraction is floored by the row the chrome must keep', (
    WidgetTester tester,
  ) async {
    // A short window at twice the text size: 10 percent of 400 is 40 dp, and
    // one row of controls at 2.0 is taller than that. The floor is what makes
    // "no overflow at any text scale" true rather than aspirational.
    final ScrollController controller = await _pumpScreen(
      tester,
      size: const Size(390, 400),
      scale: 2,
      maxFraction: 0.2,
      minFraction: 0.1,
      chrome: const <Widget>[Text(_chromeOne)],
    );
    controller.jumpTo(controller.position.maxScrollExtent);
    await tester.pumpAndSettle();

    expect(_headerHeight(tester), greaterThan(400 * 0.1));
    expect(tester.takeException(), isNull);
  });

  testWidgets('the chrome shrinks to one row and the last row stays put', (
    WidgetTester tester,
  ) async {
    final double pad = UiThemeData.light().space.s2;
    final ScrollController controller = await _pumpScreen(tester);
    final double restingBottom = tester.getRect(find.text(_chromeTwo)).bottom;
    expect(find.text(_chromeOne), findsOneWidget);
    expect(
      tester.getRect(find.text(_chromeOne)).bottom,
      lessThan(restingBottom),
      reason: 'the rows are drawn in the order the caller listed them',
    );
    expect(restingBottom, closeTo(_headerHeight(tester) - pad, 1));

    controller.jumpTo(controller.position.maxScrollExtent);
    await tester.pumpAndSettle();

    // The row that rides the lower edge is the one that survives, and it
    // rides that edge at both extents, so the control a reviewer is aiming
    // at is always the same distance from the bottom of the header.
    final Rect last = tester.getRect(find.text(_chromeTwo));
    expect(last.bottom, closeTo(_headerHeight(tester) - pad, 1));
    expect(
      tester
          .widget<Opacity>(
            find.ancestor(
              of: find.text(_chromeOne),
              matching: find.byType(Opacity),
            ),
          )
          .opacity,
      0,
      reason:
          'the row the collapse takes away is gone rather than clipped in '
          'half',
    );
  });

  testWidgets('the one frosted pane appears only once it is collapsed', (
    WidgetTester tester,
  ) async {
    final ScrollController controller = await _pumpScreen(tester);
    expect(find.byType(GlassSurface), findsNothing);

    controller.jumpTo(controller.position.maxScrollExtent);
    await tester.pumpAndSettle();

    // 13 section 2.2 spends the compact window's one glass pane here, and 09
    // section 11 rejects glass that fades: it is on at the threshold or it is
    // not there at all.
    expect(find.byType(GlassSurface), findsOneWidget);
  });

  testWidgets('a header that is not the region under review is chrome', (
    WidgetTester tester,
  ) async {
    await _pumpScreen(tester, primary: false);
    final Element marker = tester.element(find.byType(PinnedChrome));

    // 13 section 2.3 counts a pinned header at its collapsed height, which is
    // the extent it pins and not the extent it happens to be drawn at.
    expect(PinnedChrome.extentOf(marker), closeTo(phone.height * 0.40, 0.5));
    expect(
      tester.widget<PinnedChrome>(find.byType(PinnedChrome)).region,
      UiPinnedRegion.header,
    );
    expect(find.byType(PrimaryRegion), findsNothing);
  });

  testWidgets('the region under review is content, not chrome', (
    WidgetTester tester,
  ) async {
    final ScrollController controller = await _pumpScreen(tester);

    // No budget spent: 13 section 4.1 pins this header at 40 percent of a
    // phone and gives the whole of the chrome 28, and the rows on its edge
    // are inside the extent 13 section 2.5 measures already.
    expect(find.byType(PinnedChrome), findsNothing);

    // The fold rule reads the thing under review on its own box, at the
    // height it keeps once the header is pinned: the extent less the one
    // chrome row that survives the collapse.
    final UiThemeData ui = UiThemeData.light();
    final BuildContext context = tester.element(find.byType(CustomScrollView));
    final UiCollapsingHeaderStyle style = UiCollapsingHeaderStyle.resolve(
      ui,
      context,
    );
    final double row =
        style.chromeRowHeight +
        style.chromePadding.resolve(TextDirection.ltr).vertical;
    final Element marker = tester.element(find.byType(PrimaryRegion));
    expect(
      PrimaryRegion.minExtentOf(marker),
      closeTo(phone.height * 0.40 - row, 0.5),
    );
    expect(
      marker.renderObject,
      isA<RenderBox>(),
      reason: 'a marker around the sliver has no box for the gate to read',
    );
    final Rect atRest = tester.getRect(find.byType(PrimaryRegion));
    expect(atRest.top, 0);

    controller.jumpTo(controller.position.maxScrollExtent);
    await tester.pumpAndSettle();
    expect(
      tester.getRect(find.byType(PrimaryRegion)).height,
      closeTo(PrimaryRegion.minExtentOf(marker), 0.5),
      reason: 'pinned, the content is exactly the height the marker promises',
    );
  });

  testWidgets('tracks the scroll under reduced motion', (
    WidgetTester tester,
  ) async {
    final ScrollController controller = await _pumpScreen(
      tester,
      disableAnimations: true,
    );
    final double resting = _headerHeight(tester);

    controller.jumpTo(100);
    await tester.pump();

    // A collapse is a position and not a transition (04 section 1.5). A
    // reviewer who has asked for no motion still gets a header that follows
    // their finger, because the alternative is one frozen at whichever
    // extent the scroll started at.
    expect(_headerHeight(tester), lessThan(resting));
    expect(_headerHeight(tester), closeTo(resting - 100, 1));
  });

  testWidgets('a header with no chrome is its content', (
    WidgetTester tester,
  ) async {
    await _pumpScreen(tester, chrome: const <Widget>[]);

    expect(find.byType(GlassSurface), findsNothing);
    expect(_headerHeight(tester), closeTo(phone.height * 0.55, 0.5));
    expect(tester.takeException(), isNull);
  });

  testWidgets('right to left keeps the chrome on the lower edge', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: phone,
        textDirection: TextDirection.rtl,
        child: SizedBox.fromSize(
          size: phone,
          child: const CustomScrollView(
            slivers: <Widget>[
              UiCollapsingHeader(
                content: ColoredBox(color: Color(0xFF000000)),
                chrome: <Widget>[Text(_chromeOne)],
              ),
              SliverToBoxAdapter(child: Text(_beneath)),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      tester.getRect(find.text(_chromeOne)).bottom,
      closeTo(_headerHeight(tester) - UiThemeData.light().space.s2, 1),
    );
    expect(tester.takeException(), isNull);
  });
}
