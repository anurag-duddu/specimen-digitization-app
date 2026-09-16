/// The abstention chip (10 sections 4.1 and 5; 02 section 4.13).
///
/// The qualifier that sits beside a number the product will not stand behind.
/// It is an outline, never a colour, because an abstention is not a severity.
/// Two screens drew their own copy before this one existed; a measurement that
/// is not calibrated has to look the same wherever a reviewer meets it.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The uncalibrated qualifier, outline only.
class NotCalibratedChip extends StatelessWidget {
  const NotCalibratedChip({super.key, this.showGlyph = true});

  /// The word, used by the widget and by the tests that assert on it.
  static const String label = 'Not calibrated';

  /// What assistive technology hears, as a complete phrase.
  static const String semanticsLabel = 'Measurement: not calibrated';

  /// False inside a meter that already carries its own glyph, where a second
  /// one would read as a second measurement.
  final bool showGlyph;

  @override
  Widget build(BuildContext context) => UiChip(
    label: label,
    icon: showGlyph ? UiIcons.unmeasured : null,
    semanticsLabel: semanticsLabel,
  );
}
