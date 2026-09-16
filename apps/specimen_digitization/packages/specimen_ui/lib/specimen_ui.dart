/// The Specimen Digitization design system.
///
/// Tokens, primitives and controls built on `package:flutter/widgets.dart`.
/// The direction is `design/09-brand-direction.md`; the library is specified
/// in `design/10-component-library.md`.
///
/// This barrel is written once, in the foundation wave, and lists the five
/// family barrels rather than the controls inside them, so a family agent
/// adding a control never edits this file.
library;

// Foundation (L1).
export 'src/foundation/color.dart';
export 'src/foundation/density.dart';
export 'src/foundation/fields.dart';
export 'src/foundation/fonts.dart';
export 'src/foundation/glass.dart';
export 'src/foundation/motion.dart';
export 'src/foundation/palette.dart';
export 'src/foundation/shape.dart';
export 'src/foundation/space.dart';
export 'src/foundation/type.dart';

// Controls (L3), one barrel per family.
export 'src/controls/actions/actions.dart';
export 'src/controls/data/data.dart';
export 'src/controls/inputs/inputs.dart';
export 'src/controls/navigation/navigation.dart';
export 'src/controls/overlays/overlays.dart';
