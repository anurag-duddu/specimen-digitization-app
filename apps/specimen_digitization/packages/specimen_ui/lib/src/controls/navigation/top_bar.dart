/// The top bar (10 section 4.4, `UiTopBar`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/glass.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/fit.dart';
import '../../primitives/glass_surface.dart';
import '../../primitives/label.dart';
import '../actions/icon_button.dart';
import '../overlays/popover_menu.dart';
import 'scaffold.dart';

/// One command at the end of a top bar, declared rather than drawn.
///
/// The bar has one compact variant, "actions beyond two collapse into an
/// overflow menu" (11 section 3.3), and a menu needs a label, a glyph and a
/// shortcut for every command it lists. A `Widget` in the slot carries none of
/// those, so an action that may be collapsed says what it is here and lets the
/// bar draw it either as a disc or as a menu item.
///
/// A bar given plain widgets still works and still ellipsises its title; it
/// simply keeps every action drawn, because a bar cannot put into a menu a
/// control it cannot read.
class UiTopBarAction extends StatelessWidget {
  /// A command called [label] that does [onPressed].
  const UiTopBarAction({
    super.key,
    required this.icon,
    required this.label,
    this.onPressed,
    this.shortcut,
    this.disabledReason,
  });

  /// The glyph on the disc, and at the start of the menu row.
  final IconSpec icon;

  /// What the command is called. Verb first, two to four words
  /// (02 section 4.3). The disc has no visible text, so this is its tooltip
  /// and its semantics label as well as the menu row's words.
  final String label;

  /// What choosing it does. Null disables it.
  final VoidCallback? onPressed;

  /// The keyboard shortcut, shown at the end of the menu row.
  final String? shortcut;

  /// Why the command is unavailable, in the reviewer's words
  /// (03 section 3.6).
  final String? disabledReason;

  /// The same command as a menu row.
  UiMenuItem get menuItem => UiMenuItem(
    label: label,
    onSelected: onPressed,
    icon: icon,
    shortcut: shortcut,
    disabledReason: disabledReason,
  );

  @override
  Widget build(BuildContext context) => UiIconButton(
    icon: icon,
    semanticsLabel: label,
    tooltip: label,
    onPressed: onPressed,
    disabledReason: disabledReason,
  );
}

/// The resolved measurements of one top bar (10 section 1.5).
@immutable
class UiTopBarStyle {
  /// Binds every token the top bar draws with.
  const UiTopBarStyle({
    required this.height,
    required this.gutter,
    required this.gap,
    required this.title,
    required this.actionExtent,
    required this.titleMin,
  });

  /// The bar's least height, before the safe area and the text scale.
  ///
  /// `space.topBar` at touch density and the 48 dp hit box at pointer, which
  /// is 10 section 4.4's "56 dp (48 pointer)", and the floor rather than the
  /// height: [heightIn] grows it with the title's line box.
  final double height;

  /// The padding between the bar's content and the window's edge.
  final double gutter;

  /// The space between one slot and the next.
  final double gap;

  /// The title's type role.
  final TextStyle title;

  /// The width one action disc occupies.
  final double actionExtent;

  /// The least width the title is given before the actions collapse.
  final double titleMin;

  /// The style for [ui].
  static UiTopBarStyle resolve(UiThemeData ui) => UiTopBarStyle(
    height: ui.density.isTouch ? ui.space.topBar : UiDensity.hitBox,
    gutter: ui.space.s4,
    gap: ui.space.s2,
    title: ui.type.title,
    actionExtent: UiDensity.hitBox,
    titleMin: ui.space.labelMin,
  );

  /// The bar's height at [context]'s text scale (11 section 2.2).
  ///
  /// A bar holds one line of `type.title`, so its height is that line box
  /// plus the padding the density height implies, floored at the density
  /// height itself. At scale 1.0 it is 56 or 48 exactly, as 10 section 4.4
  /// states it; above it the bar grows rather than clipping the title.
  double heightIn(UiThemeData ui, BuildContext context) {
    final double derived =
        UiType.lineHeightOf(title, context) +
        2 * UiType.insetFor(ui.density, title);
    return derived < height ? height : derived;
  }

  /// How many actions stay on the bar when the rest collapse.
  ///
  /// Two, per 11 section 3.3. One disc beside an overflow glyph reads as two
  /// overflow controls; three is already a row the title has to fight.
  static const int keptActions = 2;

  /// What the overflow trigger is called.
  static const String overflowLabel = 'More actions';
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
/// **Fit** (11 section 3.3). The title ellipsises first: it is a [UiLabel] in
/// the space the other slots leave, and the whole of it stays on its semantics
/// node. When even a title cut to [UiTopBarStyle.titleMin] leaves no room, the
/// actions past the second collapse into an overflow [UiPopoverMenu] carrying
/// the same labels, glyphs and shortcuts, so nothing a reviewer could do at
/// 1400 dp is unreachable at 360. That needs actions the bar can read: see
/// [UiTopBarAction].
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

  /// The end slot: commands, in the order they are read.
  ///
  /// [UiTopBarAction]s are the declared form and the only one the bar can
  /// collapse into an overflow menu.
  final List<Widget> actions;

  /// True once content has scrolled under the bar.
  ///
  /// Null reads the enclosing scaffold's value.
  final bool? scrolledUnder;

  /// The actions, where every one of them is declared.
  ///
  /// Null when any is an opaque widget, which is the bar's signal to keep
  /// them all drawn rather than to collapse a control it cannot describe.
  List<UiTopBarAction>? get _declared {
    final List<UiTopBarAction> declared = <UiTopBarAction>[];
    for (final Widget action in actions) {
      if (action is! UiTopBarAction) return null;
      declared.add(action);
    }
    return declared;
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiTopBarStyle style = UiTopBarStyle.resolve(ui);
    final EdgeInsets safe = MediaQuery.paddingOf(context);
    final bool filled = scrolledUnder ?? UiScaffold.of(context).scrolledUnder;

    final Widget content = ConstrainedBox(
      constraints: BoxConstraints(
        minHeight: style.heightIn(ui, context) + safe.top,
      ),
      child: Padding(
        padding: EdgeInsetsDirectional.symmetric(
          horizontal: style.gutter,
        ).add(
          EdgeInsets.only(left: safe.left, top: safe.top, right: safe.right),
        ),
        child: _fitted(context, ui, style),
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

  /// The bar's arrangements, widest first.
  ///
  /// Every action drawn; then the first two drawn and the rest in an overflow
  /// menu, which is the row 11 section 3.3 gives this control; then every
  /// action in the menu, for a column narrow enough that two discs and a
  /// trigger leave the title nothing. The title ellipsises inside each of
  /// them, which is why it is the flexible child: a bar runs out of variants
  /// long before it runs out of words to cut.
  ///
  /// A bar given opaque widgets declares one arrangement and keeps them all,
  /// because it cannot put into a menu a control it cannot read.
  Widget _fitted(BuildContext context, UiThemeData ui, UiTopBarStyle style) {
    final List<UiTopBarAction>? declared = _declared;
    // The chrome the title has to share the line with. The leading slot is an
    // opaque widget, so it is counted as one hit box, which is what a back
    // control and the mark both are.
    final double chrome =
        (leading == null ? 0 : UiDensity.hitBox + style.gap) + style.titleMin;
    double widthOf(int slots) =>
        chrome + slots * (style.actionExtent + style.gap);

    final List<List<Widget>> arrangements = <List<Widget>>[
      actions,
      if (declared != null && declared.length > UiTopBarStyle.keptActions)
        _collapsed(declared, UiTopBarStyle.keptActions),
      if (declared != null && declared.length > UiTopBarStyle.keptActions)
        _collapsed(declared, 0),
    ];
    return FitBuilder(
      variants: <FitVariant>[
        for (final List<Widget> drawn in arrangements)
          FitVariant(
            intrinsicWidth: widthOf(drawn.length),
            builder: (BuildContext context, bool _) => _row(ui, style, drawn),
          ),
      ],
    );
  }

  /// [keep] actions on the bar, and the rest behind one overflow trigger.
  List<Widget> _collapsed(List<UiTopBarAction> declared, int keep) =>
      <Widget>[
        ...declared.take(keep),
        UiMenuTrigger(
          semanticsLabel: UiTopBarStyle.overflowLabel,
          icon: UiIcons.more,
          items: <UiMenuItem>[
            for (final UiTopBarAction action in declared.skip(keep))
              action.menuItem,
          ],
        ),
      ];

  /// One arrangement of the bar, with [drawn] at its end.
  ///
  /// The title takes the whole of what the leading and the actions leave when
  /// it is alone there, and half of it when there is a centre slot, which is
  /// 10 section 4.4's rule that the centre is centred in the space the title
  /// and the actions leave rather than in the window. A `Spacer` beside a
  /// `Flexible` title would have taken half of that space in both cases, and
  /// a 200 percent title then ellipsised with the other half of the bar
  /// empty beside it.
  Widget _row(UiThemeData ui, UiTopBarStyle style, List<Widget> drawn) {
    final Widget? name = title == null
        ? null
        : UiLabel(
            title!,
            style: style.title.copyWith(color: ui.color.ink),
          );
    return Row(
      children: <Widget>[
        if (leading != null) ...<Widget>[leading!, SizedBox(width: style.gap)],
        if (center != null) ...<Widget>[
          if (name != null) Flexible(child: name),
          Expanded(child: Center(child: center)),
        ] else if (name != null)
          Expanded(child: name)
        else
          const Spacer(),
        for (final Widget action in drawn) ...<Widget>[
          SizedBox(width: style.gap),
          action,
        ],
      ],
    );
  }
}
