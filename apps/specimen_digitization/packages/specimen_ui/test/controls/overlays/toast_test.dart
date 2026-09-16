// `UiToast`, `UiToastHost` and `UiToasts` (10 section 4.3).

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';

const String _first = 'Review recorded on version 4';
const String _second = 'Upload paused. The network dropped.';

/// The context inside the host, so a test raises a toast the way a screen
/// does.
late BuildContext hostContext;

Widget _host({double bottomInset = 0}) => UiToastHost(
  bottomInset: bottomInset,
  child: Builder(
    builder: (BuildContext context) {
      hostContext = context;
      return const SizedBox.expand();
    },
  ),
);

UiToastHostState get _state => UiToastHost.maybeOf(hostContext)!;

/// Makes the surface the size the window claims to be.
///
/// `uiHarness` sets `MediaQueryData.size`, which is what decides the window
/// class, but the test view keeps its own 800 by 600 surface. A geometry
/// assertion has to measure against the same rectangle the layout used.
void useWindow(WidgetTester tester, Size window) {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = window;
  addTearDown(tester.view.reset);
}

void main() {
  testWidgets('one is visible at a time and the rest wait', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _host()));
    UiToasts.show(hostContext, message: _first);
    UiToasts.show(hostContext, message: _second);
    await tester.pumpAndSettle();

    expect(find.text(_first), findsOneWidget);
    expect(find.text(_second), findsNothing);
    expect(_state.waiting, 1);

    await tester.pump(UiToastStyle.showDuration);
    await tester.pumpAndSettle();
    expect(find.text(_first), findsNothing);
    expect(find.text(_second), findsOneWidget);
    expect(_state.waiting, 0);

    await tester.pump(UiToastStyle.showDuration);
    await tester.pumpAndSettle();
    expect(find.text(_second), findsNothing);
  });

  testWidgets('a toast with an action waits for the reviewer', (
    WidgetTester tester,
  ) async {
    final List<String> taken = <String>[];
    await tester.pumpWidget(uiHarness(child: _host()));
    UiToasts.show(
      hostContext,
      message: _second,
      actionLabel: 'Retry upload',
      onAction: () => taken.add('retry'),
    );
    await tester.pumpAndSettle();
    expect(find.text(_second), findsOneWidget);

    await tester.pump(UiToastStyle.showDuration * 2);
    await tester.pumpAndSettle();
    expect(
      find.text(_second),
      findsOneWidget,
      reason: 'taking the action away after six seconds takes it away as the '
          'reviewer reaches for it',
    );

    await tester.tap(find.text('Retry upload'));
    await tester.pumpAndSettle();
    expect(taken, <String>['retry']);
    expect(find.text(_second), findsNothing);
  });

  testWidgets('the message is a live region and the action is not', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(uiHarness(child: _host()));
    UiToasts.show(
      hostContext,
      message: _first,
      actionLabel: 'Retry upload',
      onAction: () {},
    );
    await tester.pumpAndSettle();

    expect(find.byType(Announcer), findsOneWidget);
    final SemanticsData data = tester
        .getSemantics(find.byType(Announcer))
        .getSemanticsData();
    expect(data.flagsCollection.isLiveRegion, isTrue);
    expect(
      data.label,
      _first,
      reason: 'the news is read once; the action announces itself as a button',
    );
    handle.dispose();
  });

  testWidgets('it sits above the bottom edge, centred only when compact', (
    WidgetTester tester,
  ) async {
    for (final (Size window, bool compact) in <(Size, bool)>[
      (const Size(390, 844), true),
      (const Size(1180, 820), false),
    ]) {
      useWindow(tester, window);
      await tester.pumpWidget(uiHarness(size: window, child: _host()));
      UiToasts.show(hostContext, message: _first);
      await tester.pumpAndSettle();

      final Rect capsule = tester.getRect(find.byType(UiToast));
      expect(
        capsule.bottom,
        lessThan(window.height),
        reason: 'a toast is anchored above the bottom edge, never off it',
      );
      final double startGap = capsule.left;
      final double endGap = window.width - capsule.right;
      if (compact) {
        expect(
          (startGap - endGap).abs(),
          lessThan(1),
          reason: 'a compact window centres the capsule over the navigation',
        );
      } else {
        expect(
          startGap,
          lessThan(endGap),
          reason: 'a wider window anchors it to the bottom start corner',
        );
      }
      await tester.pump(UiToastStyle.showDuration);
      await tester.pumpAndSettle();
    }
  });

  testWidgets('bottomInset reserves room for the pill navigation', (
    WidgetTester tester,
  ) async {
    const Size window = Size(390, 844);
    final List<double> bottoms = <double>[];
    useWindow(tester, window);
    for (final double inset in <double>[0, 96]) {
      await tester.pumpWidget(
        uiHarness(size: window, child: _host(bottomInset: inset)),
      );
      UiToasts.show(hostContext, message: _first);
      await tester.pumpAndSettle();
      bottoms.add(tester.getRect(find.byType(UiToast)).bottom);
      await tester.pump(UiToastStyle.showDuration);
      await tester.pumpAndSettle();
    }
    expect(bottoms.first - bottoms.last, closeTo(96, 0.5));
  });

  testWidgets('the capsule is the window only frosted pane', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(uiHarness(child: _host()));
    UiToasts.show(hostContext, message: _first);
    await tester.pumpAndSettle();
    expect(glassPaneCount(), 1);
    expectGlassBudget(tester);
    await tester.pump(UiToastStyle.showDuration);
    await tester.pumpAndSettle();
  });

  testWidgets('the entrance collapses under reduced motion', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(disableAnimations: true, child: _host()),
    );
    UiToasts.show(hostContext, message: _first);
    await tester.pump();
    expect(find.text(_first), findsOneWidget);
    expect(tester.binding.transientCallbackCount, 0);
    await tester.pump(UiToastStyle.showDuration);
    await tester.pumpAndSettle();
  });

  testWidgets('it builds right to left and at 200 percent text', (
    WidgetTester tester,
  ) async {
    for (final (TextDirection direction, TextScaler scaler)
        in <(TextDirection, TextScaler)>[
          (TextDirection.rtl, TextScaler.noScaling),
          (TextDirection.ltr, const TextScaler.linear(2)),
        ]) {
      await tester.pumpWidget(
        uiHarness(
          textDirection: direction,
          textScaler: scaler,
          child: _host(),
        ),
      );
      UiToasts.show(
        hostContext,
        message: _second,
        actionLabel: 'Retry upload',
        onAction: () {},
      );
      await tester.pumpAndSettle();
      expect(find.text(_second), findsOneWidget);
    }
  });

  testWidgets('raising one with no host installed does nothing', (
    WidgetTester tester,
  ) async {
    late BuildContext bare;
    await tester.pumpWidget(
      uiHarness(
        child: Builder(
          builder: (BuildContext context) {
            bare = context;
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    UiToasts.show(bare, message: _first);
    UiToasts.dismiss(bare);
    await tester.pumpAndSettle();
    expect(find.text(_first), findsNothing);
  });

  testWidgets('the action satisfies the control contract', (
    WidgetTester tester,
  ) async {
    await expectControlContract(
      tester,
      (BuildContext context) => UiToast(
        data: UiToastData(
          message: _second,
          icon: UiIcons.syncProblem,
          actionLabel: 'Retry upload',
          onAction: () {},
        ),
      ),
      semanticsLabel: 'Retry upload',
    );
  });
}
