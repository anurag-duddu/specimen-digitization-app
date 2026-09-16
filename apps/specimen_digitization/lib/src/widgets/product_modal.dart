/// The product's adaptive modal: a sheet on a compact window, a dialog above
/// it (05 section 3.0; 10 section 4.3).
///
/// `UiDialog.showAdaptive` is the call a screen should make, and this does
/// exactly what it does, with one addition. `ModalRoutes` pushes the pane on
/// the root navigator, where the application has no `DefaultTextStyle` of its
/// own: a route outside a `Material` inherits the framework's own fallback,
/// and every `Text` in the pane comes out carrying its yellow underline. The
/// pane is therefore built here, inside a `DefaultTextStyle` taken from the
/// product's type scale, so the chrome the package draws (the title and the
/// action row) is inside it too.
//
// TODO(fe/polish-2): ModalRoutes should publish the product text style the
// way a `Material` does, and every call site here should go back to
// `UiDialog.showAdaptive`.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Opens [body] with [title] and at most two actions.
///
/// Returns what the pane was closed with, or null when it was dismissed.
Future<T?> showProductModal<T>({
  required BuildContext context,
  required String title,
  required WidgetBuilder body,
  UiModalActionBuilder? primaryAction,
  UiModalActionBuilder? secondaryAction,
  String? semanticsLabel,
  bool dismissible = true,
}) {
  final bool sheet = isCompactWindow(context);

  Widget pane(BuildContext modalContext) {
    final UiThemeData ui = modalContext.ui;
    final UiButton? primary = primaryAction?.call(modalContext);
    final UiButton? secondary = secondaryAction?.call(modalContext);
    return DefaultTextStyle(
      style: ui.type.body.copyWith(color: ui.color.ink),
      child: sheet
          ? UiSheet(
              title: title,
              primaryAction: primary,
              secondaryAction: secondary,
              child: body(modalContext),
            )
          : UiDialog(
              title: title,
              primaryAction: primary,
              secondaryAction: secondary,
              child: body(modalContext),
            ),
    );
  }

  return sheet
      ? showUiSheet<T>(
          context: context,
          semanticsLabel: semanticsLabel ?? title,
          dismissible: dismissible,
          builder: pane,
        )
      : showUiDialog<T>(
          context: context,
          semanticsLabel: semanticsLabel ?? title,
          dismissible: dismissible,
          builder: pane,
        );
}
