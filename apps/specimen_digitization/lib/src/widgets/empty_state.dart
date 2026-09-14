/// The empty state (design system, 7.2; UX writing, section 4.6).
///
/// Three parts, in this order: a title naming the absence, one sentence
/// saying what would fill it, and at most one button that does it.
library;

import 'package:flutter/material.dart';

import '../theme/icons.dart';

/// An absence, named, with one way out of it.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.body,
    this.actionLabel,
    this.onAction,
  }) : assert(
         (actionLabel == null) == (onAction == null),
         'an empty state action needs both a label and a callback',
       );

  /// A 40dp display glyph.
  final IconData icon;

  /// The absence, named. Sentence case, no terminal period.
  final String title;

  /// One sentence saying what would fill the emptiness.
  final String body;

  /// The single action's verb phrase, two to four words.
  final String? actionLabel;

  /// What the single action does.
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final String? action = actionLabel;

    return Semantics(
      container: true,
      child: Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: context.sizes.readingMax),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: context.space.space6,
              vertical: context.space.space12,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: <Widget>[
                ExcludeSemantics(
                  child: Icon(
                    icon,
                    size: context.sizes.iconDisplay,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                SizedBox(height: context.space.space4),
                Text(
                  title,
                  style: theme.textTheme.titleMedium,
                  textAlign: TextAlign.center,
                ),
                SizedBox(height: context.space.space2),
                Text(
                  body,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  textAlign: TextAlign.center,
                ),
                if (action != null) ...<Widget>[
                  SizedBox(height: context.space.space6),
                  FilledButton(onPressed: onAction, child: Text(action)),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
