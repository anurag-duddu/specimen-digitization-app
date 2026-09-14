/// One entry point for every modal that collects something
/// (design system, 7.3 `ReasonSheet`; motion, catalog rows 26, 47 and 48).
///
/// A modal bottom sheet below 600 logical pixels and a constrained dialog at
/// 600 and above. The decision is made from the window's width, never from the
/// platform. Both forms are raised off Flutter's 150 ms dialog default onto the
/// motion tokens, and both collapse to no travel under reduced motion.
library;

import 'package:flutter/material.dart';

import '../layout/window_class.dart';
import '../theme/icons.dart';
import '../theme/motion.dart';

/// The three dialog widths this product uses.
///
/// A dialog that does not fit one of these needs a design decision, not a
/// new number at a call site.
abstract final class DialogWidths {
  /// A confirmation with no field.
  static const double narrow = 400;

  /// The default. A title, a consequence and one field.
  static const double standard = 480;

  /// A form with a diff, a list of findings, or two columns.
  static const double wide = 640;
}

/// Shows [builder] as a bottom sheet on a compact window and as a dialog
/// everywhere else.
///
/// [width] applies to the dialog form only; the sheet is always full width.
/// Set [dismissible] to false when the form has unsaved input, and handle the
/// refusal inside [builder] with a `PopScope`.
Future<T?> showAdaptiveForm<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  double width = DialogWidths.standard,
  bool dismissible = true,
}) {
  final bool compact = WindowClass.of(context).isCompact;
  final MotionTokens motion = context.motion;
  final double sheetRadius = context.shape.radiusLg;
  final double dialogRadius = context.shape.radiusMd;

  if (compact) {
    return showModalBottomSheet<T>(
      context: context,
      isScrollControlled: true,
      isDismissible: dismissible,
      enableDrag: dismissible,
      useSafeArea: true,
      showDragHandle: dismissible,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(sheetRadius)),
      ),
      sheetAnimationStyle: AnimationStyle(
        duration: motion.emphasized,
        curve: MotionTokens.emphasizedEnterCurve,
        reverseDuration: motion.standard,
        reverseCurve: MotionTokens.emphasizedExitCurve,
      ),
      builder: (BuildContext sheetContext) => Padding(
        // Lift the sheet clear of the software keyboard.
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(sheetContext).bottom,
        ),
        child: builder(sheetContext),
      ),
    );
  }

  return showDialog<T>(
    context: context,
    barrierDismissible: dismissible,
    animationStyle: AnimationStyle(
      duration: motion.standard,
      curve: MotionTokens.standardCurve,
      reverseDuration: motion.quick,
      reverseCurve: MotionTokens.exitCurve,
    ),
    builder: (BuildContext dialogContext) => Dialog(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(dialogRadius),
      ),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: width),
        child: builder(dialogContext),
      ),
    ),
  );
}
