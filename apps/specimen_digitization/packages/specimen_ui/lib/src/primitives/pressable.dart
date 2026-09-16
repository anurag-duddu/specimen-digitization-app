/// The one way anything in this product becomes interactive
/// (10 section 3, `Pressable`).
///
/// It owns the whole control contract that is not about paint: named states, a
/// 48 dp hit box, keyboard activation, the focus ring, the state layer, the
/// semantics role and label, and the reason a disabled control gives. A
/// control paints itself from the states this hands it and owns nothing else.
///
/// This replaces `InkWell`, `InkResponse`, `Material` and a bare
/// `GestureDetector` at every call site.
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../foundation/density.dart';
import '../foundation/motion.dart';
import '../foundation/theme.dart';
import 'focus_ring.dart';
import 'state_layer.dart';

/// The semantics role a pressable carries.
///
/// Named here rather than taken as raw `Semantics` flags so a control states
/// what it is once and cannot half set a role.
enum PressableRole {
  /// A command. The default.
  button,

  /// An on or off control. Reports `toggled`.
  toggle,

  /// A box that is checked, unchecked or mixed. Reports `checked`.
  checkbox,

  /// One option of a group. Reports `inMutuallyExclusiveGroup`.
  radio,

  /// One tab of a tab list. Reports the tab role and `selected`.
  tab,

  /// A destination rather than a command.
  link,
}

/// Makes [builder] interactive.
class Pressable extends StatefulWidget {
  /// Wraps [builder] in the control contract.
  ///
  /// [onPressed] null and [disabledReason] set is the disabled state this
  /// product cares about: a control the server forbids, which still has to say
  /// why (03 section 3.6).
  const Pressable({
    super.key,
    required this.builder,
    required this.semanticsLabel,
    this.onPressed,
    this.onLongPress,
    this.disabledReason,
    this.onDisabledReason,
    this.shape,
    this.radius,
    this.capsule = false,
    this.scaleOnPress = false,
    this.selected = false,
    this.checked,
    this.role = PressableRole.button,
    this.semanticsValue,
    this.focusNode,
    this.autofocus = false,
    this.statesController,
    this.minHitBox,
    this.excludeFromSemantics = false,
  });

  /// Paints the control from its current states.
  final Widget Function(BuildContext context, Set<WidgetState> states) builder;

  /// The label a screen reader reads. Stands alone: "Approve record", never
  /// "Approve".
  final String semanticsLabel;

  /// What activation does. Null disables the control.
  final VoidCallback? onPressed;

  /// What a long press does, where the control has one.
  final VoidCallback? onLongPress;

  /// Why the control is disabled, in the reviewer's words.
  ///
  /// Carried on the semantics hint, and handed to [onDisabledReason] so an
  /// overlay can show it. A disabled control in this product is disabled
  /// because the server forbids the decision, and the reviewer is owed the
  /// reason.
  final String? disabledReason;

  /// Called with [disabledReason] when the reviewer hovers or long presses a
  /// disabled control.
  ///
  /// `UiTooltip` (slot C3) is the intended consumer. Until it exists this is
  /// how a control surfaces the reason without this primitive owning an
  /// overlay of its own.
  final ValueChanged<String>? onDisabledReason;

  /// The control's outline, for the state layer. Defaults to a superellipse
  /// at [radius], or a capsule when [capsule] is set.
  final ShapeBorder? shape;

  /// The control's corner radius. The focus ring is drawn at this plus four.
  final double? radius;

  /// True when the control is a capsule.
  final bool capsule;

  /// True to scale the visual to 0.98 while pressed on a touch window.
  final bool scaleOnPress;

  /// True when the control is selected.
  final bool selected;

  /// The checkbox or toggle value, where the role has one. Null is mixed.
  final bool? checked;

  /// What the control is, for semantics.
  final PressableRole role;

  /// The value a screen reader reads after the label, where there is one.
  final String? semanticsValue;

  /// An external focus node, for a composite control that manages focus.
  final FocusNode? focusNode;

  /// True to take focus when first built.
  final bool autofocus;

  /// An external states controller, where a control needs to read the states
  /// outside the builder.
  final WidgetStatesController? statesController;

  /// The minimum hit box. Defaults to 48 in both densities, which is the
  /// floor density never moves.
  final double? minHitBox;

  /// True where an ancestor already publishes the semantics for this control,
  /// such as a row that merges its own children.
  final bool excludeFromSemantics;

  /// True when the control responds to input.
  bool get enabled => onPressed != null || onLongPress != null;

  @override
  State<Pressable> createState() => _PressableState();
}

class _PressableState extends State<Pressable> {
  WidgetStatesController? _internalStates;
  bool _showFocusRing = false;

  WidgetStatesController get _states =>
      widget.statesController ?? (_internalStates ??= WidgetStatesController());

  @override
  void initState() {
    super.initState();
    _syncStates();
    _states.addListener(_statesChanged);
  }

  @override
  void didUpdateWidget(Pressable oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.statesController != widget.statesController) {
      oldWidget.statesController?.removeListener(_statesChanged);
      _internalStates?.removeListener(_statesChanged);
      _states.addListener(_statesChanged);
    }
    _syncStates();
  }

  @override
  void dispose() {
    widget.statesController?.removeListener(_statesChanged);
    _internalStates
      ?..removeListener(_statesChanged)
      ..dispose();
    super.dispose();
  }

  void _statesChanged() {
    if (mounted) setState(() {});
  }

  void _syncStates() {
    _states
      ..update(WidgetState.disabled, !widget.enabled)
      ..update(WidgetState.selected, widget.selected);
  }

  void _activate() {
    if (!widget.enabled) {
      _reportReason();
      return;
    }
    widget.onPressed?.call();
  }

  void _reportReason() {
    final String? reason = widget.disabledReason;
    if (reason != null) widget.onDisabledReason?.call(reason);
  }

  void _setHovered(bool value) {
    _states.update(WidgetState.hovered, value && widget.enabled);
    if (value && !widget.enabled) _reportReason();
  }

  void _setFocusRing(bool value) {
    // FocusableActionDetector only reports true under
    // FocusHighlightMode.traditional, which is exactly clause 4: the ring is
    // for keyboard focus and never for a pointer press.
    if (_showFocusRing == value) return;
    setState(() => _showFocusRing = value);
  }

  void _setPressed(bool value) =>
      _states.update(WidgetState.pressed, value && widget.enabled);

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final bool enabled = widget.enabled;
    final Set<WidgetState> states = <WidgetState>{..._states.value};
    if (_showFocusRing) states.add(WidgetState.focused);

    final ShapeBorder shape =
        widget.shape ??
        (widget.capsule
            ? ui.shape.capsule
            : RoundedSuperellipseBorder(
                borderRadius: BorderRadius.circular(
                  widget.radius ?? ui.shape.inner,
                ),
              ));

    Widget visual = widget.builder(context, states);
    visual = Stack(
      alignment: Alignment.center,
      children: <Widget>[
        visual,
        Positioned.fill(
          child: IgnorePointer(
            child: StateLayer(states: states, shape: shape),
          ),
        ),
      ],
    );

    if (widget.scaleOnPress) {
      visual = AnimatedScale(
        // Touch only: a pointer has a hover state to say the same thing, and
        // a mouse user pressing a button that shrinks reads as a glitch.
        scale: states.contains(WidgetState.pressed) && ui.density.isTouch
            ? _pressedScale
            : 1,
        duration: ui.motion.pressIn,
        curve: MotionTokens.standardCurve,
        child: visual,
      );
    }

    final double hit = widget.minHitBox ?? UiDensity.hitBox;
    Widget core = ConstrainedBox(
      constraints: BoxConstraints(minWidth: hit, minHeight: hit),
      // Shrink wrapped, so the hit box pads the visual rather than stretching
      // it: in pointer density the extra 8 dp is transparent slop.
      child: Center(widthFactor: 1, heightFactor: 1, child: visual),
    );

    core = FocusRing(
      visible: _showFocusRing,
      radius: widget.radius ?? ui.shape.inner,
      capsule: widget.capsule,
      child: core,
    );

    core = FocusableActionDetector(
      enabled: enabled,
      focusNode: widget.focusNode,
      autofocus: widget.autofocus,
      mouseCursor: enabled
          ? SystemMouseCursors.click
          : SystemMouseCursors.basic,
      onShowHoverHighlight: _setHovered,
      onShowFocusHighlight: _setFocusRing,
      shortcuts: _activationShortcuts,
      actions: <Type, Action<Intent>>{
        ActivateIntent: CallbackAction<ActivateIntent>(
          onInvoke: (ActivateIntent intent) {
            _activate();
            return null;
          },
        ),
        ButtonActivateIntent: CallbackAction<ButtonActivateIntent>(
          onInvoke: (ButtonActivateIntent intent) {
            _activate();
            return null;
          },
        ),
      },
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        excludeFromSemantics: true,
        onTap: enabled ? _activate : _reportReason,
        onTapDown: enabled ? (TapDownDetails _) => _setPressed(true) : null,
        onTapUp: enabled ? (TapUpDetails _) => _setPressed(false) : null,
        onTapCancel: enabled ? () => _setPressed(false) : null,
        onLongPress: enabled ? widget.onLongPress : _reportReason,
        child: core,
      ),
    );

    if (widget.excludeFromSemantics) return core;

    return Semantics(
      container: true,
      label: widget.semanticsLabel,
      value: widget.semanticsValue,
      hint: enabled ? null : widget.disabledReason,
      enabled: enabled,
      button: widget.role == PressableRole.button,
      link: widget.role == PressableRole.link,
      toggled: widget.role == PressableRole.toggle ? widget.checked : null,
      checked: widget.role == PressableRole.checkbox ? widget.checked : null,
      inMutuallyExclusiveGroup: widget.role == PressableRole.radio
          ? true
          : null,
      selected: _selectedFlag,
      role: widget.role == PressableRole.tab ? SemanticsRole.tab : null,
      focusable: enabled,
      onTap: enabled ? _activate : null,
      onLongPress: enabled ? widget.onLongPress : null,
      child: core,
    );
  }

  /// `selected` is reported for the roles that have a selection, and left
  /// unset elsewhere so a plain button does not announce "not selected".
  bool? get _selectedFlag => switch (widget.role) {
    PressableRole.tab || PressableRole.radio => widget.selected,
    _ => widget.selected ? true : null,
  };

  /// The 0.98 the contract names.
  static const double _pressedScale = 0.98;

  /// Space and Enter activate. Stated rather than inherited, because the
  /// default map depends on the platform and clause 3 does not.
  static const Map<ShortcutActivator, Intent> _activationShortcuts =
      <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.space): ActivateIntent(),
        SingleActivator(LogicalKeyboardKey.enter): ActivateIntent(),
        SingleActivator(LogicalKeyboardKey.numpadEnter): ActivateIntent(),
      };
}
