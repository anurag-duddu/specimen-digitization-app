/// One row of a list (10 section 4.5, `UiListRow`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';
import '../actions/button.dart' show UiSize;

/// What pressing a row does, and therefore what a screen reader calls it.
enum UiListRowMode {
  /// The row opens something. Semantics `button`.
  navigate,

  /// The row is in a selection. Semantics `checkbox`, with `checked`.
  select,
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
/// called: a row that opens a record is a `button`, and a row in a selection
/// is a `checkbox` carrying `checked`.
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
      role: mode == UiListRowMode.select
          ? PressableRole.checkbox
          : PressableRole.button,
      checked: mode == UiListRowMode.select ? selected : null,
      // A row has no corners of its own: it tiles against its neighbours and
      // the pane around it owns the shape. `radius.none` is the token for a
      // cell (09 section 5).
      radius: ui.shape.none,
      focusNode: focusNode,
      autofocus: autofocus,
      statesController: statesController,
      builder: (BuildContext context, Set<WidgetState> states) =>
          _body(ui, style, states),
    );
  }

  Widget _body(
    UiThemeData ui,
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
              child: Row(
                children: <Widget>[
                  if (leading != null) ...<Widget>[
                    SizedBox.square(
                      dimension: UiListRowStyle.leadingExtent,
                      child: Center(child: leading),
                    ),
                    SizedBox(width: style.gap),
                  ],
                  Expanded(child: _text(ui, style)),
                  if (trailing != null) ...<Widget>[
                    SizedBox(width: style.gap),
                    trailing!,
                  ],
                ],
              ),
            ),
          ),
        ),
      ],
    ),
  );

  /// The title over the subtitle, both clipped so that neither can push the
  /// row wider than the pane it sits in. The whole of both is in the
  /// semantics label, so nothing an ellipsis hides is lost.
  Widget _text(UiThemeData ui, UiListRowStyle style) {
    final String? second = subtitle;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          title,
          style: style.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        if (second != null)
          Text(
            second,
            style: style.subtitle,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
      ],
    );
  }
}
