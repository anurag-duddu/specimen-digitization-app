/// The top bar (10 section 4.4, `UiTopBar`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/glass.dart';
import '../../foundation/theme.dart';
import '../../primitives/glass_surface.dart';
import 'scaffold.dart';

/// The resolved measurements of one top bar (10 section 1.5).
@immutable
class UiTopBarStyle {
  /// Binds every token the top bar draws with.
  const UiTopBarStyle({
    required this.height,
    required this.gutter,
    required this.gap,
    required this.title,
  });

  /// The bar's least height, before the safe area and the text scale.
  ///
  /// `space.topBar` at touch density and the 48 dp hit box at pointer, which
  /// is 10 section 4.4's "56 dp (48 pointer)".
  final double height;

  /// The padding between the bar's content and the window's edge.
  final double gutter;

  /// The space between one slot and the next.
  final double gap;

  /// The title's type role.
  final TextStyle title;

  /// The style for [ui].
  static UiTopBarStyle resolve(UiThemeData ui) => UiTopBarStyle(
    height: ui.density.isTouch ? ui.space.topBar : UiDensity.hitBox,
    gutter: ui.space.s4,
    gap: ui.space.s2,
    title: ui.type.title,
  );
}

/// The bar across the top of a page: transparent over the fields, filled with
/// `glass.flat` once the content has scrolled under it.
///
/// Slots are [leading] (back, or the mark), [title], [actions] and an optional
/// [center] for the collection switcher on wide windows. There is no elevation
/// and no colour change on scroll beyond the glass fill, and the fill does not
/// fade in: 09 section 11 rejects glass that animates its opacity.
///
/// The bar owns the top and horizontal safe areas, so its pane reaches the
/// window's edges while its content clears a notch. A scaffold removes the top
/// padding from everything below it, which is why the two agree rather than
/// both insetting.
///
/// [scrolledUnder] is normally left null and read from the enclosing
/// `UiScaffold`, which drives it from the body's own scroll notifications.
/// Pass it to drive the bar from something else, and say what at the call
/// site.
///
/// Retires `AppBar`.
class UiTopBar extends StatelessWidget {
  /// A bar with the given slots.
  const UiTopBar({
    super.key,
    this.leading,
    this.title,
    this.center,
    this.actions = const <Widget>[],
    this.scrolledUnder,
  });

  /// The start slot: a back control, or the mark.
  final Widget? leading;

  /// The page's name, in sentence case with no terminal period
  /// (02 section 1.6). Set in `type.title`.
  final String? title;

  /// An optional slot between the title and the actions.
  ///
  /// Centred in the space the title and the actions leave rather than in the
  /// window, so it can never sit on top of either.
  final Widget? center;

  /// The end slot: icon buttons, in the order they are read.
  final List<Widget> actions;

  /// True once content has scrolled under the bar.
  ///
  /// Null reads the enclosing scaffold's value.
  final bool? scrolledUnder;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiTopBarStyle style = UiTopBarStyle.resolve(ui);
    final EdgeInsets safe = MediaQuery.paddingOf(context);
    final bool filled = scrolledUnder ?? UiScaffold.of(context).scrolledUnder;

    final Widget content = ConstrainedBox(
      constraints: BoxConstraints(minHeight: style.height + safe.top),
      child: Padding(
        padding: EdgeInsetsDirectional.symmetric(
          horizontal: style.gutter,
        ).add(
          EdgeInsets.only(left: safe.left, top: safe.top, right: safe.right),
        ),
        child: Row(
          children: <Widget>[
            if (leading != null) ...<Widget>[
              leading!,
              SizedBox(width: style.gap),
            ],
            if (title != null)
              Flexible(
                child: Text(
                  title!,
                  style: style.title.copyWith(color: ui.color.ink),
                ),
              ),
            if (center != null)
              Expanded(child: Center(child: center))
            else
              const Spacer(),
            for (final Widget action in actions) ...<Widget>[
              SizedBox(width: style.gap),
              action,
            ],
          ],
        ),
      ),
    );

    if (!filled) return content;
    return GlassSurface(
      level: GlassLevel.flat,
      // The bar spans the window, so it has no corners of its own.
      radius: ui.shape.none,
      child: content,
    );
  }
}
