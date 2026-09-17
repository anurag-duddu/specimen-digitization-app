/// The anchored overlay (10 section 3, `Popover`).
///
/// The base of menus, selects, tooltips and date inputs. It positions itself
/// against its trigger, fits the overlay it opens in, dismisses on an outside
/// tap and on `Escape`, and returns focus to the trigger when it closes.
///
/// **Fit.** A pane below or above its trigger hangs from the trigger's
/// leading edge. Where that would carry it past the overlay's trailing edge,
/// the anchor mirrors and the pane hangs from the trailing edge instead, and
/// where neither edge holds it the pane is clamped inside the overlay's
/// padding: the safe area plus `space.s4` on each side, except that a pane may
/// come as close to an edge as its own trigger does, so a select flush with
/// the window keeps its list flush under it. The vertical rule is unchanged:
/// `auto` opens below and flips above when the trigger is in the bottom third.
/// Slot A3 measured the defect this closes on a record's bar at 800 dp: a
/// trigger at 736 to 784 opened its menu at 788 to 1036.
///
/// The overlay rather than the window, because the overlay is the only place
/// the pane can be drawn: in the application the two are the same rectangle,
/// and a gallery frame with an `Overlay` of its own is measured against the
/// frame.
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../foundation/glass.dart';
import '../foundation/motion.dart';
import '../foundation/theme.dart';
import 'glass_surface.dart';
import 'surface.dart';

/// What a popover's pane is painted on.
enum PopoverSurface {
  /// Frosted glass at the popover's level. Menus, selects and date inputs.
  glass,

  /// A solid `paper` pane with a `boundary` edge.
  ///
  /// Tooltips are small and frequent, and a save layer each is a cost the
  /// budget in 09 section 3.3 does not have room for (10 section 4.3).
  paper,
}

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
    this.surface = PopoverSurface.glass,
    this.interactive = true,
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

  /// Which glass level the pane carries. Ignored on a [PopoverSurface.paper]
  /// pane.
  final GlassLevel level;

  /// What the pane is painted on.
  final PopoverSurface surface;

  /// True when the pane takes focus and receives pointer events.
  ///
  /// A menu or a select is interactive: the reviewer moves into it and picks
  /// something. A tooltip is not. It describes the control under the pointer,
  /// so taking focus would move the reviewer away from that control, and
  /// receiving pointer events would swallow the click they were about to
  /// make on it.
  final bool interactive;

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
      if (widget.interactive) {
        _triggerFocus = FocusManager.instance.primaryFocus;
      }
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
      overlayChildBuilder: (BuildContext overlayContext) {
        final _PopoverGeometry geometry = _geometry(ui);
        return Positioned.fill(
          child: Stack(
            children: <Widget>[
              if (widget.barrierDismissible && widget.interactive)
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
                targetAnchor: Alignment.topLeft,
                followerAnchor: Alignment.topLeft,
                // The follower's origin is the overlay's origin: the trigger's
                // own offset is taken back out, so the layout below works in
                // the overlay's coordinates while the pane still follows a
                // trigger that moves.
                offset: -geometry.trigger.topLeft,
                child: CustomSingleChildLayout(
                  delegate: _PopoverLayout(geometry),
                  child: _pane(context),
                ),
              ),
            ],
          ),
        );
      },
      child: CompositedTransformTarget(link: _link, child: widget.child),
    );
  }

  /// Where the trigger sits in the overlay the pane is drawn in, and what the
  /// pane has to fit.
  ///
  /// Read at build time, as the vertical rule always was: the pane follows a
  /// trigger that scrolls through the layer link, and the anchor it hangs from
  /// is decided when it opens.
  _PopoverGeometry _geometry(UiThemeData ui) {
    final OverlayState overlay = Overlay.of(context);
    final RenderObject? theaterObject = overlay.context.findRenderObject();
    final RenderBox? theater =
        theaterObject is RenderBox && theaterObject.hasSize
        ? theaterObject
        : null;
    final RenderObject? triggerObject = context.findRenderObject();
    final RenderBox? trigger =
        triggerObject is RenderBox && triggerObject.hasSize
        ? triggerObject
        : null;
    // A fresh `Size`: a render box's own is a debug tracked value that may not
    // be handed to another box as its size.
    final Size bounds = theater == null
        ? MediaQuery.sizeOf(context)
        : Size(theater.size.width, theater.size.height);
    final Rect anchor = trigger == null
        ? Rect.zero
        : trigger.localToGlobal(Offset.zero, ancestor: theater) & trigger.size;
    // The overlay's own padding, read without depending: the window's safe
    // area reaches the overlay whole, where a scaffold has already taken it
    // out of the page beneath it.
    final EdgeInsets safe =
        overlay.context
            .getInheritedWidgetOfExactType<MediaQuery>()
            ?.data
            .padding ??
        EdgeInsets.zero;
    return _PopoverGeometry(
      trigger: anchor,
      bounds: bounds,
      placement: _resolve(widget.placement, anchor, bounds),
      gap: widget.gap ?? ui.space.s2,
      insetStart: safe.left + ui.space.s4,
      insetEnd: safe.right + ui.space.s4,
      direction: Directionality.of(context),
    );
  }

  /// Auto is below unless the trigger is in the bottom third of the overlay,
  /// which is the flip 10 section 3 asks for. Computed from the trigger's
  /// place rather than from a measured pane, so it never needs a second
  /// layout pass.
  static PopoverPlacement _resolve(
    PopoverPlacement placement,
    Rect trigger,
    Size bounds,
  ) {
    if (placement != PopoverPlacement.auto) return placement;
    return trigger.top > bounds.height * 2 / 3
        ? PopoverPlacement.above
        : PopoverPlacement.below;
  }

  /// The pane, with the focus scope and the tap region an interactive
  /// popover needs and a passive one must not have.
  Widget _pane(BuildContext context) {
    // An `OverlayPortal` builds its child under the overlay, not under the
    // trigger, so the pane inherits whatever text style the overlay sits in.
    // Publishing it here makes the pane correct in any host (11 section 5).
    final Widget content = DefaultTextStyle(
      style: context.ui.defaultTextStyle,
      child: Semantics(
        container: true,
        label: widget.semanticsLabel,
        explicitChildNodes: true,
        child: _PopoverPane(
          level: widget.level,
          surface: widget.surface,
          radius: widget.radius,
          child: Builder(builder: widget.overlayBuilder),
        ),
      ),
    );
    if (!widget.interactive) return IgnorePointer(child: content);
    return TapRegion(
      onTapOutside: widget.barrierDismissible
          ? (PointerDownEvent _) => _close()
          : null,
      child: FocusScope(node: _scope, autofocus: true, child: content),
    );
  }
}

/// Where a pane is placed, and what it is placed inside.
///
/// Every rectangle is in the coordinates of the overlay the pane is drawn in.
@immutable
class _PopoverGeometry {
  const _PopoverGeometry({
    required this.trigger,
    required this.bounds,
    required this.placement,
    required this.gap,
    required this.insetStart,
    required this.insetEnd,
    required this.direction,
  });

  /// The trigger's rectangle.
  final Rect trigger;

  /// The overlay's size.
  final Size bounds;

  /// Where the pane sits, never `auto`.
  final PopoverPlacement placement;

  /// The distance between the trigger and the pane.
  final double gap;

  /// What the pane keeps clear of the overlay's left edge: the safe area and
  /// the gutter.
  final double insetStart;

  /// The same, at the right edge.
  final double insetEnd;

  /// The reading direction, which decides which edge is the leading one.
  final TextDirection direction;

  /// The left most point the pane may reach.
  ///
  /// The inset, or the trigger's own left edge where the trigger is already
  /// closer: a pane never has to keep further from an edge than the control
  /// that opened it.
  double get minLeft => math.min(insetStart, trigger.left);

  /// The right most point the pane may reach, by the same rule.
  double get maxRight => math.max(bounds.width - insetEnd, trigger.right);

  /// The width the pane has to fit in.
  double get room => math.max(0, maxRight - minLeft);

  @override
  bool operator ==(Object other) =>
      other is _PopoverGeometry &&
      other.trigger == trigger &&
      other.bounds == bounds &&
      other.placement == placement &&
      other.gap == gap &&
      other.insetStart == insetStart &&
      other.insetEnd == insetEnd &&
      other.direction == direction;

  @override
  int get hashCode => Object.hash(
    trigger,
    bounds,
    placement,
    gap,
    insetStart,
    insetEnd,
    direction,
  );
}

/// Lays the pane out inside the overlay, against its trigger.
///
/// The box it lays out in is the whole overlay, so a pane placed anywhere
/// inside it is inside its parent and reachable by a pointer; the follower
/// around it has moved that box's origin onto the overlay's.
class _PopoverLayout extends SingleChildLayoutDelegate {
  const _PopoverLayout(this.geometry);

  final _PopoverGeometry geometry;

  @override
  Size getSize(BoxConstraints constraints) =>
      constraints.constrain(geometry.bounds);

  @override
  BoxConstraints getConstraintsForChild(BoxConstraints constraints) =>
      BoxConstraints(
        maxWidth: math.min(geometry.room, constraints.maxWidth),
        maxHeight: constraints.maxHeight,
      );

  @override
  Offset getPositionForChild(Size size, Size childSize) {
    final Rect trigger = geometry.trigger;
    final double gap = geometry.gap;
    final bool rtl = geometry.direction == TextDirection.rtl;
    switch (geometry.placement) {
      case PopoverPlacement.above:
      case PopoverPlacement.below:
      case PopoverPlacement.auto:
        final double top = geometry.placement == PopoverPlacement.above
            ? trigger.top - gap - childSize.height
            : trigger.bottom + gap;
        return Offset(_fitted(childSize.width, rtl: rtl), top);
      case PopoverPlacement.start:
      case PopoverPlacement.end:
        // Beside the trigger, in the reading direction. Placed there on
        // purpose by the caller, so the pane is not moved to the other side.
        final bool before =
            (geometry.placement == PopoverPlacement.start) != rtl;
        final double left = before
            ? trigger.left - gap - childSize.width
            : trigger.right + gap;
        return Offset(left, trigger.center.dy - childSize.height / 2);
    }
  }

  /// The pane's left edge for a pane hanging from the trigger.
  ///
  /// The leading edges align; the trailing edges align instead where the
  /// leading anchor would carry the pane past the overlay's trailing edge;
  /// and the pane is clamped inside the overlay's padding where neither
  /// anchor holds it.
  double _fitted(double width, {required bool rtl}) {
    final Rect trigger = geometry.trigger;
    final double minLeft = geometry.minLeft;
    final double maxRight = geometry.maxRight;
    double left;
    if (rtl) {
      left = trigger.right - width;
      if (left < minLeft) left = trigger.left;
    } else {
      left = trigger.left;
      if (left + width > maxRight) left = trigger.right - width;
    }
    return left.clamp(minLeft, math.max(minLeft, maxRight - width));
  }

  @override
  bool shouldRelayout(_PopoverLayout oldDelegate) =>
      oldDelegate.geometry != geometry;
}

/// The pane itself, faded in at the standard duration.
class _PopoverPane extends StatelessWidget {
  const _PopoverPane({
    required this.level,
    required this.surface,
    required this.radius,
    required this.child,
  });

  final GlassLevel level;
  final PopoverSurface surface;
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
      child: switch (surface) {
        PopoverSurface.glass => GlassSurface(
          level: level,
          radius: radius,
          child: child,
        ),
        PopoverSurface.paper => Surface(
          radius: radius ?? ui.shape.inner,
          boundary: true,
          clip: true,
          child: child,
        ),
      },
    );
  }
}
