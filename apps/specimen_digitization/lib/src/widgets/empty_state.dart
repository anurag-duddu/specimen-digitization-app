/// The empty state (10 sections 4.5 and 5; 02 section 4.6).
///
/// Three parts, in this order: a title naming the absence, one sentence
/// saying what would fill it, and at most one button that does it.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

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

  /// The 40 dp display glyph.
  ///
  /// Still an `IconData` rather than an `IconSpec`, because the screens that
  /// raise an empty state are other slots' and move in wave 3. A glyph named
  /// here is wrapped in a registry entry at `regular`, so both kinds of
  /// caller draw through `UiIcon`.
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
    final UiThemeData ui = context.ui;
    final String? action = actionLabel;

    return Semantics(
      container: true,
      child: Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: ui.space.readingMax),
          child: Padding(
            padding: EdgeInsetsDirectional.symmetric(
              horizontal: ui.space.s6,
              vertical: ui.space.s12,
            ),
            child: UiEmptyState(
              icon: IconSpec(icon, weight: UiIconWeight.light),
              title: title,
              body: body,
              action: action == null
                  ? null
                  : UiButton(
                      label: action,
                      variant: UiButtonVariant.primary,
                      onPressed: onAction,
                    ),
            ),
          ),
        ),
      ),
    );
  }
}
