/// The environment band (design system, section 7.3; UX writing, 5.1).
///
/// A full bleed strip that states a permanent condition of the build. It
/// never animates, because animating it would imply it just happened
/// (motion, catalog row 9), and it has no dismiss control, because the
/// condition it names does not go away.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';

/// A band naming the environment, hidden entirely in production.
class EnvironmentBanner extends StatelessWidget {
  const EnvironmentBanner({super.key, required this.environment});

  /// The environment name the session reports, such as `synthetic`.
  final String environment;

  /// The one environment that gets no band.
  static const String production = 'production';

  /// True when this environment should show a band at all.
  static bool showsFor(String environment) =>
      environment.trim().toLowerCase() != production;

  /// The sentence the band carries. Sentence case, no shouting, no dashes.
  static String messageFor(String environment) {
    final String name = environment.trim().toLowerCase();
    final String opening = name.isEmpty
        ? 'This environment'
        : '${name[0].toUpperCase()}${name.substring(1)} environment';
    return '$opening. Results here are fixtures, not real model processing '
        'and not approved museum records.';
  }

  @override
  Widget build(BuildContext context) {
    if (!showsFor(environment)) return const SizedBox.shrink();
    final ThemeData theme = Theme.of(context);
    final Color fill = context.tokens.environmentSyntheticFill;
    final Color onFill = context.tokens.environmentSyntheticOnFill;
    // 28dp: the band is a strip, not a card. It is a minimum, so the text
    // wraps to a second line on a narrow window rather than truncating.
    final double strip = context.space.space6 + context.space.space1;

    return Semantics(
      container: true,
      label: messageFor(environment),
      excludeSemantics: true,
      child: ColoredBox(
        color: fill,
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: strip),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: context.space.space4,
              vertical: context.space.space1,
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: <Widget>[
                Icon(
                  Symbols.science,
                  size: context.sizes.iconInline,
                  color: onFill,
                ),
                SizedBox(width: context.space.space2),
                Expanded(
                  child: Text(
                    messageFor(environment),
                    style: theme.textTheme.bodySmall?.copyWith(color: onFill),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
