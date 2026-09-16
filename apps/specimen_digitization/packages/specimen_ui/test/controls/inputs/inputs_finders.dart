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
