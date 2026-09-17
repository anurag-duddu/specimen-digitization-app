/// One entry point for every modal that collects something
/// (design system, 7.3 `ReasonSheet`; 10 section 5; 11 section 5).
///
/// A sheet below 600 logical pixels and a constrained dialog at 600 and above.
/// The decision is made from the window's width, never from the platform.
/// `showUiModal` owns both forms now: the scrim, the entrance, the Escape
/// dismissal, the focus return and the product's own text style all come from
/// the design system rather than from a call site.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The three dialog widths this product uses.
///
/// A dialog that does not fit one of these needs a design decision, not a
/// new number at a call site. The modal frame caps every dialog at
/// `space.dialogMax`, so a width above it is a request for as much room as
/// the system gives.
abstract final class DialogWidths {
  /// A confirmation with no field.
  static const double narrow = 400;

  /// The default. A title, a consequence and one field.
  static const double standard = 480;

  /// A form with a diff, a list of findings, or two columns.
  static const double wide = 640;
}

/// What the scrim behind a modal calls itself.
///
/// The frame's scrim is a control: it closes the modal. Without a name it is
/// a tappable node with nothing to say, which `labeledTapTargetGuideline`
/// rightly refuses. The modal's own name is on the route node beside it, so
/// one word is the whole of what this has to say.
const String modalDismissLabel = 'Close';

/// What a form calls itself to a screen reader when the caller says nothing.
///
/// Every form in this slot names itself. The fallback exists for the two
/// call sites in other slots, which pass a title of their own inside the
/// body rather than to the route.
const String adaptiveFormLabel = 'Form';

/// Shows [builder] as a sheet on a compact window and as a dialog everywhere
/// else.
///
/// [width] applies to the dialog form only; the sheet is always full width.
/// Set [dismissible] to false when the form has unsaved input, and handle the
/// refusal inside [builder] with a `PopScope`. [semanticsLabel] names the
/// route, which is what a screen reader announces on the way in.
Future<T?> showAdaptiveForm<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  double width = DialogWidths.standard,
  bool dismissible = true,
  String? semanticsLabel,
}) {
  final bool sheet = isCompactWindow(context);
  return showUiModal<T>(
    context: context,
    semanticsLabel: semanticsLabel ?? adaptiveFormLabel,
    dismissLabel: modalDismissLabel,
    dismissible: dismissible,
    builder: (BuildContext modalContext) =>
        _FormPane(width: sheet ? null : width, child: builder(modalContext)),
  );
}

/// A titled modal: a sheet on a compact window and a dialog on a wider one,
/// whose [body] owns its own scroll view.
///
/// This is `UiDialog.showAdaptive` with one thing changed: the sheet form does
/// not scroll its own body. Every form in this product is long enough to
/// scroll and the dialog form has no scroll view of its own, so the body
/// carries one; letting the sheet add a second would hand the inner one an
/// unbounded main axis. The package API that would retire this is a
/// `scrollBody` parameter on `UiDialog.showAdaptive`.
Future<T?> showAdaptiveModal<T>(
  BuildContext context, {
  required String title,
  required WidgetBuilder body,
  UiModalActionBuilder? primaryAction,
  UiModalActionBuilder? secondaryAction,
  String? semanticsLabel,
  bool dismissible = true,
}) => isCompactWindow(context)
    ? UiSheet.show<T>(
        context: context,
        title: title,
        body: body,
        primaryAction: primaryAction,
        secondaryAction: secondaryAction,
        semanticsLabel: semanticsLabel ?? title,
        dismissLabel: modalDismissLabel,
        dismissible: dismissible,
        scrollBody: false,
      )
    : UiDialog.show<T>(
        context: context,
        title: title,
        body: body,
        primaryAction: primaryAction,
        secondaryAction: secondaryAction,
        semanticsLabel: semanticsLabel ?? title,
        dismissLabel: modalDismissLabel,
        dismissible: dismissible,
      );

/// The pane a form is drawn in: its width on a wide window, and its clearance
/// above the software keyboard on every window.
///
/// The modal frame is inside a `SafeArea`, which reads the display's own
/// padding and not the keyboard's inset, so a form with a field in it would
/// otherwise be typed into from behind the keyboard.
class _FormPane extends StatelessWidget {
  const _FormPane({required this.width, required this.child});

  final double? width;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final double keyboard = MediaQuery.viewInsetsOf(context).bottom;
    final Widget lifted = keyboard == 0
        ? child
        : Padding(
            padding: EdgeInsets.only(bottom: keyboard),
            child: child,
          );
    final double? cap = width;
    if (cap == null) return lifted;
    return ConstrainedBox(
      constraints: BoxConstraints(maxWidth: cap),
      child: lifted,
    );
  }
}
