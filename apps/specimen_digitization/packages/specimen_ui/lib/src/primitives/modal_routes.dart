/// Sheets and dialogs (10 section 3, `ModalRoutes`).
///
/// A sheet on a compact window, a dialog above it, and one call that picks
/// between them by window class. Both are `glass.modal` over a `Scrim`, both
/// trap focus, and both collapse their entrance under reduced motion.
library;

import 'package:flutter/widgets.dart';

import '../foundation/glass.dart';
import '../foundation/motion.dart';
import '../foundation/theme.dart';
import 'glass_surface.dart';
import 'scrim.dart';

/// The width below which a window gets a sheet rather than a dialog.
///
/// The application's `WindowClass.mediumMin` is the same 600 (05 section 2).
/// It is restated here rather than imported because the package cannot import
/// the application: the path dependency points one way, and importing upward
/// would invert the layering the `layering` gate holds. The two values are
/// pinned together by a test in the application.
const double compactWindowMax = 600;

/// True when [context] is painted into a compact window.
bool isCompactWindow(BuildContext context) =>
    MediaQuery.sizeOf(context).width < compactWindowMax;

/// Shows [builder] as a bottom sheet.
///
/// Returns the value the sheet was closed with, or null when it was
/// dismissed.
Future<T?> showUiSheet<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  required String semanticsLabel,
  String? dismissLabel,
  bool dismissible = true,
}) => _show<T>(
  context: context,
  builder: builder,
  semanticsLabel: semanticsLabel,
  dismissLabel: dismissLabel,
  dismissible: dismissible,
  sheet: true,
);

/// Shows [builder] as a centred dialog, at most 560 logical pixels wide.
Future<T?> showUiDialog<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  required String semanticsLabel,
  String? dismissLabel,
  bool dismissible = true,
}) => _show<T>(
  context: context,
  builder: builder,
  semanticsLabel: semanticsLabel,
  dismissLabel: dismissLabel,
  dismissible: dismissible,
  sheet: false,
);

/// Shows [builder] as a sheet on a compact window and a dialog above it.
///
/// One call, so a caller never writes the breakpoint itself (05 section 3.7).
Future<T?> showUiModal<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  required String semanticsLabel,
  String? dismissLabel,
  bool dismissible = true,
}) => _show<T>(
  context: context,
  builder: builder,
  semanticsLabel: semanticsLabel,
  dismissLabel: dismissLabel,
  dismissible: dismissible,
  sheet: isCompactWindow(context),
);

Future<T?> _show<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  required String semanticsLabel,
  required String? dismissLabel,
  required bool dismissible,
  required bool sheet,
}) {
  final UiThemeData ui = context.ui;
  final NavigatorState navigator = Navigator.of(context, rootNavigator: true);
  return navigator.push<T>(
    RawDialogRoute<T>(
      barrierDismissible: false,
      barrierColor: null,
      transitionDuration: ui.motion.emphasized,
      // The route owns the scrim so that the scrim fades with the pane rather
      // than snapping, and so that a caller cannot forget it.
      pageBuilder:
          (
            BuildContext context,
            Animation<double> animation,
            Animation<double> secondary,
          ) => _ModalFrame(
            sheet: sheet,
            semanticsLabel: semanticsLabel,
            dismissLabel: dismissLabel,
            dismissible: dismissible,
            builder: builder,
          ),
      transitionBuilder:
          (
            BuildContext context,
            Animation<double> animation,
            Animation<double> secondary,
            Widget child,
          ) {
            final CurvedAnimation curved = CurvedAnimation(
              parent: animation,
              curve: MotionTokens.emphasizedEnterCurve,
              reverseCurve: MotionTokens.emphasizedExitCurve,
            );
            final Widget faded = FadeTransition(
              opacity: curved,
              child: child,
            );
            // Under reduced motion the pane appears without travel, which is
            // what 04 section 2.5 collapses a sheet to. The fade stays,
            // because a fade is not motion.
            if (context.ui.motion.reduced) return faded;
            return SlideTransition(
              position: Tween<Offset>(
                begin: sheet ? const Offset(0, 0.08) : const Offset(0, 0.02),
                end: Offset.zero,
              ).animate(curved),
              child: faded,
            );
          },
    ),
  );
}

/// The chrome around a modal: the scrim, the focus trap and the pane.
class _ModalFrame extends StatelessWidget {
  const _ModalFrame({
    required this.sheet,
    required this.semanticsLabel,
    required this.dismissLabel,
    required this.dismissible,
    required this.builder,
  });

  final bool sheet;
  final String semanticsLabel;
  final String? dismissLabel;
  final bool dismissible;
  final WidgetBuilder builder;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    void close() => Navigator.of(context).maybePop();
    final Widget pane = GlassSurface(
      level: GlassLevel.modal,
      radius: ui.shape.sheet,
      child: builder(context),
    );

    return PopScope(
      canPop: dismissible,
      child: Stack(
        children: <Widget>[
          Positioned.fill(
            child: Scrim(
              onDismiss: dismissible ? close : null,
              dismissLabel: dismissLabel,
            ),
          ),
          Positioned.fill(
            child: SafeArea(
              child: Align(
                alignment: sheet
                    ? Alignment.bottomCenter
                    : Alignment.center,
                child: Padding(
                  padding: EdgeInsets.all(sheet ? 0 : ui.space.s4),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      maxWidth: sheet ? double.infinity : ui.space.dialogMax,
                    ),
                    child: FocusScope(
                      autofocus: true,
                      child: Semantics(
                        container: true,
                        scopesRoute: true,
                        explicitChildNodes: true,
                        namesRoute: true,
                        label: semanticsLabel,
                        child: pane,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
