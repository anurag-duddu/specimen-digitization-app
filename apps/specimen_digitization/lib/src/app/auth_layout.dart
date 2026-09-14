/// The one layout every screen before the collection uses
/// (screen blueprints, section 2; responsive, section 3.1).
///
/// A single centered column, 400 logical pixels wide at every window class,
/// that scrolls with the software keyboard so the primary button stays
/// reachable on a phone. There is no second pane at any width: a split screen
/// would read as consumer chrome on an evidentiary tool.
library;

import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../theme/icons.dart';
import '../widgets/widgets.dart';

/// The centered entry column.
class AuthLayout extends StatelessWidget {
  const AuthLayout({
    super.key,
    required this.title,
    required this.children,
    this.purpose,
    this.wordmark = true,
  });

  /// The screen's own heading, under the wordmark.
  final String title;

  /// One line saying what this screen is for.
  final String? purpose;

  /// The form, the actions and at most one secondary line.
  final List<Widget> children;

  /// False on a screen that already sits under an app bar.
  final bool wordmark;

  /// The product name, spelled once.
  static const String productName = 'Specimen Digitization';

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: EdgeInsets.fromLTRB(
            context.space.space6,
            context.space.space6,
            context.space.space6,
            // Lift the column clear of the software keyboard.
            context.space.space6 + MediaQuery.viewInsetsOf(context).bottom,
          ),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: DialogWidths.narrow),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (wordmark) ...<Widget>[
                  ExcludeSemantics(
                    child: Icon(
                      Symbols.biotech,
                      size: context.sizes.iconDisplay,
                    ),
                  ),
                  SizedBox(height: context.space.space4),
                  Text(
                    productName,
                    style: theme.textTheme.headlineSmall,
                    textAlign: TextAlign.center,
                  ),
                  SizedBox(height: context.space.space6),
                ],
                Text(title, style: theme.textTheme.titleLarge),
                if (purpose != null) ...<Widget>[
                  SizedBox(height: context.space.space2),
                  Text(purpose!, style: theme.textTheme.bodyMedium),
                ],
                SizedBox(height: context.space.space6),
                ...children,
              ],
            ),
          ),
        ),
      ),
    );
  }
}
