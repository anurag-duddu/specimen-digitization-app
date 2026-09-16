/// The dialog (10 section 4.3, `UiDialog`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
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
/// capped at `space.dialogMax` by the route.
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
  }) => showUiDialog<T>(
    context: context,
    semanticsLabel: semanticsLabel ?? title,
    dismissLabel: dismissLabel,
    dismissible: dismissible,
    builder: (BuildContext context) => UiDialog(
      title: title,
      primaryAction: primaryAction?.call(context),
      secondaryAction: secondaryAction?.call(context),
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
        );

  @override
  Widget build(BuildContext context) {
    final UiModalStyle paint = style ?? UiModalStyle.resolve(context.ui);
    return Padding(
      padding: paint.padding,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Semantics(
            header: true,
            child: Text(
              title,
              style: paint.title.copyWith(color: paint.titleColor),
            ),
          ),
          SizedBox(height: paint.gap),
          Flexible(child: child),
          if (primaryAction != null || secondaryAction != null) ...<Widget>[
            SizedBox(height: paint.gap),
            UiModalActions(
              primary: primaryAction,
              secondary: secondaryAction,
              style: paint,
            ),
          ],
        ],
      ),
    );
  }
}
