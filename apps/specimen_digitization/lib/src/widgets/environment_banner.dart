/// The environment band (design system, section 7.3; UX writing, 5.1).
///
/// A full bleed strip that states a permanent condition of the build. It
/// never animates, because animating it would imply it just happened
/// (motion, catalog row 9), and it has no dismiss control, because the
/// condition it names does not go away.
///
/// Finding V-15: at 390 wide and 200 percent text the sentence wrapped to
/// eleven lines and took about half the window, which is why the record
/// scrolled instead of pinning the photograph. The band is now one line that
/// truncates, with the whole sentence on a tooltip and on its semantics node,
/// and a disclosure that opens the rest to a second line. Two lines is the
/// cap at every text scale, so the band can never take the screen again.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';

/// A band naming the environment, hidden entirely in production.
class EnvironmentBanner extends StatefulWidget {
  const EnvironmentBanner({super.key, required this.environment});

  /// The environment name the session reports, such as `synthetic`.
  final String environment;

  /// The one environment that gets no band.
  static const String production = 'production';

  /// The most lines the band may ever occupy, open or closed.
  ///
  /// Not a style preference. It is the guarantee that replaces finding V-15:
  /// whatever the text scale, the band is one line or two.
  static const int maxLines = 2;

  /// True when this environment should show a band at all.
  static bool showsFor(String environment) =>
      environment.trim().toLowerCase() != production;

  /// The environment's own name, sentence case.
  static String nameFor(String environment) {
    final String name = environment.trim().toLowerCase();
    if (name.isEmpty) return 'This environment';
    return '${name[0].toUpperCase()}${name.substring(1)} environment';
  }

  /// The clause the band always shows, short enough for one line.
  static String headlineFor(String environment) =>
      '${nameFor(environment)}. Results here are fixtures.';

  /// The clause behind the disclosure.
  static const String detail =
      'Not real model processing, and not approved museum records.';

  /// The sentence the band carries. Sentence case, no shouting, no dashes.
  ///
  /// This is what the tooltip and the semantics node say in full, whether the
  /// band is open or closed, so truncating the visible line never costs a
  /// reviewer the statement.
  static String messageFor(String environment) =>
      '${headlineFor(environment)} $detail';

  @override
  State<EnvironmentBanner> createState() => _EnvironmentBannerState();
}

class _EnvironmentBannerState extends State<EnvironmentBanner> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    if (!EnvironmentBanner.showsFor(widget.environment)) {
      return const SizedBox.shrink();
    }
    final ThemeData theme = Theme.of(context);
    final Color fill = context.tokens.environmentSyntheticFill;
    final Color onFill = context.tokens.environmentSyntheticOnFill;
    final String message = EnvironmentBanner.messageFor(widget.environment);
    final TextStyle? style = theme.textTheme.bodySmall?.copyWith(color: onFill);

    return Semantics(
      container: true,
      label: message,
      excludeSemantics: true,
      child: ColoredBox(
        color: fill,
        child: Padding(
          padding: EdgeInsets.only(left: context.space.space4),
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
                child: Tooltip(
                  message: message,
                  child: Text(
                    _open
                        ? message
                        : EnvironmentBanner.headlineFor(widget.environment),
                    style: style,
                    // One line closed, two open, at every text scale. The
                    // whole sentence stays on the tooltip and on the
                    // semantics node above.
                    maxLines: _open ? EnvironmentBanner.maxLines : 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
              IconButton(
                onPressed: () => setState(() => _open = !_open),
                // No animation. The band states a condition of the build, and
                // a band that moves reads as a band reporting news
                // (motion catalog, row 9).
                icon: Icon(
                  _open ? Symbols.expand_less : Symbols.expand_more,
                  color: onFill,
                ),
                iconSize: context.sizes.iconInline,
                tooltip: _open
                    ? 'Hide what a test environment means'
                    : 'Show what a test environment means',
              ),
            ],
          ),
        ),
      ),
    );
  }
}
