/// Brand expression that protects text and photographic evidence from a tint.
library;

import 'package:flutter/widgets.dart';

import '../foundation/theme.dart';

/// A decorative amber-to-iris region with no content slot.
///
/// Keeping this visual separate prevents copy or evidence from accidentally
/// being placed on a changing-contrast background. It carries no semantics.
class UiBrandAccent extends StatelessWidget {
  /// Draws the brand gradient at [height], or the standard large spacing step.
  const UiBrandAccent({super.key, this.height});

  /// The decorative region's height. Width follows its parent.
  final double? height;

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: SizedBox(
      height: height ?? context.ui.space.s16,
      child: DecoratedBox(
        decoration: BoxDecoration(gradient: context.ui.brand.heroGradient),
        child: const SizedBox.expand(),
      ),
    ),
  );
}

/// An adaptable hero with an explicit brand region and solid content panel.
///
/// Copy and actions wrap naturally at large text sizes. The gradient cannot
/// host text or evidence; use [UiBrandAccent] separately for smaller brand
/// moments. This pattern is for welcome, introduction and empty-state pages,
/// not for repeated record rows or photographic workbenches.
class UiBrandHero extends StatelessWidget {
  /// Builds a solid content panel beneath a decorative gradient.
  const UiBrandHero({
    super.key,
    required this.title,
    this.eyebrow,
    this.description,
    this.actions = const <Widget>[],
    this.padding,
  });

  /// The primary heading, exposed as a semantic heading.
  final String title;

  /// A short contextual label above the heading.
  final String? eyebrow;

  /// Supporting copy that is allowed to wrap without a line cap.
  final String? description;

  /// Actions that wrap to additional rows when space is limited.
  final List<Widget> actions;

  /// Optional content inset; the default follows the spacing grid.
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: ui.color.paper,
        border: Border.all(color: ui.color.hairline),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const UiBrandAccent(),
          Padding(
            padding: padding ?? EdgeInsets.all(ui.space.s6),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                if (eyebrow != null) ...<Widget>[
                  Text(
                    eyebrow!,
                    style: ui.type.label.copyWith(
                      color: ui.brand.secondary.content,
                    ),
                  ),
                  SizedBox(height: ui.space.s2),
                ],
                Semantics(
                  header: true,
                  child: Text(
                    title,
                    style: ui.type.headline.copyWith(color: ui.color.ink),
                  ),
                ),
                if (description != null) ...<Widget>[
                  SizedBox(height: ui.space.s2),
                  Text(
                    description!,
                    style: ui.type.bodyLarge.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                ],
                if (actions.isNotEmpty) ...<Widget>[
                  SizedBox(height: ui.space.s6),
                  Wrap(
                    spacing: ui.space.s2,
                    runSpacing: ui.space.s2,
                    children: actions,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
