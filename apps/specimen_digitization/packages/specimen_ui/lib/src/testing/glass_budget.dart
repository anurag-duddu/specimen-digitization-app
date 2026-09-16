/// Counting the frosted panes on screen (09 section 3.3; 10 section 8,
/// `glass_budget`).
///
/// A pane costs a save layer, so the budget is a design rule rather than a
/// suggestion: at most four panes per window and at most one modal. What is
/// countable is the `BackdropFilter` render objects actually in the tree,
/// which is the only number that matters on a tablet.
///
/// These are plain functions rather than matchers, and they import nothing
/// from `flutter_test`, so the package's test harness and the application's
/// golden harness can both build `expectGlassBudget` on them without
/// `flutter_test` entering the application's dependency graph.
library;

import 'package:flutter/widgets.dart';

/// How many frosted panes are in the tree right now.
int glassPaneCount() => _glassPanes().length;

/// How many of them sit inside a modal route.
///
/// A sheet and a dialog are both pushed over the page, so anything whose
/// enclosing route is a `PopupRoute` is inside a modal. `ModalRoutes` builds
/// both on `RawDialogRoute`, which is one.
int modalGlassPaneCount() => _glassPanes()
    .where((Element element) => ModalRoute.of(element) is PopupRoute)
    .length;

List<Element> _glassPanes() {
  final Element? root = WidgetsBinding.instance.rootElement;
  if (root == null) return const <Element>[];
  final List<Element> found = <Element>[];
  void visit(Element element) {
    if (element.widget is BackdropFilter) found.add(element);
    element.visitChildren(visit);
  }

  visit(root);
  return found;
}
