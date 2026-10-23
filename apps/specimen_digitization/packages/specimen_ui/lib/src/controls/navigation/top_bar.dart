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
    onPressed: onPressed,
    disabledReason: disabledReason,
  );
}

/// Which of the two bars [UiTopBar] is (10 section 4.4, amended 2026-10-17).
///
/// The names follow `UiBannerForm`: one component, two forms, each resolved
/// from tokens in [UiTopBarStyle] rather than tuned at a call site.
enum UiTopBarForm {
  /// A page's bar: transparent over the page, a title and commands, filled
  /// with `glass.flat` once content has scrolled under it. What every record
  /// screen draws, and the default.
  page,

  /// The workspace header: the collection switcher and the account, on every
  /// compact destination, as one surface.
  ///
  /// It paints an opaque `paper` ground (14 section 3: shell chrome is
  /// `paper`) across its whole box, **including the top safe inset**, so the
  /// status bar strip and the bar read as one surface on every tab and every
  /// platform. It is the top edge mirror of `UiTabBar`, which paints its
  /// ground under the bottom inset: in both, the platform only decides how
  /// big the inset is. Around its 48 dp controls it keeps `space.s2` of air on
  /// every side, the actions touch (their own hit boxes are the spacing), and
  /// the [UiTopBar.leading] slot takes the space the actions leave, start
  /// aligned, so a long collection name is cut rather than overflowing.
  workspace,
}

/// The resolved measurements of one top bar (10 section 1.5).
@immutable
class UiTopBarStyle {
  /// Binds every token the top bar draws with.
  const UiTopBarStyle({
    required this.form,
    required this.height,
    required this.gutter,
    required this.verticalInset,
    required this.gap,
    required this.title,
    required this.actionExtent,
    required this.titleMin,
    this.ground,
  });

  /// Which form this is.
  final UiTopBarForm form;

  /// The bar's least height, before the safe area and the text scale.
  ///
  /// Page form: `space.topBar` at touch density and the 48 dp hit box at
  /// pointer, which is 10 section 4.4's "56 dp (48 pointer)", and the floor
  /// rather than the height: [heightIn] grows it with the title's line box.
  /// Workspace form: a 48 dp control plus [verticalInset] above and below,
  /// 64 dp, at both densities, and again a floor: the controls grow it.
  final double height;

  /// The padding between the bar's content and the window's edge.
  final double gutter;

  /// The air above and below the content row, inside [height]. Zero for the
  /// page form, whose content is centred in its height instead.
  final double verticalInset;

  /// The space between one slot and the next.
  final double gap;

  /// The opaque ground the bar paints over its whole box, the top safe inset
  /// included, or null for a bar that is transparent until content scrolls
  /// under it.
  final Color? ground;

  /// The title's type role.
  final TextStyle title;

  /// The width one action disc occupies.
  final double actionExtent;

  /// The least width the title is given before the actions collapse.
  final double titleMin;

  /// The style for [ui] in [form].
  static UiTopBarStyle resolve(
    UiThemeData ui, {
    UiTopBarForm form = UiTopBarForm.page,
  }) => switch (form) {
    UiTopBarForm.page => UiTopBarStyle(
      form: form,
      height: ui.density.isTouch ? ui.space.topBar : UiDensity.hitBox,
      gutter: ui.space.s4,
      verticalInset: ui.space.s0,
      gap: ui.space.s2,
      title: ui.type.title,
      actionExtent: UiDensity.hitBox,
      titleMin: ui.space.labelMin,
    ),
    UiTopBarForm.workspace => UiTopBarStyle(
      form: form,
      height: UiDensity.hitBox + 2 * ui.space.s2,
      gutter: ui.space.s2,
      verticalInset: ui.space.s2,
      gap: ui.space.s0,
      title: ui.type.title,
      actionExtent: UiDensity.hitBox,
      titleMin: ui.space.labelMin,
      ground: ui.color.paper,
    ),
  };

  /// The bar's height at [context]'s text scale (11 section 2.2).
  ///
  /// A bar holds one line of `type.title`, so its height is that line box
  /// plus the padding the density height implies, floored at the density
  /// height itself. At scale 1.0 it is 56 or 48 exactly, as 10 section 4.4
  /// states it; above it the bar grows rather than clipping the title.
  double heightIn(UiThemeData ui, BuildContext context) {
    // The workspace form holds controls, not a title line: they set its
    // height, and `height` is only the floor under them.
    if (form == UiTopBarForm.workspace) return height;
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
/// Inside a frame the bar also reads [UiTopBarAsk]: a routed screen that
/// names itself through `UiScaffoldSlots.setTitle` or puts its way out in
/// `setLeading` wins over the [title] and [leading] the shell built the bar
/// with, and everything else on the bar stays (13 section 3.4; polish 3).
///
/// **Forms.** [UiTopBarForm.page], the default, is everything above. The
/// [UiTopBarForm.workspace] form is the compact shell's header: an opaque
/// `paper` ground that runs under the top safe inset, so the status strip and
/// the bar are one surface on every tab, with the collection switcher in
/// [leading] and the account in [actions]. The inset's size comes from the
/// platform, never from here (05 section 5). A page bar's behaviour is the
/// same with or without the workspace form existing.
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
    this.form = UiTopBarForm.page,
  });

  /// Which bar this is. The page form is the default.
  final UiTopBarForm form;

  /// The start slot: a back control, or the mark. In the workspace form, the
  /// collection switcher, which takes the space the actions leave and sits at
  /// its start.
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
    final UiTopBarStyle style = UiTopBarStyle.resolve(ui, form: form);
    final EdgeInsets safe = MediaQuery.paddingOf(context);
    // A bar with its own ground is always filled, so it neither reads nor
    // depends on the scaffold's scroll state.
    final bool filled =
        style.ground != null ||
        (scrolledUnder ?? UiScaffold.of(context).scrolledUnder);
    // What the routed screen asked of this bar wins over what it was built
    // with, slot by slot.
    final UiTopBarAsk? asked = UiTopBarAsk.maybeOf(context);
    final String? shownTitle = asked?.title ?? title;
    final Widget? shownLeading = asked?.leading ?? leading;

    final Widget content = ConstrainedBox(
      constraints: BoxConstraints(
        minHeight: style.heightIn(ui, context) + safe.top,
      ),
      child: Padding(
        padding:
            EdgeInsetsDirectional.symmetric(
              horizontal: style.gutter,
              vertical: style.verticalInset,
            ).add(
              EdgeInsets.only(
                left: safe.left,
                top: safe.top,
                right: safe.right,
              ),
            ),
        child: _fitted(
          context,
          ui,
          style,
          title: shownTitle,
          leading: shownLeading,
        ),
      ),
    );

    if (!filled) return content;
    // The opaque ground covers the whole box, and the box includes the top
    // safe inset the padding above reserves, so nothing of the page or the
    // scaffold's ground shows in the status strip.
    if (style.ground case final Color ground) {
      return ColoredBox(color: ground, child: content);
    }
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
  Widget _fitted(
    BuildContext context,
    UiThemeData ui,
    UiTopBarStyle style, {
    required String? title,
    required Widget? leading,
  }) {
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
            builder: (BuildContext context, bool _) =>
                _row(ui, style, drawn, title: title, leading: leading),
          ),
      ],
    );
  }

  /// [keep] actions on the bar, and the rest behind one overflow trigger.
  List<Widget> _collapsed(List<UiTopBarAction> declared, int keep) => <Widget>[
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
  Widget _row(
    UiThemeData ui,
    UiTopBarStyle style,
    List<Widget> drawn, {
    required String? title,
    required Widget? leading,
  }) {
    final Widget? name = title == null
        ? null
        : UiLabel(title, style: style.title.copyWith(color: ui.color.ink));
    // The workspace form's switcher is the flexible slot: it is a wide
    // labelled control, not a disc, so it takes what the actions leave and
    // sits at the start, where a long name is cut by the control itself.
    final bool flexibleLeading =
        style.form == UiTopBarForm.workspace &&
        leading != null &&
        name == null &&
        center == null;
    return Row(
      children: <Widget>[
        if (flexibleLeading)
          Expanded(
            child: Align(
              alignment: AlignmentDirectional.centerStart,
              // The width is the slot's, the height is the control's: an
              // `Align` with no factor would take every pixel a bounded
              // parent offers and a bar would stop being a bar.
              heightFactor: 1,
              child: leading,
            ),
          )
        else ...<Widget>[
          if (leading != null) ...<Widget>[leading, SizedBox(width: style.gap)],
          if (center != null) ...<Widget>[
            if (name != null) Flexible(child: name),
            Expanded(child: Center(child: center)),
          ] else if (name != null)
            Expanded(child: name)
          else
            const Spacer(),
        ],
        for (final Widget action in drawn) ...<Widget>[
          SizedBox(width: style.gap),
          action,
        ],
      ],
    );
  }
}
