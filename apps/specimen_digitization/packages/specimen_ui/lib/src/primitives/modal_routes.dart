/// Sheets and dialogs (10 section 3, `ModalRoutes`).
///
/// A sheet on a compact window, a dialog above it, and one call that picks
/// between them by window class. Both are `glass.modal` over a `Scrim`, both
/// trap focus, and both collapse their entrance under reduced motion.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../foundation/glass.dart';
import '../foundation/motion.dart';
import '../foundation/theme.dart';
import '../foundation/window.dart';
import 'frame_safe_notifier.dart';
import 'glass_surface.dart';
import 'scrim.dart';

/// Where the modals of this package say that one of them is open, and what a
/// frame reads to draw solid beneath it (13 section 2.2; 09 section 3.3).
///
/// A sheet or a dialog is pushed on the root navigator over the whole frame,
/// and nothing beneath a route can read the route above it. So [showUiSheet],
/// [showUiDialog] and [showUiModal] find the nearest scope above the context
/// they were shown from, hold it while the route is over the page, and give
/// it back when the route leaves. A frame publishes one to its page with
/// [publish] and reads [isOpen] to draw its own panes solid while a modal
/// covers them: a pane under a scrim is a save layer nobody sees, and 09
/// section 3.3 counts the modal's own pane within the window's budget.
///
/// Held from the moment the entrance has finished until the moment the exit
/// begins, so both changes happen under a scrim that is fully drawn rather
/// than one that is still fading; under reduced motion both are instant.
///
/// Null outside a frame, so a modal shown from a component test, or from above
/// the scaffold, changes nothing.
class UiModalScope extends ChangeNotifier with FrameSafeNotifier {
  int _open = 0;

  /// True while a modal shown from inside this scope is over the page.
  bool get isOpen => _open > 0;

  void _enter() {
    _open++;
    if (_open == 1) announce();
  }

  void _leave() {
    assert(_open > 0, 'a modal left a scope it never entered');
    _open--;
    if (_open == 0) announce();
  }

  /// The nearest scope above [context], or null when there is none.
  ///
  /// Reads without depending: a route wants the object, not a rebuild.
  static UiModalScope? of(BuildContext context) =>
      context.getInheritedWidgetOfExactType<_UiModalScopeScope>()?.scope;

  /// Publishes [scope] to [child]. What a frame wraps its page in.
  static Widget publish({required UiModalScope scope, required Widget child}) =>
      _UiModalScopeScope(scope: scope, child: child);
}

/// Publishes one frame's modal scope to its page.
class _UiModalScopeScope extends InheritedWidget {
  const _UiModalScopeScope({required this.scope, required super.child});

  final UiModalScope scope;

  @override
  bool updateShouldNotify(_UiModalScopeScope oldWidget) =>
      oldWidget.scope != scope;
}

/// One route's hold on a [UiModalScope]: entered when the entrance has
/// finished, left when the exit begins, and never left without having
/// entered.
class _ModalPresence {
  _ModalPresence(this.scope, this.animation) {
    // Under reduced motion the entrance is instant and has already completed
    // inside the push, so the status listener would never fire.
    if (animation.isCompleted) {
      _enter();
    } else {
      animation.addStatusListener(_status);
    }
  }

  final UiModalScope scope;
  final Animation<double> animation;
  bool _entered = false;
  bool _left = false;

  void _status(AnimationStatus status) {
    if (status == AnimationStatus.completed) _enter();
  }

  void _enter() {
    if (_entered || _left) return;
    _entered = true;
    animation.removeStatusListener(_status);
    scope._enter();
  }

  /// The route is leaving. A route dismissed before its entrance finished
  /// never held the scope and gives nothing back.
  void leave() {
    if (_left) return;
    _left = true;
    animation.removeStatusListener(_status);
    if (_entered) scope._leave();
  }
}

/// The width below which a window gets a sheet rather than a dialog.
///
/// [WindowClass.mediumMin] itself, not a second copy of it. It was restated
/// here while the classes lived in the application, because the path
/// dependency points one way; they are in the foundation now (11 section
/// 3.1), so the breakpoint is written down once.
const double compactWindowMax = WindowClass.mediumMin;

/// True when [context] is painted into a compact window.
bool isCompactWindow(BuildContext context) => WindowClass.of(context).isCompact;

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
  // The frame this modal is shown from inside, if any. Read from the caller's
  // context, because the route itself is built in the navigator's overlay,
  // above every frame.
  final UiModalScope? scope = UiModalScope.of(context);
  // Focus returns to whatever opened the modal, which is clause 3 of the
  // control contract. The route's own scope restoration returns to the page's
  // focus scope rather than to the control inside it, so the node is captured
  // here and asked for focus back when the route completes.
  final FocusNode? trigger = FocusManager.instance.primaryFocus;
  final RawDialogRoute<T> route = RawDialogRoute<T>(
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
          final Widget faded = FadeTransition(opacity: curved, child: child);
          // Under reduced motion the pane appears without travel, which is
          // what 04 section 2.5 collapses a sheet to. The fade stays,
          // because a fade is not motion.
          if (context.ui.motion.reduced) return faded;
          return SlideTransition(
            position: Tween<Offset>(
              begin: sheet
                  ? const Offset(0, MotionTokens.sheetEntranceRise)
                  : const Offset(0, MotionTokens.dialogEntranceRise),
              end: Offset.zero,
            ).animate(curved),
            child: faded,
          );
        },
  );
  // `push` returns the future of the pop, which is the moment the exit
  // begins: the frame beneath gets its panes back while the scrim is still
  // fully drawn.
  final Future<T?> popped = navigator.push<T>(route);
  final _ModalPresence? presence = scope == null
      ? null
      : _ModalPresence(scope, route.animation!);
  return popped.whenComplete(() {
    presence?.leave();
    if (trigger?.context?.mounted ?? false) trigger!.requestFocus();
  });
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

    // Escape dismisses the modal, per clause 3 of the control contract. The
    // route draws its own scrim rather than the barrier `RawDialogRoute`
    // would, so nothing else in the tree is listening for the key.
    return Shortcuts(
      shortcuts: const <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.escape): DismissIntent(),
      },
      child: Actions(
        actions: <Type, Action<Intent>>{
          DismissIntent: CallbackAction<DismissIntent>(
            onInvoke: (DismissIntent intent) {
              if (dismissible) close();
              return null;
            },
          ),
        },
        child: _frame(context, ui, close),
      ),
    );
  }

  /// The scrim, the focus trap and the pane.
  Widget _frame(BuildContext context, UiThemeData ui, VoidCallback close) {
    // The pane is a route on the root navigator, so it is published wherever
    // that navigator's overlay sits rather than under whatever wrapped the
    // control that opened it. Publishing the style here makes the frame
    // correct in any host, including a bare `WidgetsApp` and a host that
    // resets the style below `UiTheme` (11 section 5).
    final Widget pane = DefaultTextStyle(
      style: ui.defaultTextStyle,
      child: GlassSurface(
        level: GlassLevel.modal,
        radius: ui.shape.sheet,
        // A sheet meets the bottom of the window, so only its top corners
        // turn (10 section 4.3). A dialog floats, so all four do.
        corners: sheet
            ? BorderRadius.vertical(top: Radius.circular(ui.shape.sheet))
            : null,
        child: builder(context),
      ),
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
                alignment: sheet ? Alignment.bottomCenter : Alignment.center,
                child: Padding(
                  padding: EdgeInsets.all(sheet ? 0 : ui.space.s4),
                  child: ConstrainedBox(
                    // A sheet fills the window's width; a dialog shrink wraps
                    // up to 560. `minWidth: infinity` is the idiom for "as
                    // wide as the parent allows", because `ConstrainedBox`
                    // enforces against the incoming constraints.
                    constraints: BoxConstraints(
                      minWidth: sheet ? double.infinity : 0,
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
