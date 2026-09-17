/// The empty state (10 section 4.5, `UiEmptyState`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../actions/button.dart';

/// An absence, named, with at most one way out of it.
///
/// Carried from the v1 `EmptyState`. Three parts in this order: a title
/// naming the absence, one sentence saying what would fill it, and one button
/// that does it (02 section 4.6). A state with nothing to do has no button,
/// and a state with two things to do is two states.
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

  /// The single action. Typed as a button rather than as a slot, because
  /// "at most one `UiButton`" is the rule and a type states it.
  final UiButton? action;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiButton? button = action;
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
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                // The glyph repeats the title and adds nothing a screen
                // reader can act on.
                ExcludeSemantics(
                  child: UiIcon(
                    icon,
                    size: UiIconSize.display,
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
                  button,
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
