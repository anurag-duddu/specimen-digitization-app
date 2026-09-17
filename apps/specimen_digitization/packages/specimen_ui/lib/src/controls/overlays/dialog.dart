/// The dialog (10 section 4.3, `UiDialog`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../primitives/label.dart';
import '../../primitives/modal_routes.dart';
import '../actions/button.dart';
import 'sheet.dart';

/// The chrome of a centred dialog.
///
/// Retires `AlertDialog` and `showDialog`. Like [UiSheet] this is the content
/// of the pane `showUiDialog` pushes rather than a pane of its own, so a
/// window never carries two modal glass surfaces (09 section 3.3).
///
/// The difference from a sheet is the shape and the handle: a dialog floats,
/// so all four of its corners turn and there is nothing to drag. Its width is
/// capped at `space.dialogMax` by the route, and its body scrolls inside the
/// height the window leaves it, as a sheet's does.
///
/// [UiDialog.show] is the wrapper that pushes the route and fills this in.
class UiDialog extends StatelessWidget {
  /// A dialog titled [title] over [child].
  const UiDialog({
    super.key,
    required this.title,
    required this.child,
    this.primaryAction,
    this.secondaryAction,
    this.scrollBody = true,
    this.style,
  });

  /// The dialog's title. A question or an imperative, 40 characters or fewer,
  /// no period (02 section 4.5).
  final String title;

  /// The body. Two sentences at most (02 section 4.5).
  final Widget child;

  /// The one action that carries the dialog's verb. It repeats the verb in
  /// the title, and is never "Confirm" (02 section 4.4).
  final UiButton? primaryAction;

  /// The way out.
  final UiButton? secondaryAction;

  /// True to scroll [child] inside the height the chrome leaves it.
  ///
  /// The default, and what [UiSheet] does with the same parameter, so a body
  /// written for [UiDialog.showAdaptive] never has to know which of the two
  /// frames it landed in. A dialog is bounded by the window it floats in, so
  /// a body taller than that height, which two sentences become at 200
  /// percent text on a short window, scrolls rather than overflowing. Pass
  /// false when [child] is already a scrollable, because two scrollables in
  /// one column give the inner one an unbounded height again.
  final bool scrollBody;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiModalStyle? style;

  /// Pushes a dialog and returns what it was closed with.
  ///
  /// The chrome wrapper over the `showUiDialog` primitive: a caller names the
  /// slots rather than building the surface.
  static Future<T?> show<T>({
    required BuildContext context,
    required String title,
    required WidgetBuilder body,
    UiModalActionBuilder? primaryAction,
    UiModalActionBuilder? secondaryAction,
    String? semanticsLabel,
    String? dismissLabel,
    bool dismissible = true,
    bool scrollBody = true,
  }) => showUiDialog<T>(
    context: context,
    semanticsLabel: semanticsLabel ?? title,
    dismissLabel: dismissLabel,
    dismissible: dismissible,
    builder: (BuildContext context) => UiDialog(
      title: title,
      primaryAction: primaryAction?.call(context),
      secondaryAction: secondaryAction?.call(context),
      scrollBody: scrollBody,
      child: body(context),
    ),
  );

  /// Pushes a sheet on a compact window and a dialog above it.
  ///
  /// One call, so a screen never writes the breakpoint itself
  /// (05 section 3.7).
  static Future<T?> showAdaptive<T>({
    required BuildContext context,
    required String title,
    required WidgetBuilder body,
    UiModalActionBuilder? primaryAction,
    UiModalActionBuilder? secondaryAction,
    String? semanticsLabel,
    String? dismissLabel,
    bool dismissible = true,
    bool scrollBody = true,
  }) => isCompactWindow(context)
      ? UiSheet.show<T>(
          context: context,
          title: title,
          body: body,
          primaryAction: primaryAction,
          secondaryAction: secondaryAction,
          semanticsLabel: semanticsLabel,
          dismissLabel: dismissLabel,
          dismissible: dismissible,
          scrollBody: scrollBody,
        )
      : UiDialog.show<T>(
          context: context,
          title: title,
          body: body,
          primaryAction: primaryAction,
          secondaryAction: secondaryAction,
          semanticsLabel: semanticsLabel,
          dismissLabel: dismissLabel,
          dismissible: dismissible,
          scrollBody: scrollBody,
        );

  @override
  Widget build(BuildContext context) {
    final UiModalStyle paint =
        style ?? UiModalStyle.resolve(context.ui, context);
    return Padding(
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
            child: scrollBody ? SingleChildScrollView(child: child) : child,
          ),
          if (primaryAction != null || secondaryAction != null) ...<Widget>[
            SizedBox(height: paint.gap),
            UiModalActions(primary: primaryAction, secondary: secondaryAction),
          ],
        ],
      ),
    );
  }
}
