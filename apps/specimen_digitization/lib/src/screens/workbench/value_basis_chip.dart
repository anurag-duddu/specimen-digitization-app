/// The chip that says how a field's value was obtained (UX writing, 4.13).
///
/// Outline only, like the not-calibrated chip: a basis is a statement of
/// provenance, not a severity, so it takes no status colour. The word carries
/// the meaning, so colour is never the only carrier.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'value_basis.dart';

/// One small chip reading "As written", "Derived" or "Inferred".
class ValueBasisChip extends StatelessWidget {
  const ValueBasisChip({super.key, required this.basis});

  /// The basis to name.
  final ValueBasis basis;

  @override
  Widget build(BuildContext context) =>
      UiChip(label: basis.label, semanticsLabel: basis.semanticsLabel);
}
