/// The product's adaptive modal: a sheet on a compact window, a dialog above
/// it (05 section 3.0; 10 section 4.3).
///
/// One call, so a screen never writes the breakpoint itself. It was its own
/// implementation while the package published no text style of its own: a
/// route pushed on the root navigator inherited the framework fallback, and
/// every word in the pane came out with a double yellow underline, so the
/// pane was built here inside a `DefaultTextStyle` taken from the type scale.
/// `UiTheme` publishes that style now and `ModalRoutes` publishes it again
/// around its own frame (11 section 5), so this is the package's own call
/// with the product's defaults on it.
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
}) => UiDialog.showAdaptive<T>(
  context: context,
  title: title,
  body: body,
  primaryAction: primaryAction,
  secondaryAction: secondaryAction,
  semanticsLabel: semanticsLabel ?? title,
  dismissible: dismissible,
);
