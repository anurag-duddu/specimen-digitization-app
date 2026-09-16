/// The tooltip (10 section 4.3, `UiTooltip`).
library;

import 'dart:async';

// The only import of `material.dart` in the controls layer, and the reason 10
// section 1.3 allows it here: `MaterialLocalizations` carries the localised
// "dismiss" string a revealed tooltip publishes on touch. The widget itself is
// not used; this package owns the tooltip.
import 'package:flutter/material.dart' show MaterialLocalizations;
import 'package:flutter/gestures.dart' show PointerEnterEvent, PointerExitEvent;
import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../primitives/popover.dart';

/// The resolved paint of one tooltip.
@immutable
class UiTooltipStyle {
  /// Binds every token a tooltip draws with.
  const UiTooltipStyle({
    required this.label,
    required this.foreground,
    required this.radius,
    required this.padding,
    required this.maxWidth,
  });

  /// The message's type role: `body.small`.
  final TextStyle label;

  /// The message's colour.
  final Color foreground;

  /// The pane's corner radius: `radius.inner`.
  final double radius;

  /// Padding inside the pane.
  final EdgeInsetsGeometry padding;

  /// The widest a tooltip is drawn before its message wraps.
  final double maxWidth;

  /// The style a tooltip draws with in [ui].
  static UiTooltipStyle resolve(UiThemeData ui) => UiTooltipStyle(
    label: ui.type.bodySmall,
    foreground: ui.color.ink,
    radius: ui.shape.inner,
    padding: EdgeInsetsDirectional.symmetric(
      horizontal: ui.space.s3,
      vertical: ui.space.s2,
    ),
    maxWidth: ui.space.readingMax / 2,
  );

  /// How long the pointer rests on a control before its tooltip appears.
  ///
  /// Fixed at 400 ms by 10 section 4.3. It is a delay before an overlay
  /// appears rather than the duration of an animation, so the reduced-motion
  /// policy in 04 section 2.5 does not collapse it: a reviewer who asked for
  /// less motion did not ask for tooltips that fire the moment the pointer
  /// crosses a control.
  static const Duration hoverDelay = Duration(milliseconds: 400);

  /// How long a tooltip revealed by a long press stays on screen.
  ///
  /// Touch has no pointer to leave, so the reveal is a window rather than a
  /// state. Tapping anywhere ends it early.
  static const Duration touchDuration = Duration(milliseconds: 1500);
}

/// A short phrase describing the control beneath the pointer.
///
/// Retires `Tooltip`. The pane is `paper` rather than glass because tooltips
/// are small and frequent, and every frosted pane costs a save layer against
/// the budget in 09 section 3.3.
///
/// A tooltip is never the only place an instruction lives: it is unavailable
/// on touch without a long press (02 section 4.12), and the same string is
/// already the control's accessibility label, so this widget publishes the
/// message on the pane and leaves the control's own semantics alone rather
/// than saying it twice.
class UiTooltip extends StatefulWidget {
  /// Describes [child] with [message].
  const UiTooltip({
    super.key,
    required String this.message,
    required Widget this.child,
    this.placement = PopoverPlacement.above,
    this.enabled = true,
    this.style,
  }) : builder = null;

  /// Carries a disabled control's reason.
  ///
  /// [builder] is handed the callback to pass to `Pressable.onDisabledReason`,
  /// and whatever reason the control reports is what the tooltip shows. This
  /// is the carrier 10 section 4.3 names: a control the server forbids owes
  /// the reviewer the reason, and `Pressable` deliberately owns no overlay of
  /// its own.
  const UiTooltip.reason({
    super.key,
    required this.builder,
    this.placement = PopoverPlacement.above,
    this.enabled = true,
    this.style,
  }) : message = null, child = null;

  /// The phrase. A verb phrase, 40 characters or fewer, no period
  /// (02 section 4.12). Null in the [UiTooltip.reason] form, which takes its
  /// message from the control.
  final String? message;

  /// The control being described.
  final Widget? child;

  /// Builds the control in the [UiTooltip.reason] form.
  final Widget Function(BuildContext context, ValueChanged<String> report)?
  builder;

  /// Where the tooltip sits relative to the control.
  final PopoverPlacement placement;

  /// False to suppress the tooltip without changing the tree around it.
  final bool enabled;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiTooltipStyle? style;

  @override
  State<UiTooltip> createState() => _UiTooltipState();
}

class _UiTooltipState extends State<UiTooltip> {
  final PopoverController _controller = PopoverController();
  Timer? _timer;
  String? _reported;
  bool _fromTouch = false;

  /// The phrase on screen right now.
  String? get _message => widget.message ?? _reported;

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _cancel() {
    _timer?.cancel();
    _timer = null;
  }

  void _hide() {
    _cancel();
    _controller.close();
  }

  void _show({required bool fromTouch}) {
    if (!widget.enabled || (_message ?? '').isEmpty) return;
    _cancel();
    _fromTouch = fromTouch;
    _controller.open();
    if (fromTouch) {
      _timer = Timer(UiTooltipStyle.touchDuration, _hide);
    }
  }

  void _pointerEntered() {
    if (!widget.enabled || (_message ?? '').isEmpty) return;
    _cancel();
    _timer = Timer(
      UiTooltipStyle.hoverDelay,
      () => _show(fromTouch: false),
    );
  }

  /// Takes the reason a disabled control reported and reveals it.
  void _report(String reason) {
    if (reason == _reported && _controller.isOpen) return;
    setState(() => _reported = reason);
    _show(fromTouch: false);
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiTooltipStyle style = widget.style ?? UiTooltipStyle.resolve(ui);
    final Widget control =
        widget.child ?? widget.builder!(context, _report);
    return Popover(
      controller: _controller,
      placement: widget.placement,
      surface: PopoverSurface.paper,
      interactive: false,
      radius: style.radius,
      // A tooltip has no barrier of its own: it is passive, so a tap goes to
      // whatever is beneath it, and the pointer leaving is what dismisses it.
      barrierDismissible: false,
      overlayBuilder: (BuildContext context) => _TooltipPane(
        message: _message ?? '',
        style: style,
        dismissLabel: _fromTouch ? _dismissLabel(context) : null,
        onDismiss: _hide,
      ),
      child: MouseRegion(
        onEnter: (PointerEnterEvent _) => _pointerEntered(),
        onExit: (PointerExitEvent _) => _hide(),
        child: GestureDetector(
          behavior: HitTestBehavior.deferToChild,
          excludeFromSemantics: true,
          onLongPress: () => _show(fromTouch: true),
          onTap: _hide,
          child: control,
        ),
      ),
    );
  }

  /// The localised word for ending the reveal.
  ///
  /// `Localizations.of` rather than `MaterialLocalizations.of`, because a
  /// harness that never mounts the delegate should get no tooltip semantics
  /// rather than an exception.
  String? _dismissLabel(BuildContext context) =>
      Localizations.of<MaterialLocalizations>(
        context,
        MaterialLocalizations,
      )?.modalBarrierDismissLabel;
}

/// The pane itself.
class _TooltipPane extends StatelessWidget {
  const _TooltipPane({
    required this.message,
    required this.style,
    required this.dismissLabel,
    required this.onDismiss,
  });

  final String message;
  final UiTooltipStyle style;
  final String? dismissLabel;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    // The `tooltip` property rather than `SemanticsRole.tooltip`: the role
    // exists in this SDK but its debug checks do not, so setting it throws
    // "Missing checks for role SemanticsRole.tooltip" on the first frame
    // (Flutter 3.38.5, `semantics.dart`, `_DebugSemanticsRoleChecks`). The
    // property is what carries a tooltip to the platform in any case, and the
    // message reaches the node's label through the `Text` below.
    tooltip: message,
    hint: dismissLabel,
    onDismiss: dismissLabel == null ? null : onDismiss,
    child: ConstrainedBox(
      constraints: BoxConstraints(maxWidth: style.maxWidth),
      child: Padding(
        padding: style.padding,
        child: Text(
          message,
          style: style.label.copyWith(color: style.foreground),
        ),
      ),
    ),
  );
}
