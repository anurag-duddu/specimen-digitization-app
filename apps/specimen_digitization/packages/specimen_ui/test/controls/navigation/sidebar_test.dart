// The navigation sidebar (10 section 4.4, `UiSidebar`).

import 'dart:ui' show Tristate;

import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:specimen_ui/testing.dart';

import '../../harness/control_contract.dart';
import 'destinations.dart';

class _SidebarHost extends StatefulWidget {
  const _SidebarHost({
    required this.destinations,
    this.onSelect,
    this.header,
    this.footer,
  });

  final List<UiNavDestination> destinations;
  final ValueChanged<int>? onSelect;
  final Widget? header;
  final Widget? footer;

  @override
  State<_SidebarHost> createState() => _SidebarHostState();
}

class _SidebarHostState extends State<_SidebarHost> {
  int _current = 0;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 600,
    child: UiSidebar(
      destinations: widget.destinations,
      currentIndex: _current,
      header: widget.header,
      footer: widget.footer,
      onSelect: (int index) {
        widget.onSelect?.call(index);
        setState(() => _current = index);
      },
    ),
  );
}

/// Selection surface, distinct from the independent keyboard focus ring.
BoxDecoration _surface(WidgetTester tester, String label) =>
    tester
            .widget<DecoratedBox>(
              find
                  .descendant(
                    of: find.bySemanticsLabel(label),
                    matching: find.byWidgetPredicate(
                      (Widget widget) =>
                          widget is DecoratedBox &&
                          widget.decoration is BoxDecoration,
                    ),
                  )
                  .first,
            )
            .decoration
        as BoxDecoration;

/// The glyph of the row labelled [label].
IconData _glyph(WidgetTester tester, String label) => tester
    .widget<Icon>(
      find
          .descendant(
            of: find.bySemanticsLabel(label),
            matching: find.byType(Icon),
          )
          .first,
    )
    .icon!;

/// Evaluates the actual flat paint chain of a sidebar label, not token pairs.
///
/// Flutter's pixel-histogram guideline can mistake the most frequent
/// antialiased edge for the text colour (Linux rendered Sources as #B9B9BC
/// in that histogram although its paragraph ink is #494950). WCAG 1.4.3
/// evaluates foreground/background colours before font antialiasing:
/// https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
///
/// Read the resolved paragraph style, composite every solid fill beneath it,
/// and apply actual ancestor render opacity to both ink and backdrop. This
/// deliberately supports the sidebar's flat surfaces only, and rejects
/// effects whose paint cannot be measured by this bounded helper.
double _paintedTextContrast(WidgetTester tester, Finder label) {
  final element = label.evaluate().single;
  final paragraph = tester.renderObject<RenderParagraph>(label);
  final span = paragraph.text as TextSpan;
  final style = span.style!;
  if ((span.children?.isNotEmpty ?? false) ||
      style.foreground != null ||
      style.background != null ||
      style.backgroundColor != null) {
    throw StateError('Contrast measurement requires one solid text style.');
  }
  var foreground = style.color!;
  var background = const Color(0x00000000);

  void under(Color color) {
    foreground = Color.alphaBlend(foreground, color);
    background = Color.alphaBlend(background, color);
  }

  element.visitAncestorElements((ancestor) {
    if (ancestor is! RenderObjectElement) return true;
    final render = ancestor.renderObject;
    if (render is RenderDecoratedBox) {
      final decoration = render.decoration;
      if (decoration is! BoxDecoration ||
          decoration.gradient != null ||
          decoration.image != null ||
          decoration.backgroundBlendMode != null ||
          (decoration.boxShadow?.isNotEmpty ?? false) ||
          render.position != DecorationPosition.background) {
        throw StateError('Contrast measurement requires solid backgrounds.');
      }
      if (decoration.color case final color?) under(color);
    } else if (ancestor.widget case ColoredBox(:final color)) {
      under(color);
    } else if (render is RenderOpacity || render is RenderAnimatedOpacity) {
      final opacity = render is RenderOpacity
          ? render.opacity
          : (render as RenderAnimatedOpacity).opacity.value;
      foreground = foreground.withValues(alpha: foreground.a * opacity);
      background = background.withValues(alpha: background.a * opacity);
    } else if (render is RenderShaderMask ||
        render is RenderBackdropFilter ||
        ancestor.widget is ColorFiltered ||
        ancestor.widget is ImageFiltered) {
      throw StateError('Contrast measurement cannot resolve paint filters.');
    }
    return true;
  });
  if (foreground.a != 1 || background.a != 1) {
    throw StateError(
      'Contrast measurement requires an opaque painted backing.',
    );
  }
  final inkLuminance = foreground.computeLuminance();
  final backgroundLuminance = background.computeLuminance();
  return inkLuminance > backgroundLuminance
      ? (inkLuminance + .05) / (backgroundLuminance + .05)
      : (backgroundLuminance + .05) / (inkLuminance + .05);
}

void main() {
  for (final brightness in Brightness.values) {
    testWidgets('navigation text meets AA contrast in ${brightness.name}', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      try {
        await tester.pumpWidget(
          uiHarness(
            brightness: brightness,
            child: const _SidebarHost(destinations: threeDestinations),
          ),
        );
        await tester.pumpAndSettle();
        for (final selected in threeDestinations) {
          await tester.tap(find.bySemanticsLabel(selected.label));
          await tester.pumpAndSettle();
          for (final destination in threeDestinations) {
            final label = find.text(destination.label);
            expect(label.hitTestable(), findsOneWidget);
            expect(
              _paintedTextContrast(tester, label),
              greaterThanOrEqualTo(4.5),
              reason:
                  '${destination.label} must retain AA body-text contrast in '
                  '${brightness.name}, with ${selected.label} selected',
            );
          }
        }
      } finally {
        semantics.dispose();
      }
    });
  }

  testWidgets('contrast measurement catches ink, surface and opacity defects', (
    tester,
  ) async {
    const black = Color(0xFF000000);
    const white = Color(0xFFFFFFFF);
    const grey = Color(0xFF999999);
    for (final sample in [
      (ink: black, surface: white, opacity: 1.0, passes: true),
      (ink: grey, surface: white, opacity: 1.0, passes: false),
      (ink: black, surface: black, opacity: 1.0, passes: false),
      (ink: black, surface: white, opacity: .2, passes: false),
    ]) {
      await tester.pumpWidget(
        uiHarness(
          child: ColoredBox(
            color: white,
            child: Opacity(
              opacity: sample.opacity,
              child: DecoratedBox(
                decoration: BoxDecoration(color: sample.surface),
                child: Text(
                  'Contrast sample',
                  style: TextStyle(color: sample.ink, fontSize: 15),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      final ratio = _paintedTextContrast(tester, find.text('Contrast sample'));
      expect(
        ratio,
        sample.passes ? greaterThanOrEqualTo(4.5) : lessThan(4.5),
        reason: '$sample',
      );
    }
  });

  testWidgets('a pointer selects the row it lands on', (
    WidgetTester tester,
  ) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        child: _SidebarHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Intake'));
    await tester.pumpAndSettle();
    expect(selected, <int>[1]);
  });

  testWidgets('down and up move, Enter selects', (WidgetTester tester) async {
    final List<int> selected = <int>[];
    await tester.pumpWidget(
      uiHarness(
        child: _SidebarHost(
          destinations: threeDestinations,
          onSelect: selected.add,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(selected, <int>[1]);
  });

  testWidgets('the pane is flat and scales its label measure with text', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _SidebarHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    final normalWidth = tester.getSize(find.byType(UiSidebar)).width;
    expect(normalWidth, lessThan(280));
    expect(glassPaneCount(), 0);
    expect(find.byType(GlassSurface), findsNothing);
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: const _SidebarHost(destinations: threeDestinations),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.byType(UiSidebar)).width,
      greaterThan(normalWidth),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('selection is a quiet fill and weight without a stripe or jump', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _SidebarHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    expect(_surface(tester, 'Queue').color, isNotNull);
    expect(_surface(tester, 'Queue').border, isNull);
    expect(_surface(tester, 'Intake').color, isNull);
    expect(_glyph(tester, 'Queue'), UiIcons.queue.glyph);
    expect(_glyph(tester, 'Intake'), UiIcons.intake.glyph);
    final before = tester.getTopLeft(find.text('Intake'));
    await tester.tap(find.bySemanticsLabel('Intake'));
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(find.text('Intake')), before);
    expect(_surface(tester, 'Intake').color, isNotNull);
    expect(_surface(tester, 'Intake').border, isNull);
    expect(_surface(tester, 'Queue').color, isNull);
    expect(
      tester.widget<Text>(find.text('Intake')).style!.fontWeight,
      FontWeight.w600,
    );
    final icon = tester.widget<Icon>(
      find
          .descendant(
            of: find.bySemanticsLabel('Intake'),
            matching: find.byType(Icon),
          )
          .first,
    );
    expect(icon.size, UiIconSize.inline.dimension);
    expect(
      tester.getSize(find.bySemanticsLabel('Intake')).height,
      greaterThanOrEqualTo(48),
    );
  });

  testWidgets('the header sits above the rows and the footer below', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: const _SidebarHost(
          destinations: threeDestinations,
          header: Text('Specimen Digitization'),
          footer: Text('Signed in as a reviewer'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getBottomLeft(find.text('Specimen Digitization')).dy,
      lessThan(tester.getTopLeft(find.bySemanticsLabel('Queue')).dy),
    );
    expect(
      tester.getTopLeft(find.text('Signed in as a reviewer')).dy,
      greaterThan(tester.getBottomLeft(find.bySemanticsLabel('Sources')).dy),
    );
  });

  testWidgets('every row is a tab, one is selected', (
    WidgetTester tester,
  ) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(
      uiHarness(child: const _SidebarHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    for (final MapEntry<int, UiNavDestination> entry
        in threeDestinations.asMap().entries) {
      final SemanticsData data = tester
          .getSemantics(find.bySemanticsLabel(entry.value.label))
          .getSemanticsData();
      expect(data.role, SemanticsRole.tab);
      expect(
        data.flagsCollection.isSelected,
        entry.key == 0 ? Tristate.isTrue : Tristate.isFalse,
      );
    }
    expect(
      find.byWidgetPredicate(
        (Widget widget) =>
            widget is Semantics &&
            widget.properties.role == SemanticsRole.tabBar,
      ),
      findsOneWidget,
    );
    handle.dispose();
  });

  testWidgets('a row holds its words at every text scale', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(child: const _SidebarHost(destinations: threeDestinations)),
    );
    await tester.pumpAndSettle();
    final double atRest = tester.getSize(find.bySemanticsLabel('Queue')).height;

    // At 200 percent the words still fit inside the density's row height, so
    // the row holds and nothing is clipped.
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(2),
        child: const _SidebarHost(destinations: threeDestinations),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.bySemanticsLabel('Queue')).height,
      greaterThanOrEqualTo(tester.getSize(find.text('Queue')).height),
    );

    // Past the point where they do not, the row grows rather than clipping:
    // the row height is a floor, not a fixed height (10 section 2 clause 7).
    await tester.pumpWidget(
      uiHarness(
        textScaler: const TextScaler.linear(3),
        child: const _SidebarHost(destinations: threeDestinations),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getSize(find.bySemanticsLabel('Queue')).height,
      greaterThan(atRest),
    );
  });

  testWidgets('the destinations scroll when the pane is too short for them', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      uiHarness(
        child: SizedBox(
          height: 200,
          child: UiSidebar(
            destinations: fiveDestinations,
            currentIndex: 0,
            onSelect: (int _) {},
            header: const Text('Specimen Digitization'),
            footer: const Text('Signed in as a reviewer'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.text('Specimen Digitization'), findsOneWidget);
    expect(find.text('Signed in as a reviewer'), findsOneWidget);

    // The entire pane scrolls, including account/footer content.
    await tester.drag(
      find.byType(SingleChildScrollView),
      const Offset(0, -400),
    );
    await tester.pumpAndSettle();
    expect(
      tester.getRect(find.text('Signed in as a reviewer')).bottom,
      lessThanOrEqualTo(tester.getRect(find.byType(UiSidebar)).bottom),
    );
  });

  for (final UiNavDestination destination in threeDestinations) {
    testWidgets('control contract: ${destination.label}', (
      WidgetTester tester,
    ) async {
      await expectControlContract(
        tester,
        (BuildContext context) =>
            const _SidebarHost(destinations: threeDestinations),
        semanticsLabel: destination.label,
        labelsNeverWrap: true,
        geometryFromType: true,
        fit: FitExpectation(
          check: (WidgetTester tester, double width) async {
            expect(
              find.bySemanticsLabel(destination.label),
              findsOneWidget,
              reason: 'every destination stays reachable at $width dp',
            );
          },
        ),
      );
    });
  }
}
