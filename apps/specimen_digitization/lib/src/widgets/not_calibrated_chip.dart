/// The abstention chip (design system, 7.2; UX writing, section 4.13).
///
/// The qualifier that sits beside a number the product will not stand behind.
/// It is an outline, never a color, because an abstention is not a severity:
/// `SpecimenIconography.abstentions` already names the vocabulary and this is
/// its chip. Two screens drew their own copy before this one existed; a
/// measurement that is not calibrated has to look the same wherever a
/// reviewer meets it.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';

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
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Semantics(
      container: true,
      label: semanticsLabel,
      excludeSemantics: true,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(context.shape.radiusXs),
          border: Border.all(
            color: theme.colorScheme.outline,
            width: context.shape.strokeBoundary,
          ),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: context.space.space2,
            vertical: context.space.space1,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              if (showGlyph) ...<Widget>[
                Icon(
                  Symbols.hide_source,
                  size: context.sizes.iconInline,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
                SizedBox(width: context.space.space1),
              ],
              // Flexible, not fixed: the chip sits beside measurements in
              // panes as narrow as a phone column.
              Flexible(
                child: Text(
                  label,
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
