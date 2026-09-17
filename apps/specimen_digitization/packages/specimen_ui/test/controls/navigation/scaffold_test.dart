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

/// A page that publishes what it wants of the frame, the way a routed screen
/// does (13 section 3.4).
class _SlotPublisher extends StatefulWidget {
  const _SlotPublisher({
    super.key,
    this.actionBar,
    this.navVisible,
    this.bandCompact,
  });

  final Widget? actionBar;
  final bool? navVisible;
  final bool? bandCompact;

  @override
  State<_SlotPublisher> createState() => _SlotPublisherState();
}

class _SlotPublisherState extends State<_SlotPublisher> {
  UiScaffoldSlots? _slots;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _slots = UiScaffoldSlots.of(context)
      ?..setActionBar(widget.actionBar, owner: this)
      ..setNavVisible(widget.navVisible, owner: this)
      ..setBandCompact(widget.bandCompact, owner: this);
  }

  @override
  void dispose() {
    _slots?.release(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => const SizedBox.expand();
}

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

/// A page that asks for a rectangle to be kept clear, the way a source pane
/// asks for the band around its photograph.
class _Publisher extends StatefulWidget {
  const _Publisher({required this.rect});

  final Rect rect;

  @override
  State<_Publisher> createState() => _PublisherState();
}

class _PublisherState extends State<_Publisher> {
  @override
  Widget build(BuildContext context) {
    UiScaffoldExclusion.of(context)?.publish(widget.rect);
    return const SizedBox.expand();
  }
}

void main() {
  testWidgets('a page can ask the field layer to keep a rectangle clear', (
    WidgetTester tester,
  ) async {
    const Rect matte = Rect.fromLTWH(24, 96, 320, 420);
    await tester.pumpWidget(
      uiHarness(
        child: _page(body: const _Publisher(rect: matte)),
      ),
    );
    // The rectangle is reported during the body's build, so it reaches the
    // frame on the next one.
    await tester.pumpAndSettle();
    expect(
      tester.widget<FieldLayer>(find.byType(FieldLayer)).exclusion,
      matte,
      reason:
          'UiScaffold.exclusion is a constructor argument and the frame is '
          'built by the shell, which does not know where the photograph is; '
          'the screen that does says so through the scope',
    );
  });

  testWidgets('what the page asks for wins over what the caller passed', (
    WidgetTester tester,
  ) async {
    const Rect fromCaller = Rect.fromLTWH(0, 0, 10, 10);
    const Rect fromPage = Rect.fromLTWH(24, 96, 320, 420);
    await tester.pumpWidget(
      uiHarness(
        child: _page(
          exclusion: fromCaller,
          body: const _Publisher(rect: fromPage),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.widget<FieldLayer>(find.byType(FieldLayer)).exclusion,
      fromPage,
    );
  });

  testWidgets('publishing outside a scaffold is a no op', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _Publisher(rect: Rect.fromLTWH(0, 0, 4, 4))),
    );
    await tester.pumpAndSettle();
    expect(
      tester.takeException(),
      isNull,
      reason:
          'a component test that pumps a pane on its own has no frame above '
          'it, and a publisher should not need a branch for that',
    );
  });

  testWidgets('it paints the ground and the sky it is given', (
    WidgetTester tester,
  ) async {
    const Rect matte = Rect.fromLTWH(20, 100, 300, 400);
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          sky: SkyPreset.work,
          exclusion: matte,
          body: const Text('Body'),
        ),
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
    // A medium window, because at compact the frame spends the window's one
    // pane on its floating chrome and the bar's fill is the solid form of the
    // same surface; what this test is about is the threshold, which is the
    // same at every class.
    const Size window = Size(700, 900);
    await tester.pumpWidget(
      uiHarness(
        size: window,
        child: _page(
          size: window,
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
    final Rect body = tester.getRect(
      find.byKey(const ValueKey<String>('body')),
    );
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
    const Size window = Size(1000, 900);
    await tester.pumpWidget(
      uiHarness(
        size: window,
        child: _page(
          size: window,
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
      reason:
          'a top bar, an action bar and a pill are three panes at a class '
          'whose budget is three',
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
          child: _page(overlays: overlays, body: const _MeasuredBody()),
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
        labelsNeverWrap: true,
        geometryFromType: true,
        fit: FitExpectation(
          check: (WidgetTester tester, double width) async {
            expect(
              find.bySemanticsLabel(destination.label),
              findsOneWidget,
              reason: 'the frame keeps its navigation reachable at $width dp',
            );
          },
        ),
      );
    });
  }

  group('the routed screen fills the frame (13 section 3.4)', () {
    testWidgets('a page publishes its own action bar', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: _window,
          child: _page(
            body: const _SlotPublisher(actionBar: Text('Clear record')),
            nav: _pill(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Clear record'), findsOneWidget);
      expect(
        tester
            .widget<PinnedChrome>(
              find.ancestor(
                of: find.text('Clear record'),
                matching: find.byType(PinnedChrome),
              ),
            )
            .region,
        UiPinnedRegion.actionBar,
        reason:
            'the frame marks what it pins, so a screen marks only its '
            'primary region',
      );
    });

    testWidgets('what the page asks for wins over what the caller passed', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: _window,
          child: _page(
            actionBar: const Text('From the shell'),
            body: const _SlotPublisher(actionBar: Text('From the screen')),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('From the screen'), findsOneWidget);
      expect(find.text('From the shell'), findsNothing);
    });

    testWidgets('a record hides the pill and keeps its state', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: _window,
          child: _page(body: const SizedBox.expand(), nav: _pill()),
        ),
      );
      await tester.pumpAndSettle();
      final double shown = tester.getSize(find.byType(UiPillNav)).height;
      expect(shown, greaterThan(0));

      await tester.pumpWidget(
        uiHarness(
          size: _window,
          child: _page(
            body: const _SlotPublisher(navVisible: false),
            nav: _pill(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Hidden rather than removed: the pill keeps the destination it was on,
      // and takes no height, so the chrome budget counts it at nothing.
      expect(find.byType(UiPillNav), findsNothing);
      expect(
        find.byType(UiPillNav, skipOffstage: false),
        findsOneWidget,
        reason:
            'a pill taken out of the tree glides in from the first '
            'destination when the reviewer leaves the record',
      );
      expect(
        PinnedChrome.extentOf(
          tester.element(
            find.byWidgetPredicate(
              (Widget widget) =>
                  widget is PinnedChrome &&
                  widget.region == UiPinnedRegion.navigation,
            ),
          ),
        ),
        0,
        reason:
            'the region it holds is nothing, whatever the pill inside it '
            'still measures',
      );
    });

    testWidgets('a record\'s ask hides the pill and not a sidebar', (
      WidgetTester tester,
    ) async {
      // 13 section 2.3: the pill hides inside a record because the way out is
      // the bar's back. A sidebar is a column beside the body and the only
      // navigation a desktop has, so the same ask leaves it in place.
      await tester.pumpWidget(
        uiHarness(
          size: const Size(1440, 900),
          child: _page(
            body: const _SlotPublisher(navVisible: false),
            nav: UiSidebar(
              destinations: threeDestinations,
              currentIndex: 0,
              onSelect: (int _) {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final Offstage offstage = tester.widget<Offstage>(
        find
            .ancestor(
              of: find.byType(UiSidebar),
              matching: find.byType(Offstage),
            )
            .first,
      );
      expect(offstage.offstage, isFalse);
    });

    testWidgets('a hidden pill leaves no gap under the action bar', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: _window,
          child: _page(
            body: const _SlotPublisher(
              actionBar: SizedBox(height: 48),
              navVisible: false,
            ),
            nav: _pill(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final Element marker = tester.element(
        find.byWidgetPredicate(
          (Widget widget) =>
              widget is PinnedChrome &&
              widget.region == UiPinnedRegion.navigation,
        ),
      );
      expect(PinnedChrome.extentOf(marker), 0);
    });

    testWidgets('a page asks its band for the one line form', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: _window,
          child: _page(
            banner: const UiBanner(
              message: 'Test environment. Not approved museum records.',
              tone: UiBannerTone.synthetic,
              detail: 'Each reading names the model that produced it.',
              sheetTitle: 'About this build',
            ),
            body: const _SlotPublisher(bandCompact: true),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.bySemanticsLabel(UiBanner.defaultDetailLabel),
        findsNothing,
        reason:
            'the strip keeps its detail behind a tap rather than behind a '
            'chevron (13 section 2.3)',
      );
      expect(tester.getSize(find.byType(UiBanner)).height, UiDensity.hitBox);
    });

    testWidgets('the frame marks the top bar and the band it pins', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: _window,
          child: _page(
            topBar: const UiTopBar(title: 'Queue'),
            banner: const UiBanner(message: 'Test environment'),
            body: const SizedBox.expand(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final Set<UiPinnedRegion> marked = tester
          .widgetList<PinnedChrome>(find.byType(PinnedChrome))
          .map((PinnedChrome marker) => marker.region)
          .toSet();
      expect(
        marked,
        containsAll(<UiPinnedRegion>[
          UiPinnedRegion.topBar,
          UiPinnedRegion.band,
        ]),
      );
    });

    testWidgets('a page with no scaffold above it publishes nothing', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(uiHarness(child: const _SlotPublisher()));
      await tester.pumpAndSettle();

      // Null outside a frame, the way the exclusion is, so a publisher is one
      // call with no branch and a component test pumping one screen on its
      // own is the normal case rather than an error.
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets('a screen giving a slot back leaves another screen\'s in place', (
    WidgetTester tester,
  ) async {
    // The queue stays mounted under the record pushed over it, and on the
    // route change it gives back the bulk bar it no longer needs with a null
    // that names itself. The record's decision bar arrived one frame earlier
    // and is somebody else's: a null from a caller that does not hold the
    // slot is not a release.
    final UiScaffoldSlots slots = UiScaffoldSlots();
    final Object record = Object();
    final Object queue = Object();
    const Widget decision = Text('Clear record');
    slots
      ..setTopBar(const Text('FMNH-0001'), owner: record)
      ..setActionBar(decision, owner: record)
      ..setNavVisible(false, owner: record)
      ..setBandCompact(true, owner: record);

    slots
      ..setTopBar(null, owner: queue)
      ..setActionBar(null, owner: queue)
      ..setNavVisible(null, owner: queue)
      ..setBandCompact(null, owner: queue);
    expect(slots.actionBar, same(decision));
    expect(slots.topBar, isNotNull);
    expect(slots.navVisible, isFalse);
    expect(slots.bandCompact, isTrue);

    // The holder gives back what it holds, and a caller naming no one, which
    // is what release itself is, gives the slot back outright.
    slots.setActionBar(null, owner: record);
    expect(slots.actionBar, isNull);
    slots.setTopBar(null);
    expect(slots.topBar, isNull);
    slots.release(record);
    expect(slots.navVisible, isNull);
    expect(slots.bandCompact, isNull);
    slots.dispose();
  });

  testWidgets('a screen leaving keeps the screen arriving in the action bar', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          body: const _SlotPublisher(
            key: ValueKey<String>('first'),
            actionBar: Text('From the first screen'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('From the first screen'), findsOneWidget);

    // A router builds the screen arriving before it disposes the screen
    // leaving. A screen that cleared the slots outright on the way out would
    // take the next screen's decision bar with it, which is what the owner
    // makes safe.
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        child: _page(
          body: const _SlotPublisher(
            key: ValueKey<String>('second'),
            actionBar: Text('From the second screen'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('From the second screen'), findsOneWidget);
    expect(find.text('From the first screen'), findsNothing);
  });

  testWidgets('nothing the frame reads off a route animates', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        size: _window,
        disableAnimations: true,
        child: _page(body: const SizedBox.expand(), nav: _pill()),
      ),
    );
    await tester.pumpAndSettle();

    await tester.pumpWidget(
      uiHarness(
        size: _window,
        disableAnimations: true,
        child: _page(
          body: const _SlotPublisher(
            actionBar: Text('Clear record'),
            navVisible: false,
            bandCompact: true,
          ),
          nav: _pill(),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();

    // A bar arriving, a pill leaving and a band changing form are all layout
    // and none of them is a transition: a reviewer who has asked for no
    // motion sees the new frame and not a frame on its way there
    // (13 section 3.4; 04 section 2.5).
    expect(tester.binding.transientCallbackCount, 0);
    expect(find.text('Clear record'), findsOneWidget);
  });

  group('the compact window spends one frosted pane (13 section 2.2)', () {
    testWidgets('the action bar has it and everything else draws solid', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: _page(
            size: const Size(390, 844),
            topBar: const UiTopBar(title: 'CAS 118402'),
            banner: const UiBanner(message: 'Test environment'),
            actionBar: const Text('Clear record'),
            body: _scrollingBody(),
            nav: _pill(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.drag(find.byType(ListView), const Offset(0, -200));
      await tester.pumpAndSettle();

      // Scrolled under, which is when the top bar used to add a second pane
      // that the budget never saw because it counted at rest.
      expect(
        UiScaffold.of(tester.element(find.byType(ListView))).scrolledUnder,
        isTrue,
      );
      expect(
        glassPaneCount(),
        1,
        reason:
            'a phone draws the one pane the frame gives its floating '
            'chrome and nothing else',
      );
    });

    testWidgets('a window with no action bar spends it on the navigation', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: _page(
            size: const Size(390, 844),
            topBar: const UiTopBar(title: 'Queue'),
            body: _scrollingBody(),
            nav: _pill(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.drag(find.byType(ListView), const Offset(0, -200));
      await tester.pumpAndSettle();

      // A pill is the only thing floating over the page on a list screen, so
      // it keeps its capsule rather than losing it to a bar that is not there.
      expect(glassPaneCount(), 1);
    });

    testWidgets('a collapsed header inside the frame draws solid at compact', (
      WidgetTester tester,
    ) async {
      final ScrollController controller = ScrollController();
      addTearDown(controller.dispose);
      await tester.pumpWidget(
        uiHarness(
          size: const Size(390, 844),
          child: _page(
            size: const Size(390, 844),
            topBar: const UiTopBar(title: 'CAS 118402'),
            actionBar: const Text('Clear record'),
            nav: _pill(),
            body: CustomScrollView(
              controller: controller,
              slivers: <Widget>[
                const UiCollapsingHeader(
                  content: ColoredBox(color: Color(0xFF000000)),
                  chrome: <Widget>[Text('Labels')],
                ),
                SliverList.builder(
                  itemCount: 20,
                  itemBuilder: (BuildContext context, int index) =>
                      const SizedBox(height: 80),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      controller.jumpTo(controller.position.maxScrollExtent);
      await tester.pumpAndSettle();

      // The header still draws the pane 13 section 3.1 gives it; at compact
      // the frame turns the blur off inside itself, so the band is the solid
      // form of the same surface rather than a second save layer.
      expect(find.byType(GlassSurface), findsWidgets);
      expect(glassPaneCount(), 1);
    });

    testWidgets('a medium window keeps the panes it had', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          size: const Size(700, 900),
          child: _page(
            size: const Size(700, 900),
            topBar: const UiTopBar(title: 'Queue'),
            actionBar: const Text('Clear record'),
            body: _scrollingBody(),
            nav: _pill(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.drag(find.byType(ListView), const Offset(0, -200));
      await tester.pumpAndSettle();

      expect(
        glassPaneCount(),
        greaterThan(1),
        reason:
            'the rule is the compact budget of 09 section 3.3, not a ban '
            'on frosted glass',
      );
    });
  });
}
