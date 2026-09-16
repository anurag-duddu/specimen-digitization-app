/// The anchored overlay (10 section 3, `Popover`).
///
/// The base of menus, selects, tooltips and date inputs. It positions itself
/// against its trigger, flips when the viewport would clip it, dismisses on an
/// outside tap and on `Escape`, and returns focus to the trigger when it
/// closes.
library;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../foundation/glass.dart';
import '../foundation/motion.dart';
import '../foundation/theme.dart';
import 'glass_surface.dart';

/// Where a popover sits relative to its trigger.
enum PopoverPlacement {
  /// Above the trigger.
  above,

  /// Below the trigger.
  below,

  /// Before the trigger in the reading direction.
  start,

  /// After the trigger in the reading direction.
  end,

  /// Below the trigger, flipping above when the viewport would clip it.
  auto,
}

/// Opens and closes one popover.
class PopoverController extends ChangeNotifier {
  bool _open = false;

  /// True while the popover is on screen.
  bool get isOpen => _open;

  /// Shows the popover.
  void open() {
    if (_open) return;
    _open = true;
    notifyListeners();
  }

  /// Hides the popover and returns focus to the trigger.
  void close() {
    if (!_open) return;
    _open = false;
    notifyListeners();
  }

  /// Shows the popover when it is hidden and hides it when it is shown.
  void toggle() => _open ? close() : open();
}

/// An overlay anchored to a trigger.
class Popover extends StatefulWidget {
  /// Anchors [overlayBuilder] to [child], under [controller].
  const Popover({
    super.key,
    required this.controller,
    required this.child,
    required this.overlayBuilder,
    this.placement = PopoverPlacement.auto,
    this.gap,
    this.level = GlassLevel.floating,
    this.radius,
    this.semanticsLabel,
    this.barrierDismissible = true,
  });

  /// Opens and closes this popover.
  final PopoverController controller;

  /// The trigger. Focus returns here when the popover closes.
  final Widget child;

  /// The popover's content.
  final WidgetBuilder overlayBuilder;

  /// Where the popover sits.
  final PopoverPlacement placement;

  /// The distance between the trigger and the popover. Defaults to `s2`.
  final double? gap;

  /// Which glass level the pane carries.
  final GlassLevel level;

  /// The pane's corner radius. Defaults to `radius.tile`.
  final double? radius;

  /// The label a screen reader reads for the popover itself.
  final String? semanticsLabel;

  /// True when a tap outside closes the popover.
  final bool barrierDismissible;

  @override
  State<Popover> createState() => _PopoverState();
}

class _PopoverState extends State<Popover> {
  final OverlayPortalController _portal = OverlayPortalController();
  final LayerLink _link = LayerLink();
  final FocusScopeNode _scope = FocusScopeNode(debugLabel: 'Popover');
  FocusNode? _triggerFocus;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_controllerChanged);
    if (widget.controller.isOpen) _portal.show();
  }

  @override
  void didUpdateWidget(Popover oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller.removeListener(_controllerChanged);
      widget.controller.addListener(_controllerChanged);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_controllerChanged);
    _scope.dispose();
    super.dispose();
  }

  void _controllerChanged() {
    if (!mounted) return;
    if (widget.controller.isOpen) {
      _triggerFocus = FocusManager.instance.primaryFocus;
      _portal.show();
    } else {
      _portal.hide();
      // Focus returns to the trigger, which is clause 3 of the control
      // contract: Escape dismisses an overlay and returns focus to what
      // opened it.
      _triggerFocus?.requestFocus();
      _triggerFocus = null;
    }
  }

  void _close() => widget.controller.close();

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // The shortcut wraps the trigger as well as the pane. Escape pressed
    // immediately after opening, while focus is still on the trigger, has to
    // close the popover: a reviewer does not know which side of the boundary
    // their focus is on.
    return Shortcuts(
      shortcuts: const <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.escape): DismissIntent(),
      },
      child: Actions(
        actions: <Type, Action<Intent>>{
          DismissIntent: CallbackAction<DismissIntent>(
            onInvoke: (DismissIntent intent) {
              if (widget.controller.isOpen) _close();
              return null;
            },
          ),
        },
        child: _buildPortal(context, ui),
      ),
    );
  }

  Widget _buildPortal(BuildContext context, UiThemeData ui) {
    return OverlayPortal(
      controller: _portal,
      overlayChildBuilder: (BuildContext overlayContext) => Positioned.fill(
        child: Stack(
          children: <Widget>[
            if (widget.barrierDismissible)
              Positioned.fill(
                child: GestureDetector(
                  behavior: HitTestBehavior.translucent,
                  excludeFromSemantics: true,
                  onTap: _close,
                ),
              ),
            CompositedTransformFollower(
              link: _link,
              showWhenUnlinked: false,
              targetAnchor: _targetAnchor,
              followerAnchor: _followerAnchor,
              offset: _offset(ui),
              child: Align(
                alignment: _followerAnchor,
                child: TapRegion(
                  onTapOutside: widget.barrierDismissible
                      ? (PointerDownEvent _) => _close()
                      : null,
                  child: FocusScope(
                    node: _scope,
                    autofocus: true,
                    child: Semantics(
                      container: true,
                      label: widget.semanticsLabel,
                      explicitChildNodes: true,
                      child: _PopoverPane(
                        level: widget.level,
                        radius: widget.radius,
                        child: Builder(builder: widget.overlayBuilder),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
      child: CompositedTransformTarget(link: _link, child: widget.child),
    );
  }

  /// Auto is below unless the trigger is in the bottom third of the window,
  /// which is the flip 10 section 3 asks for. Computed from the window rather
  /// than from a measured overlay, so it never needs a second layout pass.
  PopoverPlacement get _resolved {
    if (widget.placement != PopoverPlacement.auto) return widget.placement;
    final RenderObject? box = context.findRenderObject();
    final Size window = MediaQuery.sizeOf(context);
    if (box is! RenderBox || !box.hasSize) return PopoverPlacement.below;
    final double top = box.localToGlobal(Offset.zero).dy;
    return top > window.height * 2 / 3
        ? PopoverPlacement.above
        : PopoverPlacement.below;
  }

  Alignment get _targetAnchor => switch (_resolved) {
    PopoverPlacement.above => Alignment.topLeft,
    PopoverPlacement.below || PopoverPlacement.auto => Alignment.bottomLeft,
    PopoverPlacement.start => Alignment.centerLeft,
    PopoverPlacement.end => Alignment.centerRight,
  };

  Alignment get _followerAnchor => switch (_resolved) {
    PopoverPlacement.above => Alignment.bottomLeft,
    PopoverPlacement.below || PopoverPlacement.auto => Alignment.topLeft,
    PopoverPlacement.start => Alignment.centerRight,
    PopoverPlacement.end => Alignment.centerLeft,
  };

  Offset _offset(UiThemeData ui) {
    final double gap = widget.gap ?? ui.space.s2;
    return switch (_resolved) {
      PopoverPlacement.above => Offset(0, -gap),
      PopoverPlacement.below || PopoverPlacement.auto => Offset(0, gap),
      PopoverPlacement.start => Offset(-gap, 0),
      PopoverPlacement.end => Offset(gap, 0),
    };
  }
}

/// The pane itself, faded in at the standard duration.
class _PopoverPane extends StatelessWidget {
  const _PopoverPane({
    required this.level,
    required this.radius,
    required this.child,
  });

  final GlassLevel level;
  final double? radius;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: 0, end: 1),
      duration: ui.motion.standard,
      curve: MotionTokens.enterCurve,
      builder: (BuildContext context, double t, Widget? pane) =>
          Opacity(opacity: t, child: pane),
      child: GlassSurface(level: level, radius: radius, child: child),
    );
  }
}
