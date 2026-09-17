// The composition markers (13 section 5).
//
// These are what the composition gates read, so what is pinned here is what
// slot A4 relies on: a marker costs nothing in the render tree, the height it
// reports is the box under it or the extent it declares, and a marker that
// can report neither says so rather than measuring zero.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../harness/control_contract.dart';

/// The element of the one marker of [T] on screen.
Element _marker<T extends Widget>(WidgetTester tester) =>
    tester.element(find.byType(T));

void main() {
  group('PinnedChrome', () {
    testWidgets('adds no render object of its own', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: const PinnedChrome(
            region: UiPinnedRegion.topBar,
            child: SizedBox(key: Key('bar'), width: 200, height: 56),
          ),
        ),
      );

      // The marker's element resolves to the child's box, which is what makes
      // it free: one element, no render object, and a gate that finds it by
      // type still reads a real rectangle.
      final Element element = _marker<PinnedChrome>(tester);
      expect(element.renderObject, isA<RenderBox>());
      expect(
        element.renderObject,
        same(tester.renderObject(find.byKey(const Key('bar')))),
      );
    });

    testWidgets('measures the box under it when it declares no extent', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: const PinnedChrome(
            region: UiPinnedRegion.band,
            child: SizedBox(width: 300, height: 32),
          ),
        ),
      );

      expect(PinnedChrome.extentOf(_marker<PinnedChrome>(tester)), 32);
    });

    testWidgets('reports the extent it declares over the box it has', (
      WidgetTester tester,
    ) async {
      // A collapsing header's box is its current extent; what it pins is the
      // minimum. The declared extent is the answer the budget wants.
      await tester.pumpWidget(
        uiHarness(
          child: const PinnedChrome(
            region: UiPinnedRegion.header,
            extent: 338,
            child: SizedBox(width: 390, height: 464),
          ),
        ),
      );

      expect(PinnedChrome.extentOf(_marker<PinnedChrome>(tester)), 338);
    });

    testWidgets('names itself when it has neither a box nor an extent', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        uiHarness(
          child: const CustomScrollView(
            slivers: <Widget>[
              PinnedChrome(
                region: UiPinnedRegion.header,
                child: SliverToBoxAdapter(child: SizedBox(height: 100)),
              ),
            ],
          ),
        ),
      );

      expect(
        () => PinnedChrome.extentOf(_marker<PinnedChrome>(tester)),
        throwsA(
          isA<FlutterError>().having(
            (FlutterError error) => error.message,
            'message',
            contains('header'),
          ),
        ),
      );
    });
  });

  group('PrimaryRegion', () {
    testWidgets('measures the box under it', (WidgetTester tester) async {
      await tester.pumpWidget(
        uiHarness(
          child: const PrimaryRegion(child: SizedBox(width: 390, height: 464)),
        ),
      );

      final Element element = _marker<PrimaryRegion>(tester);
      expect(element.renderObject, isA<RenderBox>());
      expect(PrimaryRegion.minExtentOf(element), 464);
    });

    testWidgets('reports the minimum it declares', (WidgetTester tester) async {
      await tester.pumpWidget(
        uiHarness(
          child: const PrimaryRegion(
            minExtent: 338,
            child: SizedBox(width: 390, height: 464),
          ),
        ),
      );

      expect(PrimaryRegion.minExtentOf(_marker<PrimaryRegion>(tester)), 338);
    });
  });
}
