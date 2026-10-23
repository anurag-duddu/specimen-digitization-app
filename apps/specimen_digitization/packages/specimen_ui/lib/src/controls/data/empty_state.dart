/// The empty state (10 section 4.5, `UiEmptyState`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../actions/button.dart';

/// Scale of the decorative artwork and surrounding empty-state spacing.
enum UiEmptyStateSize {
  /// A compact cell or card absence.
  small,

  /// A section-level absence.
  medium,

  /// A page-level absence.
  large,
}

/// An absence, named, with explicit next actions.
///
/// Carried from the v1 `EmptyState`. Three parts in this order: a title
/// naming the absence, one sentence saying what would fill it, and a primary action
/// that does it. A secondary action may offer a distinct recovery path, such
/// as clearing filters instead of importing. A state with no next step has no
/// action.
///
/// It sits on the sky with no glass of its own: an empty screen is already
/// one object, and a pane around nothing is a pane around nothing.
class UiEmptyState extends StatelessWidget {
  /// An empty state named [title].
  const UiEmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.body,
    this.action,
    this.secondaryAction,
    this.media,
    this.compact = false,
    this.size,
  });

  /// The glyph, drawn at 40.
  ///
  /// 09 section 7 asks for the `light` weight at this size, so a registry
  /// entry that has a light form is the one to pass here.
  final IconSpec icon;

  /// The absence, named. Sentence case, no terminal period, 30 characters at
  /// the most (02 section 7).
  final String title;

  /// One sentence saying what would fill the absence.
  final String body;

  /// The primary action, typed as a button to preserve its control contract.
  ///
  /// It does something: a button with no `onPressed` is refused, as the v1
  /// `EmptyState` refused a label without a callback. A state whose way out
  /// is unavailable for now passes no button.
  final UiButton? action;

  /// Optional alternative, for example clearing filters rather than importing.
  final UiButton? secondaryAction;

  /// Optional file preview or illustration, replacing the default Phosphor icon.
  final Widget? media;

  /// Compact padding for a table/card rather than a full page.
  final bool compact;

  /// Optional explicit scale; null retains the legacy [compact] behavior.
  final UiEmptyStateSize? size;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiButton? button = action;
    assert(
      button == null || button.onPressed != null,
      'an empty state action that does nothing is no way out; pass none',
    );
    return Semantics(
      container: true,
      child: Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: ui.space.readingMax),
          child: Padding(
            padding: EdgeInsetsDirectional.symmetric(
              horizontal: ui.space.s6,
              vertical: switch (size) {
                UiEmptyStateSize.small => ui.space.s6,
                UiEmptyStateSize.medium => ui.space.s8,
                UiEmptyStateSize.large => ui.space.s12,
                null => compact ? ui.space.s6 : ui.space.s12,
              },
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                // The glyph repeats the title and adds nothing a screen
                // reader can act on.
                ExcludeSemantics(
                  child:
                      media ??
                      UiIcon(
                        icon,
                        size: size == UiEmptyStateSize.small
                            ? UiIconSize.action
                            : UiIconSize.display,
                        color: ui.color.inkSecondary,
                      ),
                ),
                SizedBox(height: ui.space.s4),
                Text(
                  title,
                  style: ui.type.title.copyWith(color: ui.color.ink),
                  textAlign: TextAlign.center,
                ),
                SizedBox(height: ui.space.s2),
                Text(
                  body,
                  style: ui.type.body.copyWith(color: ui.color.inkSecondary),
                  textAlign: TextAlign.center,
                ),
                if (button != null) ...<Widget>[
                  SizedBox(height: ui.space.s6),
                  Wrap(
                    alignment: WrapAlignment.center,
                    spacing: ui.space.s2,
                    runSpacing: ui.space.s2,
                    children: [?secondaryAction, button],
                  ),
                ],
                if (button == null && secondaryAction != null)
                  Padding(
                    padding: EdgeInsets.only(top: ui.space.s6),
                    child: secondaryAction,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
