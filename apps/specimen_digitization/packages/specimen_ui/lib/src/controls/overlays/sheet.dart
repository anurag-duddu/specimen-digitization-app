/// The bottom sheet (10 section 4.3, `UiSheet`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/fit.dart';
import '../../primitives/label.dart';
import '../../primitives/modal_routes.dart';
import '../actions/button.dart';

/// Builds one of a modal's actions, with the modal's own context.
///
/// A builder rather than a widget because an action almost always closes the
/// modal it is in, and `Navigator.pop` needs the context inside the route.
typedef UiModalActionBuilder = UiButton Function(BuildContext context);

/// The resolved paint of a sheet or a dialog.
@immutable
class UiModalStyle {
  /// Binds every token the modal chrome draws with.
  const UiModalStyle({
    required this.padding,
    required this.gap,
    required this.actionGap,
    required this.title,
    required this.titleColor,
    required this.handleColor,
    required this.handleSize,
    required this.actionHeight,
  });

  /// Padding inside the pane.
  final EdgeInsetsGeometry padding;

  /// The gap between the title, the body and the action row.
  final double gap;

  /// The gap between the two actions.
  final double actionGap;

  /// The title's type role: `title.large`.
  final TextStyle title;

  /// The title's colour.
  final Color titleColor;

  /// The drag handle's colour. An edge the reviewer must be able to find, so
  /// `boundary` rather than `hairline` (09 section 3.1).
  final Color handleColor;

  /// The drag handle's size.
  final Size handleSize;

  /// The least height the action row occupies, derived from the label role
  /// the buttons in it are set in (11 section 2.2).
  ///
  /// At scale 1.0 it is the density's control height exactly; above it the
  /// strip grows with the words rather than clipping them.
  final double actionHeight;

  /// The style the modal chrome draws with in [ui], at [context]'s scale.
  ///
  /// [context] is optional so that a caller with tokens and no element still
  /// gets the chrome's paint; without it the action row reports its height at
  /// scale 1.0, which is the density height.
  static UiModalStyle resolve(UiThemeData ui, [BuildContext? context]) =>
      UiModalStyle(
        padding: EdgeInsetsDirectional.all(ui.space.s6),
        gap: ui.space.s4,
        actionGap: ui.space.s2,
        title: ui.type.titleLarge,
        titleColor: ui.color.ink,
        handleColor: ui.color.boundary,
        handleSize: Size(ui.space.s8, ui.space.s1),
        actionHeight: context == null
            ? ui.density.controlHeight
            : UiType.controlHeightFor(ui.density, ui.type.label, context),
      );

  /// How fast a downward flick on the handle has to be to close the sheet.
  ///
  /// Logical pixels per second. Dragging is never the only way out: the scrim
  /// and Escape both close a dismissible sheet, which is what SC 2.5.7 asks
  /// for (06 section 3.2).
  static const double dismissVelocity = 400;
}

/// The action row of a sheet or a dialog.
///
/// At most one `primary` and one `secondary` or `ghost` button, plus any
/// [tertiary] actions, aligned to the end with the primary last
/// (10 section 4.3). It becomes a column with the primary on top when the row
/// does not fit on one line or the window is compact, which is 11 section
/// 3.3's row for a modal's actions: "the actions stack, primary on top".
///
/// Public because both modals draw it and because a screen that builds its
/// own surface should not reinvent it.
///
// fe/fit-actions: this is `UiButtonRow` of 11 section 3.4 under the name the
// overlays family already had for it, built to that section's shape so the
// swap is a rename and a move. Slot G1 owns `controls/actions/` and lands the
// real class; when it does, this becomes a forwarder or goes, and its two
// call sites below move with it. Spelled without a `TODO(` marker on purpose:
// the `no_stand_ins` gate fails on that string anywhere under `lib/`, and
// weakening a gate to carry a coordination note is the worse trade.
class UiModalActions extends StatelessWidget {
  /// A row of [primary], [secondary] and [tertiary].
  const UiModalActions({
    super.key,
    this.primary,
    this.secondary,
    this.tertiary = const <UiButton>[],
    this.style,
  });

  /// The one action that carries the modal's verb.
  final UiButton? primary;

  /// The way out. "Cancel" for a form, never "OK" (02 section 4.3).
  final UiButton? secondary;

  /// Anything else the modal offers, read before the two above.
  final List<UiButton> tertiary;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiModalStyle? style;

  /// The buttons in the order a row draws them: the primary last, at the end.
  List<UiButton> get _inRow => <UiButton>[
    ...tertiary,
    ?secondary,
    ?primary,
  ];

  /// The buttons in the order a column draws them: the primary on top.
  ///
  /// The order reverses with the axis because "last" and "first" are the same
  /// position read two ways: the end of a line and the top of a stack are
  /// both where the eye finishes, and the primary belongs there.
  List<UiButton> get _inColumn => <UiButton>[
    ?primary,
    ?secondary,
    ...tertiary,
  ];

  @override
  Widget build(BuildContext context) {
    assert(
      primary == null || primary!.variant == UiButtonVariant.primary,
      'the primary action of a modal is the primary variant (10 section 4.3)',
    );
    assert(
      secondary == null || secondary!.variant != UiButtonVariant.primary,
      'a modal carries at most one primary action (10 section 4.3)',
    );
    final UiThemeData ui = context.ui;
    final UiModalStyle paint = style ?? UiModalStyle.resolve(ui, context);
    final List<UiButton> row = _inRow;
    if (row.isEmpty) return const SizedBox.shrink();
    if (isCompactWindow(context)) return _column(paint);

    double width = paint.actionGap * (row.length - 1);
    for (final UiButton button in row) {
      width += _buttonWidth(context, ui, button);
    }
    return FitBuilder(
      variants: <FitVariant>[
        FitVariant(
          intrinsicWidth: width,
          builder: (BuildContext context, bool _) => _row(paint, row),
        ),
        FitVariant(
          intrinsicWidth: 0,
          builder: (BuildContext context, bool _) => _column(paint),
        ),
      ],
    );
  }

  Widget _row(UiModalStyle paint, List<UiButton> buttons) => ConstrainedBox(
    constraints: BoxConstraints(minHeight: paint.actionHeight),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: <Widget>[
        for (int i = 0; i < buttons.length; i++) ...<Widget>[
          if (i != 0) SizedBox(width: paint.actionGap),
          buttons[i],
        ],
      ],
    ),
  );

  Widget _column(UiModalStyle paint) {
    final List<UiButton> buttons = _inColumn;
    return Column(
      mainAxisSize: MainAxisSize.min,
      // Stretched, because a stacked action that is narrower than the one
      // above it reads as the lesser of the two whichever way round they are.
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        for (int i = 0; i < buttons.length; i++) ...<Widget>[
          if (i != 0) SizedBox(height: paint.actionGap),
          buttons[i],
        ],
      ],
    );
  }
}

/// The width [button] needs to draw its label, its glyphs and its padding.
///
/// Measured through the button's own resolved style, so the arithmetic does
/// not restate a token the actions family owns.
double _buttonWidth(BuildContext context, UiThemeData ui, UiButton button) {
  final UiButtonStyle style = UiButtonStyle.resolve(
    ui,
    button.variant,
    button.size,
  );
  final double glyphs =
      (button.loading || button.leading != null
          ? ui.space.iconInline + style.gap
          : 0) +
      (button.trailing != null ? ui.space.iconInline + style.gap : 0);
  return style.padding.resolve(Directionality.of(context)).horizontal +
      glyphs +
      measureLabel(context, button.label, style.label).width;
}

/// The chrome of a bottom sheet.
///
/// Retires `showModalBottomSheet` and `BottomSheet`. This is the content of
/// the pane `showUiSheet` pushes, not a pane of its own: the route already
/// carries the one modal glass surface the budget allows (09 section 3.3).
///
/// [UiSheet.show] is the wrapper that pushes the route and fills this in.
class UiSheet extends StatelessWidget {
  /// A sheet titled [title] over [child].
  const UiSheet({
    super.key,
    required this.title,
    required this.child,
    this.primaryAction,
    this.secondaryAction,
    this.showDragHandle = true,
    this.scrollBody = true,
    this.style,
  });

  /// The sheet's title. A question or an imperative, 40 characters or fewer,
  /// no period (02 section 4.5).
  final String title;

  /// The body.
  final Widget child;

  /// The one action that carries the sheet's verb.
  final UiButton? primaryAction;

  /// The way out.
  final UiButton? secondaryAction;

  /// True to draw the handle at the top of the sheet.
  final bool showDragHandle;

  /// True to scroll [child] inside the height the chrome leaves it.
  ///
  /// The default, and what a body of stacked controls needs: the sheet is
  /// bounded by the window, so a body taller than the window scrolls rather
  /// than pushing the action row off the bottom. Pass false when [child] is
  /// already a scrollable, because two scrollables in one column give the
  /// inner one an unbounded height again.
  final bool scrollBody;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiModalStyle? style;

  /// Pushes a sheet and returns what it was closed with.
  ///
  /// The chrome wrapper over the `showUiSheet` primitive: a caller names the
  /// slots rather than building the surface. The primitive keeps its own name
  /// and its own signature, so a caller that wants a bare pane still has one.
  static Future<T?> show<T>({
    required BuildContext context,
    required String title,
    required WidgetBuilder body,
    UiModalActionBuilder? primaryAction,
    UiModalActionBuilder? secondaryAction,
    String? semanticsLabel,
    String? dismissLabel,
    bool dismissible = true,
    bool showDragHandle = true,
    bool scrollBody = true,
  }) => showUiSheet<T>(
    context: context,
    semanticsLabel: semanticsLabel ?? title,
    dismissLabel: dismissLabel,
    dismissible: dismissible,
    builder: (BuildContext context) => UiSheet(
      title: title,
      showDragHandle: showDragHandle,
      scrollBody: scrollBody,
      primaryAction: primaryAction?.call(context),
      secondaryAction: secondaryAction?.call(context),
      child: body(context),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiModalStyle paint = style ?? UiModalStyle.resolve(ui, context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (showDragHandle) _DragHandle(style: paint),
        // The body's bound, and the whole of it. A `Column` hands an
        // inflexible child an unbounded main axis, so the padded block used
        // to be measured against infinity and the `Flexible` inside it had
        // nothing to be flexible against: a scrolling body shrink wrapped to
        // its entire content and a filter sheet overflowed a phone by 1044
        // dp. Flexible here is what makes "the window height minus the
        // chrome" a measurement the layout takes rather than a sum this file
        // would have to keep in step with the chrome above and below it.
        Flexible(
          child: Padding(
            padding: paint.padding,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Semantics(
                  header: true,
                  child: UiLabel(
                    title,
                    style: paint.title.copyWith(color: paint.titleColor),
                  ),
                ),
                SizedBox(height: paint.gap),
                Flexible(
                  child: scrollBody
                      ? SingleChildScrollView(child: child)
                      : child,
                ),
                if (primaryAction != null ||
                    secondaryAction != null) ...<Widget>[
                  SizedBox(height: paint.gap),
                  UiModalActions(
                    primary: primaryAction,
                    secondary: secondaryAction,
                    style: paint,
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// The bar at the top of a sheet, and the flick that closes it.
class _DragHandle extends StatelessWidget {
  const _DragHandle({required this.style});

  final UiModalStyle style;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      // The handle is the affordance, not the only way out: the scrim and
      // Escape close the sheet too, so this carries no semantics of its own.
      excludeFromSemantics: true,
      onVerticalDragEnd: (DragEndDetails details) {
        if (details.velocity.pixelsPerSecond.dy <
            UiModalStyle.dismissVelocity) {
          return;
        }
        Navigator.maybeOf(context)?.maybePop();
      },
      child: Padding(
        padding: EdgeInsetsDirectional.symmetric(vertical: ui.space.s3),
        child: Center(
          child: SizedBox(
            width: style.handleSize.width,
            height: style.handleSize.height,
            child: DecoratedBox(
              decoration: ShapeDecoration(
                shape: const StadiumBorder(),
                color: style.handleColor,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
