// The page frame (10 section 4.4, `UiScaffold`).

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';
import 'destinations.dart';

const Size _window = Size(420, 820);

Widget _page({
  Widget? topBar,
  Widget? banner,
  Widget? body,
  Widget? actionBar,
  Widget? nav,
  Widget? overlays,
  SkyPreset sky = SkyPreset.home,
  Rect? exclusion,
  EdgeInsets padding = EdgeInsets.zero,
  EdgeInsets viewInsets = EdgeInsets.zero,
  Size size = _window,
}) => Builder(
  builder: (BuildContext context) => MediaQuery(
    data: MediaQuery.of(
      context,
    ).copyWith(size: size, padding: padding, viewInsets: viewInsets),
    child: SizedBox.fromSize(
      size: size,
      child: UiScaffold(
        topBar: topBar,
        banner: banner,
        body: body,
        actionBar: actionBar,
        nav: nav,
        overlays: overlays,
        sky: sky,
        exclusion: exclusion,
      ),
    ),
  ),
);

Widget _pill() => UiPillNav(
  destinations: threeDestinations,
  currentIndex: 0,
  onSelect: (int _) {},
);

/// A body that takes whatever it is given, so a test can measure what that is.
class _MeasuredBody extends StatelessWidget {
  const _MeasuredBody();

  @override
  Widget build(BuildContext context) => const SizedBox.expand();
}

Widget _scrollingBody() => ListView.builder(
  itemCount: 40,
  itemBuilder: (BuildContext context, int index) =>
      SizedBox(height: 60, child: Text('Row $index')),
);

void main() {
  testWidgets('it paints the ground and the sky it is given', (
    WidgetTester tester,
  ) async {
    const Rect matte = Rect.fromLTWH(20, 100, 300, 400);
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(sky: SkyPreset.work, exclusion: matte, body: const Text('Body')),
      ),
    );
    await tester.pumpAndSettle();
    final FieldLayer layer = tester.widget<FieldLayer>(find.byType(FieldLayer));
    expect(layer.preset, SkyPreset.work);
    expect(layer.exclusion, matte);
  });

  testWidgets('the body learns what the chrome at the bottom occupies', (
    WidgetTester tester,
  ) async {
    late double inset;
    late double expected;
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          padding: const EdgeInsets.only(bottom: 34),
          nav: _pill(),
          body: Builder(
            builder: (BuildContext context) {
              inset = UiScaffold.of(context).bottomInset;
              expected =
                  34 +
                  UiScaffoldStyle.resolve(context.ui).gap +
                  UiPillNav.heightOf(context);
              return const SizedBox.expand();
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(inset, expected);
  });

  testWidgets('the action bar is counted in the inset too', (
    WidgetTester tester,
  ) async {
    late double withoutBar;
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          nav: _pill(),
          body: Builder(
            builder: (BuildContext context) {
              withoutBar = UiScaffold.of(context).bottomInset;
              return const SizedBox.expand();
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    late double withBar;
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          nav: _pill(),
          actionBar: const SizedBox(height: 40, child: Text('Approve record')),
          body: Builder(
            builder: (BuildContext context) {
              withBar = UiScaffold.of(context).bottomInset;
              return const SizedBox.expand();
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      withBar,
      greaterThan(withoutBar),
      reason:
          'the frame measures what it floats rather than guessing it, so a '
          'body padded by the inset clears the action bar as well as the pill',
    );
  });

  testWidgets('the pill sits 16 dp above the bottom safe area', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          padding: const EdgeInsets.only(bottom: 34),
          nav: _pill(),
          body: const SizedBox.expand(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final double frameBottom = tester.getRect(find.byType(UiScaffold)).bottom;
    final double pillBottom = tester.getRect(find.byType(UiPillNav)).bottom;
    final BuildContext context = tester.element(find.byType(UiPillNav));
    expect(frameBottom - pillBottom, 34 + UiPillNav.gapOf(context));
  });

  testWidgets('the keyboard replaces the safe area rather than adding to it', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          padding: const EdgeInsets.only(bottom: 34),
          viewInsets: const EdgeInsets.only(bottom: 300),
          nav: _pill(),
          body: const SizedBox.expand(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final double frameBottom = tester.getRect(find.byType(UiScaffold)).bottom;
    final double pillBottom = tester.getRect(find.byType(UiPillNav)).bottom;
    final BuildContext context = tester.element(find.byType(UiPillNav));
    expect(
      frameBottom - pillBottom,
      300 + UiPillNav.gapOf(context),
      reason: 'the keyboard covers the home indicator, so they do not add up',
    );
  });

  testWidgets('the action bar sits above the navigation', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          nav: _pill(),
          actionBar: const Text('Approve record'),
          body: const SizedBox.expand(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getRect(find.text('Approve record')).bottom,
      lessThan(tester.getRect(find.byType(UiPillNav)).top),
    );
    expect(
      tester
          .widget<GlassSurface>(
            find
                .ancestor(
                  of: find.text('Approve record'),
                  matching: find.byType(GlassSurface),
                )
                .first,
          )
          .level,
      GlassLevel.floating,
    );
  });

  testWidgets('the top bar fills once the body has scrolled under it', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          topBar: const UiTopBar(title: 'Queue'),
          body: _scrollingBody(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 0);

    await tester.drag(find.byType(ListView), const Offset(0, -200));
    await tester.pumpAndSettle();
    expect(
      glassPaneCount(),
      1,
      reason: 'the bar takes its glass.flat fill from the body scrolling',
    );

    await tester.drag(find.byType(ListView), const Offset(0, 400));
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 0, reason: 'and gives it back at the top');
  });

  testWidgets('a rail sits beside the body and a pill floats over it', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: const Size(900, 700),
        child: _page(
          size: const Size(900, 700),
          nav: UiRail(
            destinations: threeDestinations,
            currentIndex: 0,
            onSelect: (int _) {},
          ),
          body: const SizedBox.expand(child: Text('Body')),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getRect(find.byType(UiRail)).right,
      lessThanOrEqualTo(tester.getRect(find.text('Body')).left),
    );

    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          nav: _pill(),
          body: const SizedBox.expand(key: ValueKey<String>('body')),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final Rect body = tester.getRect(find.byKey(const ValueKey<String>('body')));
    final Rect pill = tester.getRect(find.byType(UiPillNav));
    expect(
      body.contains(pill.topLeft) && body.contains(pill.bottomRight),
      isTrue,
      reason:
          'a floating pill is over the body, so the body keeps its full '
          'height and pads its content with the published inset instead',
    );
  });

  testWidgets('a sidebar is placed beside the body too', (
    WidgetTester tester,
  ) async {
    expect(
      UiScaffold.placementOf(
        UiSidebar(
          destinations: threeDestinations,
          currentIndex: 0,
          onSelect: (int _) {},
        ),
      ),
      UiNavPlacement.beside,
    );
    expect(UiScaffold.placementOf(_pill()), UiNavPlacement.floating);
    expect(UiScaffold.placementOf(null), UiNavPlacement.floating);

    await tester.pumpWidget(
      uiHarness(
        size: const Size(1280, 800),
        child: _page(
          size: const Size(1280, 800),
          nav: UiSidebar(
            destinations: threeDestinations,
            currentIndex: 0,
            onSelect: (int _) {},
          ),
          body: const SizedBox.expand(child: Text('Body')),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getRect(find.byType(UiSidebar)).right,
      lessThanOrEqualTo(tester.getRect(find.text('Body')).left),
    );
  });

  testWidgets('overlays sit over the body and under the navigation', (
    WidgetTester tester,
  ) async {
    int bodyTaps = 0;
    int overlayTaps = 0;
    int navSelections = 0;
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          nav: UiPillNav(
            destinations: threeDestinations,
            currentIndex: 0,
            onSelect: (int _) => navSelections++,
          ),
          body: GestureDetector(
            onTap: () => bodyTaps++,
            behavior: HitTestBehavior.opaque,
            child: const SizedBox.expand(),
          ),
          overlays: GestureDetector(
            onTap: () => overlayTaps++,
            behavior: HitTestBehavior.opaque,
            child: const SizedBox.expand(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tapAt(const Offset(200, 200));
    await tester.pumpAndSettle();
    expect(overlayTaps, 1);
    expect(bodyTaps, 0, reason: 'the overlay is over the body');

    await tester.tap(find.bySemanticsLabel('Intake'));
    await tester.pumpAndSettle();
    expect(navSelections, 1, reason: 'the navigation is over the overlay');
    expect(overlayTaps, 1);
  });

  testWidgets('a full page holds the glass budget', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          topBar: const UiTopBar(title: 'Queue'),
          actionBar: const Text('Approve record'),
          nav: _pill(),
          body: _scrollingBody(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView), const Offset(0, -200));
    await tester.pumpAndSettle();
    expect(
      glassPaneCount(),
      3,
      reason: 'a top bar, an action bar and a pill are three panes',
    );
    expectGlassBudget(tester, window: 'a scrolled page with every slot');
  });

  testWidgets('the banner sits between the top bar and the body', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          topBar: const UiTopBar(title: 'Queue'),
          banner: const Text('This is the test environment'),
          body: const Text('Body'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getRect(find.text('This is the test environment')).top,
      greaterThanOrEqualTo(tester.getRect(find.text('Queue')).bottom),
    );
    expect(
      tester.getRect(find.text('This is the test environment')).bottom,
      lessThanOrEqualTo(tester.getRect(find.text('Body')).top),
    );
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        textDirection: TextDirection.rtl,
        textScaler: const TextScaler.linear(2),
        child: _page(
          topBar: const UiTopBar(title: 'Queue'),
          nav: _pill(),
          actionBar: const Text('Approve record'),
          body: const Text('Body'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(UiScaffold), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a scaffold hosts toasts, so UiToasts.show needs no ceremony', (
    WidgetTester tester,
  ) async {
    late BuildContext inside;
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          nav: _pill(),
          body: Builder(
            builder: (BuildContext context) {
              inside = context;
              return const SizedBox.expand();
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      UiToastHost.maybeOf(inside),
      isNotNull,
      reason: 'the frame installs the layer every page wants',
    );

    UiToasts.show(inside, message: 'Review recorded on version 4');
    await tester.pumpAndSettle();
    expect(find.text('Review recorded on version 4'), findsOneWidget);

    // The toast clears the pill rather than sitting over it, because the host
    // is given the same inset the body pads itself by.
    expect(
      tester.getRect(find.byType(UiToast)).bottom,
      lessThanOrEqualTo(tester.getRect(find.byType(UiPillNav)).top),
    );
  });

  testWidgets('a caller that passes its own overlays gets no toast layer', (
    WidgetTester tester,
  ) async {
    late BuildContext inside;
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          overlays: const SizedBox.shrink(),
          body: Builder(
            builder: (BuildContext context) {
              inside = context;
              return const SizedBox.expand();
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      UiToastHost.maybeOf(inside),
      isNull,
      reason: 'whatever the caller passes replaces the default',
    );
    UiToasts.show(inside, message: 'Review recorded on version 4');
    await tester.pumpAndSettle();
    expect(
      find.text('Review recorded on version 4'),
      findsNothing,
      reason:
          'a missing toast layer is not a reason to fail a review, so the '
          'call is silently dropped rather than throwing',
    );
  });

  testWidgets('the body is laid out against the frame, host or no host', (
    WidgetTester tester,
  ) async {
    for (final Widget? overlays in <Widget?>[null, const SizedBox.shrink()]) {
      await tester.pumpWidget(
        uiHarness(
          size: _window,
          child: _page(
            overlays: overlays,
            body: const _MeasuredBody(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.getSize(find.byType(_MeasuredBody)).width,
        _window.width,
        reason:
            'the toast host passes the frame constraints through rather than '
            'loosening them under the page',
      );
    }
  });

  for (final UiNavDestination destination in threeDestinations) {
    testWidgets('control contract in a frame: ${destination.label}', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        // The bar's title is not a destination's label here, so the finder
        // the contract uses resolves to the disc rather than to two nodes
        // that happen to read the same.
        (BuildContext context) => _page(
          topBar: const UiTopBar(title: 'Review desk'),
          nav: _pill(),
          body: const SizedBox.expand(),
        ),
        semanticsLabel: destination.label,
      );
    });
  }
}
