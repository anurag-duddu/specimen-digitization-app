/// Evidence keeps its styled text and explicit copy commands while the shared
/// selection adapter supplies platform handles, magnifier and context menus.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Makes [child] selectable with the product's own selection behaviour.
class SelectableEvidence extends StatelessWidget {
  const SelectableEvidence({super.key, required this.child});

  /// The text block to make selectable.
  final Widget child;

  @override
  Widget build(BuildContext context) => UiSelectionArea(child: child);
}
