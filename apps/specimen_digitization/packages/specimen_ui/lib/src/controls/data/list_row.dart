/// One row of a list (10 section 4.5, `UiListRow`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/fit.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import '../actions/button.dart' show UiSize;

/// What pressing a row does, and therefore what a screen reader calls it.
enum UiListRowMode {
  /// The row opens something. Semantics `button`.
  navigate,

  /// The row is in a selection. Semantics `checkbox`, with `checked`.
  select,

  /// The row is one destination of a navigation. Semantics `tab`, with
  /// `selected`.
  ///
  /// What `UiSidebar` publishes: a list of destinations is a tab list whose
  /// current member is selected, not a list of buttons one of which happens
  /// to be highlighted, and `SemanticsRole.tabBar` requires every child node
  /// to carry the tab role.
  tab,
}

/// The resolved paint of one row.
@immutable
class UiListRowStyle {
  /// Binds every token a row draws with.
  const UiListRowStyle({
    required this.background,
    required this.bar,
    required this.title,
    required this.subtitle,
    required this.padding,
    required this.gap,
    required this.minHeight,
    required this.barWidth,
    required this.trailingLabel,
    required this.trailingColor,
    required this.titleMin,
  });

  /// The fill, by state. Transparent except when the row is selected.
  final WidgetStateProperty<Color> background;

  /// The leading bar on a selected row.
  final Color bar;

  /// The title's resolved style.
  final TextStyle title;

  /// The subtitle's resolved style.
  final TextStyle subtitle;

  /// The padding inside the row, outside the leading bar's gutter.
  final EdgeInsetsGeometry padding;

  /// The space between the leading slot, the text and the trailing slot.
  final double gap;

  /// The row's minimum height.
  final double minHeight;

  /// The leading bar's width, which is also the gutter reserved for it on
  /// every row whether or not it is drawn.
  final double barWidth;

  /// The type role a [UiRowTrailing] sets its label in.
  final TextStyle trailingLabel;

  /// The colour a [UiRowTrailing] draws its label and its glyph in.
  final Color trailingColor;

  /// The least width the title may be given before the row switches to its
  /// compact variant (11 section 3.3, rule 3).
  final double titleMin;

  /// The fixed box the leading slot occupies.
  ///
  /// A 24 glyph, a 40 thumbnail and a checkbox all sit in the same box, so
  /// the title's leading edge is in one place down the whole list and does
  /// not move when a row's leading content changes, is hidden or is
  /// disabled.
  static const double leadingExtent = 40;

  /// 10 section 4.5: a selected row fills `ink` at 6 percent.
  static const double selectedFillOpacity = 0.06;

  /// The row's height in [ui].
  ///
  /// `density.rowHeight` floored at the hit box. 09 section 6 gives the
  /// pointer row 44, which is below the 48 the control contract sets in both
  /// densities, and a full width row has nowhere to put the 4 dp of
  /// transparent slop above and below without overlapping the rows it tiles
  /// against. The floor is the hit box; the touch row is unchanged at 56.
  static double heightOf(UiThemeData ui) =>
      ui.density.rowHeight < UiDensity.hitBox
      ? UiDensity.hitBox
      : ui.density.rowHeight;

  /// The style at [size] in [ui].
  static UiListRowStyle resolve(UiThemeData ui, UiSize size) {
    final bool dense = size == UiSize.sm;
    Color fill(Set<WidgetState> states) => states.contains(WidgetState.selected)
        ? ui.color.stateLayer(selectedFillOpacity)
        : ui.color.ground.withValues(alpha: 0);

    return UiListRowStyle(
      background: WidgetStateProperty.resolveWith(fill),
      bar: ui.color.ink,
      title: (dense ? ui.type.body : ui.type.title).copyWith(
        color: ui.color.ink,
      ),
      subtitle: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
      padding: EdgeInsetsDirectional.symmetric(
        horizontal: dense ? ui.space.s2 : ui.space.s3,
      ),
      gap: ui.space.s3,
      minHeight: heightOf(ui),
      barWidth: ui.shape.stroke.bar,
      trailingLabel: ui.type.label,
      trailingColor: ui.color.inkSecondary,
      titleMin: ui.space.labelMin,
    );
  }
}

/// The end of a row, as a glyph with a word beside it.
///
/// The declared form of the `trailing` slot, and the one the row can make
/// narrower: 11 section 3.3 gives `UiListRow` one compact variant, "trailing
/// drops its label and keeps its glyph", which a row can only do to a
/// trailing it can read. A `Text`, a chip or a caret passed straight into the
/// slot is drawn as it is and the title ellipsises instead, which is rule 4.
///
/// The label is not announced. A row publishes one merged node whose words
/// the caller states in `UiListRow.semanticsLabel`, so a trailing that says
/// something a screen reader needs says it there: a second node inside the
/// row would be a second stop on a row that is one thing.
class UiRowTrailing extends StatelessWidget {
  /// A glyph with [label] beside it.
  const UiRowTrailing({
    super.key,
    required this.label,
    required this.icon,
    this.compact = false,
    this.style,
  });

  /// The word. One or two, in sentence case (02 section 4.13).
  final String label;

  /// The glyph, which is what survives when the label is dropped.
  final IconSpec icon;

  /// True to draw the glyph alone.
  ///
  /// Set by the row when the title would otherwise fall under its minimum, so
  /// a call site passes the trailing once and the row decides.
  final bool compact;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiListRowStyle? style;

  /// The width this trailing needs in [context], with or without its label.
  ///
  /// Measured through the same painter the engine lays the line out with, so
  /// the row switches on the width the words actually take at the reviewer's
  /// text scale rather than on an estimate.
  double widthIn(BuildContext context, UiListRowStyle paint) {
    final double glyph = UiIconSize.inline.dimension;
    if (compact) return glyph;
    return glyph +
        paint.gap +
        measureLabel(context, label, paint.trailingLabel).width;
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiListRowStyle paint = style ?? UiListRowStyle.resolve(ui, UiSize.md);
    final Widget glyph = UiIcon(
      icon,
      size: UiIconSize.inline,
      color: paint.trailingColor,
    );
    if (compact) return glyph;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        glyph,
        SizedBox(width: paint.gap),
        Flexible(
          child: UiLabel(
            label,
            style: paint.trailingLabel.copyWith(color: paint.trailingColor),
          ),
        ),
      ],
    );
  }
}

/// A row of a list: a leading slot, a title over a subtitle, a trailing slot.
///
/// Retires `ListTile` and `CheckboxListTile`.
///
/// The whole row is one `Pressable` and one merged semantics node, so a
/// screen reader is not walked through the identifier, the reason, the chip
/// and the age as four separate stops. [mode] decides what that node is
/// called: a row that opens a record is a `button`, a row in a selection is a
/// `checkbox` carrying `checked`, and a row that is one destination of a
/// navigation is a `tab`.
///
/// Never glass. A row is a repeated item, and 09 section 11 rejects glass on
/// repeated items outright: the list's container may be a pane, its rows are
/// `paper` or nothing at all.
class UiListRow extends StatelessWidget {
  /// A row titled [title].
  const UiListRow({
    super.key,
    required this.title,
    this.subtitle,
    this.leading,
    this.trailing,
    this.size = UiSize.md,
    this.mode = UiListRowMode.navigate,
    this.selected = false,
    this.onPressed,
    this.onLongPress,
    this.semanticsLabel,
    this.disabledReason,
    this.focusNode,
    this.autofocus = false,
    this.statesController,
  });

  /// The row's own line. `type.title` at `md`, `type.body` at `sm`.
  final String title;

  /// One supporting line under the title, up to two lines long.
  final String? subtitle;

  /// A 24 glyph, a 40 thumbnail or a checkbox the caller passes in.
  final Widget? leading;

  /// Text, a chip or a caret at the end of the row.
  final Widget? trailing;

  /// `md` for a list, `sm` for a menu.
  final UiSize size;

  /// What pressing the row does.
  final UiListRowMode mode;

  /// True when the row is the open record, or is checked in a selection.
  final bool selected;

  /// What activation does. Null disables the row.
  final VoidCallback? onPressed;

  /// What a long press does, where the caller allows a selection to start
  /// with one.
  final VoidCallback? onLongPress;

  /// Overrides the phrase a screen reader reads.
  ///
  /// Defaults to the title and the subtitle, which is what the row shows. A
  /// row that carries a status, an age or a score in its slots states them
  /// here, because those slots' own semantics are dropped into this one node
  /// (02 section 4.16).
  final String? semanticsLabel;

  /// Why the row cannot be opened, in the reviewer's words.
  final String? disabledReason;

  /// An external focus node, for a list that moves focus itself.
  final FocusNode? focusNode;

  /// True to take focus when first built.
  final bool autofocus;

  /// An external states controller, for a caller that reads the row's states
  /// from outside it.
  final WidgetStatesController? statesController;

  /// The phrase the row publishes.
  String get _label {
    final String? second = subtitle;
    if (semanticsLabel != null) return semanticsLabel!;
    return second == null ? title : '$title, $second';
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiListRowStyle style = UiListRowStyle.resolve(ui, size);
    return Pressable(
      semanticsLabel: _label,
      onPressed: onPressed,
      onLongPress: onLongPress,
      disabledReason: disabledReason,
      selected: selected,
      role: switch (mode) {
        UiListRowMode.navigate => PressableRole.button,
        UiListRowMode.select => PressableRole.checkbox,
        UiListRowMode.tab => PressableRole.tab,
      },
      checked: mode == UiListRowMode.select ? selected : null,
      // A row has no corners of its own: it tiles against its neighbours and
      // the pane around it owns the shape. `radius.none` is the token for a
      // cell (09 section 5).
      radius: ui.shape.none,
      focusNode: focusNode,
      autofocus: autofocus,
      statesController: statesController,
      builder: (BuildContext context, Set<WidgetState> states) =>
          _body(context, style, states),
    );
  }

  Widget _body(
    BuildContext context,
    UiListRowStyle style,
    Set<WidgetState> states,
  ) => ColoredBox(
    color: style.background.resolve(states),
    child: Stack(
      children: <Widget>[
        if (selected)
          PositionedDirectional(
            start: 0,
            top: 0,
            bottom: 0,
            width: style.barWidth,
            child: ColoredBox(color: style.bar),
          ),
        Padding(
          // The bar's gutter is reserved on every row, drawn or not, so
          // selecting one never shifts its content sideways.
          padding: EdgeInsetsDirectional.only(start: style.barWidth),
          child: Padding(
            padding: style.padding,
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: style.minHeight),
              child: _fitted(context, style),
            ),
          ),
        ),
      ],
    ),
  );

  /// The row's two arrangements (11 section 3.3).
  ///
  /// The title is content and takes two lines, so the row never has to choose
  /// between a word and an ellipsis for it. What it does choose is whether
  /// the trailing keeps its label: below the width at which the title falls
  /// under `titleMin` the trailing drops to its glyph, which is worth some
  /// seventy logical pixels on a two word status and is the difference
  /// between a readable identifier and four characters of one.
  ///
  /// Only a [UiRowTrailing] can be made narrower. Anything else in the slot
  /// is drawn as it was given, the row declares one variant, and rule 4 takes
  /// over.
  Widget _fitted(BuildContext context, UiListRowStyle style) {
    final Widget? end = trailing;
    final double chrome =
        style.padding.resolve(Directionality.of(context)).horizontal +
        style.barWidth +
        (leading == null ? 0 : UiListRowStyle.leadingExtent + style.gap) +
        (end == null ? 0 : style.gap);

    if (end is! UiRowTrailing) {
      return FitBuilder(
        variants: <FitVariant>[
          FitVariant(
            intrinsicWidth: chrome + style.titleMin,
            builder: (BuildContext context, bool _) =>
                _line(context, style, end),
          ),
        ],
      );
    }

    final UiRowTrailing full = UiRowTrailing(
      label: end.label,
      icon: end.icon,
      style: style,
    );
    final UiRowTrailing glyph = UiRowTrailing(
      label: end.label,
      icon: end.icon,
      compact: true,
      style: style,
    );
    return FitBuilder(
      variants: <FitVariant>[
        FitVariant(
          intrinsicWidth:
              chrome + style.titleMin + full.widthIn(context, style),
          builder: (BuildContext context, bool _) =>
              _line(context, style, full),
        ),
        FitVariant(
          intrinsicWidth:
              chrome + style.titleMin + glyph.widthIn(context, style),
          builder: (BuildContext context, bool _) =>
              _line(context, style, glyph),
        ),
      ],
    );
  }

  Widget _line(BuildContext context, UiListRowStyle style, Widget? end) => Row(
    children: <Widget>[
      if (leading != null) ...<Widget>[
        SizedBox.square(
          dimension: UiListRowStyle.leadingExtent,
          child: Center(child: leading),
        ),
        SizedBox(width: style.gap),
      ],
      Expanded(child: _text(style)),
      if (end != null) ...<Widget>[SizedBox(width: style.gap), end],
    ],
  );

  /// The title over the subtitle, both clipped so that neither can push the
  /// row wider than the pane it sits in. The whole of both is in the
  /// semantics label, so nothing an ellipsis hides is lost.
  ///
  /// Both are content rather than labels (11 section 3.3): a record's
  /// identifier and the sentence under it are what the row is for, so they
  /// wrap to a second line before they are cut. The row grows; its minimum
  /// height is a floor and never a ceiling.
  Widget _text(UiListRowStyle style) {
    final String? second = subtitle;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          title,
          style: style.title,
          maxLines: contentMaxLines,
          overflow: TextOverflow.ellipsis,
        ),
        if (second != null)
          Text(
            second,
            style: style.subtitle,
            maxLines: contentMaxLines,
            overflow: TextOverflow.ellipsis,
          ),
      ],
    );
  }

  /// The most lines the title or the subtitle takes before it ellipsises.
  ///
  /// Two, per 11 section 3.3: the title is content, and a row four lines deep
  /// is a card.
  static const int contentMaxLines = 2;
}
