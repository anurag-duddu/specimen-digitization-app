// Shared readings for the inputs tests.
//
// A field's edge and fill are the two things every test in this family asserts
// on, and reading them out of the decoration in one place keeps the tests
// about behaviour rather than about widget trees.

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The tokens the tree under [tester] resolved.
UiThemeData uiOf(WidgetTester tester) =>
    tester.element(find.byType(UiFieldBox).first).ui;

/// The decoration of the first field box on screen.
ShapeDecoration _decoration(WidgetTester tester) =>
    tester
            .widget<DecoratedBox>(
              find
                  .descendant(
                    of: find.byType(UiFieldBox).first,
                    matching: find.byType(DecoratedBox),
                  )
                  .first,
            )
            .decoration
        as ShapeDecoration;

/// The edge of the first field box on screen.
BorderSide fieldSide(WidgetTester tester) =>
    (_decoration(tester).shape as OutlinedBorder).side;

/// The fill of the first field box on screen.
Color fieldFill(WidgetTester tester) => _decoration(tester).color!;

/// Every edge on screen that a reviewer can see.
///
/// A `ShapeDecoration` whose shape carries a side wider than nothing. 11
/// section 4 gives a field exactly one, so counting them is how a test says
/// "one edge" rather than "the edge I happened to look at".
int visibleEdges(WidgetTester tester, [Finder? within]) {
  final Finder boxes = within == null
      ? find.byType(DecoratedBox)
      : find.descendant(of: within, matching: find.byType(DecoratedBox));
  return tester.widgetList<DecoratedBox>(boxes).where((DecoratedBox box) {
    final Decoration decoration = box.decoration;
    if (decoration is! ShapeDecoration) return false;
    final ShapeBorder shape = decoration.shape;
    return shape is OutlinedBorder &&
        shape.side.style != BorderStyle.none &&
        shape.side.width > 0;
  }).length;
}

/// How many focus rings are being painted.
int visibleRings(WidgetTester tester, [Finder? within]) {
  final Finder rings = within == null
      ? find.byType(FocusRing)
      : find.descendant(of: within, matching: find.byType(FocusRing));
  return tester
      .widgetList<FocusRing>(rings)
      .where((FocusRing ring) => ring.visible)
      .length;
}

/// How many rings are actually on the canvas under [within].
///
/// Counted from the painting side rather than from the widget side: each
/// `FocusRing` is asked for the `CustomPaint` it builds, and only the ones
/// carrying a foreground painter are counted. Everything else that paints
/// inside a field is left out by construction, including the
/// `BorderSide.none` painter the transparent `Material` the editor needs
/// brings with it.
int ringPainters(WidgetTester tester, Finder within) {
  int painting = 0;
  for (final Element ring in tester.elementList(
    find.descendant(of: within, matching: find.byType(FocusRing)),
  )) {
    CustomPaint? own;
    void nearestPaint(Element element) {
      if (own != null) return;
      final Widget widget = element.widget;
      if (widget is CustomPaint) {
        own = widget;
        return;
      }
      element.visitChildren(nearestPaint);
    }

    ring.visitChildren(nearestPaint);
    if (own?.foregroundPainter != null) painting++;
  }
  return painting;
}

/// Every live region label on screen, in tree order.
///
/// A message that has to be announced once lives in a live region, so this is
/// how a test asserts that an error announced itself and that help text did
/// not (06 section 3).
List<String> liveRegions(WidgetTester tester) => <String>[
  for (final SemanticsNode node in _nodes(tester.binding.rootElement!))
    if (node.getSemanticsData().flagsCollection.isLiveRegion)
      node.getSemanticsData().label,
];

Iterable<SemanticsNode> _nodes(Element root) sync* {
  final SemanticsOwner? owner = root.renderObject?.owner?.semanticsOwner;
  final SemanticsNode? tree = owner?.rootSemanticsNode;
  if (tree == null) return;
  yield* _walk(tree);
}

Iterable<SemanticsNode> _walk(SemanticsNode node) sync* {
  yield node;
  final List<SemanticsNode> children = <SemanticsNode>[];
  node.visitChildren((SemanticsNode child) {
    children.add(child);
    return true;
  });
  for (final SemanticsNode child in children) {
    yield* _walk(child);
  }
}
