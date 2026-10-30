/// Retained workspace panels with one responsive docking and dismissal policy.
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/layout.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';

/// Whether a workspace panel shares space or temporarily covers the workspace.
enum UiSidePanelMode {
  /// The panel reserves space beside the body; both remain interactive.
  docked,

  /// The body retains its full width beneath a dismissible modal scrim.
  overlay,
}

/// A panel's placement, resolved from its actual content allocation.
@immutable
class UiSidePanelLayout {
  const UiSidePanelLayout._({required this.mode, required this.width});

  /// Docks only when the body retains its requested readable minimum.
  ///
  /// [availableWidth] excludes any permanent navigation. An overlay leaves a
  /// small exposed dismissal area where possible, rather than squeezing its
  /// controls into the remaining width beside the body.
  factory UiSidePanelLayout.resolve({
    required double availableWidth,
    required double panelWidth,
    required double minBodyWidth,
  }) {
    assert(availableWidth.isFinite && availableWidth >= 0);
    assert(panelWidth.isFinite && panelWidth > 0);
    assert(minBodyWidth.isFinite && minBodyWidth > 0);
    final docked = availableWidth >= panelWidth + minBodyWidth;
    final available = docked
        ? availableWidth
        : math.max(0.0, availableWidth - UiLayoutMetrics.grid * 6);
    return UiSidePanelLayout._(
      mode: docked ? UiSidePanelMode.docked : UiSidePanelMode.overlay,
      width: math.min(panelWidth, available),
    );
  }

  /// How the panel shares the available workspace.
  final UiSidePanelMode mode;

  /// The panel's bounded width, independent of its reveal progress.
  final double width;
}

/// A retained panel beside one stable workspace subtree.
///
/// The panel reveals at its full content width, so its fields and rows do not
/// wrap through every animation frame. The body and panel stay mounted across
/// open/close and dock/overlay changes, retaining drafts, scroll and selection.
///
/// Put permanent navigation in [leading] and the page scaffold in [child]. An
/// overlay then covers and excludes the complete background, including that
/// navigation, from pointer, focus and accessibility interaction. Dismissal
/// returns focus to the opener only when focus was still within the panel.
///
/// The host owns [open] and content state. Closing never saves or discards a
/// form. A null [panel] removes the optional surface without moving [child].
class UiSidePanel extends StatefulWidget {
  /// Builds a workspace panel within finite parent constraints.
  const UiSidePanel({
    super.key,
    required this.open,
    required this.mode,
    required this.width,
    required this.panel,
    required this.child,
    required this.onDismiss,
    this.leading,
    this.leadingWidth = 0,
    this.initialFocusNode,
    this.semanticsLabel = 'Side panel',
    this.dismissLabel = 'Close panel',
  }) : assert(width >= 0),
       assert(leadingWidth >= 0);

  /// Whether the optional panel is open.
  final bool open;

  /// Docked on a roomy workspace; modal where a second pane would crowd it.
  final UiSidePanelMode mode;

  /// Panel content width. Use [UiSidePanelLayout] to bound this to the parent.
  final double width;

  /// Retained panel contents, or null when this route has no panel.
  final Widget? panel;

  /// The workspace, kept at one position in the widget tree.
  final Widget child;

  /// Requests a close; the host updates [open].
  final VoidCallback onDismiss;

  /// Permanent navigation outside the optional panel.
  final Widget? leading;

  /// Width reserved for [leading], normally the sidebar's measured width.
  final double leadingWidth;

  /// Preferred focus target after an explicit open, such as panel search.
  final FocusNode? initialFocusNode;

  /// Accessible name for the panel's scope.
  final String semanticsLabel;

  /// Accessible name for scrim dismissal.
  final String dismissLabel;

  @override
  State<UiSidePanel> createState() => _UiSidePanelState();
}

class _UiSidePanelState extends State<UiSidePanel>
    with SingleTickerProviderStateMixin {
  late final AnimationController _reveal = AnimationController(
    vsync: this,
    value: _open ? 1 : 0,
  );
  final FocusScopeNode _panelFocus = FocusScopeNode(debugLabel: 'Side panel');
  final FocusScopeNode _bodyFocus = FocusScopeNode(
    debugLabel: 'Workspace body',
    traversalEdgeBehavior: TraversalEdgeBehavior.parentScope,
  );
  FocusNode? _returnFocus;
  int _focusGeneration = 0;
  bool _pendingRestore = false;

  bool get _open => widget.open && widget.panel != null;
  bool get _modal => _open && widget.mode == UiSidePanelMode.overlay;
  bool get _covered =>
      widget.mode == UiSidePanelMode.overlay && (_open || !_reveal.isDismissed);

  @override
  void initState() {
    super.initState();
    _reveal.addStatusListener(_revealStatusChanged);
    // A panel docked by default must not take focus away from the page. A
    // modal open on first build does need to contain focus from the start.
    if (_modal) _focusPanel();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _animate();
    if (_pendingRestore && !_covered) _scheduleRestore(_focusGeneration);
  }

  void _revealStatusChanged(AnimationStatus status) {
    if (status == AnimationStatus.dismissed && _pendingRestore) {
      _scheduleRestore(_focusGeneration);
    }
  }

  @override
  void didUpdateWidget(UiSidePanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    final wasOpen = oldWidget.open && oldWidget.panel != null;
    if (_open && !wasOpen) {
      _focusPanel();
    } else if (!_open && wasOpen) {
      _restoreFocus();
    } else if (_modal && oldWidget.mode != UiSidePanelMode.overlay) {
      // A resize can turn an already-open dock into a modal. Any focus in the
      // newly covered body must enter the modal too.
      if (!_panelFocus.hasFocus) _focusPanel();
    }
    _animate();
    if (_pendingRestore && !_covered) _scheduleRestore(_focusGeneration);
  }

  void _animate() {
    final duration = MotionTokens.of(context).standard;
    _reveal.duration = duration;
    // A route that no longer supplies panel content has nothing to animate.
    // Keeping its old reservation would leave a blank strip beside the new
    // destination until the close animation ended.
    if (widget.panel == null || duration == Duration.zero) {
      _reveal.value = _open ? 1 : 0;
    } else if (_open) {
      _reveal.forward();
    } else {
      _reveal.reverse();
    }
  }

  void _focusPanel() {
    if (!_panelFocus.hasFocus && !_pendingRestore) {
      _returnFocus = FocusManager.instance.primaryFocus;
    }
    _pendingRestore = false;
    final generation = ++_focusGeneration;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_open || generation != _focusGeneration) return;
      final initial = widget.initialFocusNode;
      if (initial?.context != null && initial!.canRequestFocus) {
        initial.requestFocus();
      } else {
        _panelFocus.requestFocus();
      }
    });
  }

  void _restoreFocus() {
    _pendingRestore = _panelFocus.hasFocus;
    if (!_pendingRestore) _returnFocus = null;
    final generation = ++_focusGeneration;
    _scheduleRestore(generation);
  }

  void _scheduleRestore(int generation) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          _open ||
          generation != _focusGeneration ||
          !_pendingRestore ||
          _covered) {
        return;
      }
      final previous = _returnFocus;
      _returnFocus = null;
      _pendingRestore = false;
      if (previous?.context != null && previous!.canRequestFocus) {
        previous.requestFocus();
      } else if (_bodyFocus.context != null && _bodyFocus.canRequestFocus) {
        // A dock open by default has no opener to remember. Return to the
        // body's remembered control, or its first traversable control, rather
        // than leaving keyboard focus on a hidden panel or a page container.
        final policy = FocusTraversalGroup.of(_bodyFocus.context!);
        final target = policy.findFirstFocus(
          _bodyFocus,
          ignoreCurrentFocus:
              !(_bodyFocus.focusedChild?.canRequestFocus ?? false),
        );
        target?.requestFocus();
      }
    });
  }

  @override
  void dispose() {
    _focusGeneration++;
    _panelFocus.dispose();
    _bodyFocus.dispose();
    _reveal.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    _panelFocus.traversalEdgeBehavior = _modal
        ? TraversalEdgeBehavior.closedLoop
        : TraversalEdgeBehavior.parentScope;
    return AnimatedBuilder(
      animation: _reveal,
      builder: (context, _) {
        final progress = MotionTokens.standardCurve.transform(_reveal.value);
        final reserved = widget.mode == UiSidePanelMode.docked
            ? widget.width * progress
            : 0.0;
        return PopScope<Object?>(
          canPop: !_covered,
          onPopInvokedWithResult: (didPop, result) {
            if (!didPop && _modal) widget.onDismiss();
          },
          child: CallbackShortcuts(
            bindings: {
              if (_open)
                const SingleActivator(LogicalKeyboardKey.escape):
                    widget.onDismiss,
            },
            child: ClipRect(
              child: Stack(
                fit: StackFit.expand,
                children: [
                  IgnorePointer(
                    ignoring: _covered,
                    child: ExcludeFocus(
                      excluding: _covered,
                      child: ExcludeSemantics(
                        excluding: _covered,
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            SizedBox(
                              width: widget.leadingWidth,
                              child: widget.leading,
                            ),
                            Expanded(
                              child: Padding(
                                padding: EdgeInsetsDirectional.only(
                                  start: reserved,
                                ),
                                child: FocusScope(
                                  node: _bodyFocus,
                                  child: widget.child,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  Offstage(
                    offstage: !_covered,
                    child: IgnorePointer(
                      ignoring: !_covered,
                      child: ExcludeSemantics(
                        excluding: !_modal,
                        child: Opacity(
                          opacity: widget.mode == UiSidePanelMode.overlay
                              ? progress
                              : 0,
                          child: ModalBarrier(
                            color: ui.color.scrim,
                            dismissible: _modal,
                            onDismiss: widget.onDismiss,
                            semanticsLabel: widget.dismissLabel,
                          ),
                        ),
                      ),
                    ),
                  ),
                  PositionedDirectional(
                    start: widget.leadingWidth,
                    top: 0,
                    bottom: 0,
                    width: widget.width * progress,
                    child: ClipRect(
                      child: OverflowBox(
                        alignment: AlignmentDirectional.centerStart,
                        minWidth: widget.width,
                        maxWidth: widget.width,
                        child: Offstage(
                          offstage: !_open && _reveal.isDismissed,
                          child: TickerMode(
                            enabled: _open,
                            child: IgnorePointer(
                              ignoring: !_open,
                              child: ExcludeFocus(
                                excluding: !_open,
                                child: ExcludeSemantics(
                                  excluding: !_open,
                                  child: Semantics(
                                    container: true,
                                    explicitChildNodes: true,
                                    scopesRoute: _modal,
                                    namesRoute: _modal,
                                    label: widget.semanticsLabel,
                                    child: FocusScope(
                                      node: _panelFocus,
                                      child: ColoredBox(
                                        color: ui.color.paper,
                                        child: widget.panel,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
