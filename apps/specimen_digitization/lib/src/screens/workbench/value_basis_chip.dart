/// The chip that says how a field's value was obtained (UX writing, 4.13).
///
/// Outline only, like the not-calibrated chip: a basis is a statement of
/// provenance, not a severity, so it takes no status colour. The word carries
/// the meaning, so colour is never the only carrier.
library;

import 'package:specimen_ui/specimen_ui.dart';

import 'value_basis.dart';

/// One small chip reading "As written", "Derived" or "Inferred".
///
/// A [UiChip] itself, not a wrapper, because `UiDisclosure.trailing` measures
/// the chip it is given to decide whether it fits beside the title.
UiChip valueBasisChip(ValueBasis basis) =>
    UiChip(label: basis.label, semanticsLabel: basis.semanticsLabel);
