/// Text a reviewer can select and copy, without Material
/// (10 section 1.3; accessibility, section 3.1).
///
/// `SelectionArea` is a Material widget: it reaches for
/// `materialTextSelectionControls` and the Material context menu, so a screen
/// on the design system cannot use it. `SelectableRegion` is the
/// `widgets.dart` control underneath it, and this is that control with the
/// one decision the product has to make written down once: no handles and no
/// context menu of its own.
///
/// Pointer selection and the copy shortcut work, which is the path a reviewer
/// on a desktop browser takes. On touch, where handles would be the
/// affordance, every evidence surface in this product carries a named copy
/// control instead, which is the 48 dp target a drag never is.
library;

import 'package:flutter/widgets.dart';

/// Makes [child] selectable with the product's own selection behaviour.
class SelectableEvidence extends StatelessWidget {
  const SelectableEvidence({super.key, required this.child});

  /// The text block to make selectable.
  final Widget child;

  @override
  Widget build(BuildContext context) => SelectableRegion(
    selectionControls: emptyTextSelectionControls,
    child: child,
  );
}
