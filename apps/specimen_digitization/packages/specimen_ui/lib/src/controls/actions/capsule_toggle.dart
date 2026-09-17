/// The capsule toggle (10 section 4.1, `UiCapsuleToggle`).
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/fit.dart';
import '../../primitives/label.dart';
import '../../primitives/pressable.dart';
import '../overlays/tooltip.dart';
import 'button.dart';

/// One option of a capsule toggle.
@immutable
class UiToggleOption<T> {
  /// Binds [value] to the words the reviewer reads.
  const UiToggleOption({
    required this.value,
    required this.label,
    this.semanticsLabel,
  });

  /// What [UiCapsuleToggle.onChanged] reports when this option is on.
  final T value;

  /// The visible label. Sentence case, short (02 section 1.6).
  final String label;

  /// Overrides the label a screen reader reads, where the visible one does
  /// not stand alone out of context (02 section 4.16).
  final String? semanticsLabel;

  /// What a screen reader announces.
  String get spokenLabel => semanticsLabel ?? label;
}

/// How many options may be on at once.
enum UiToggleSelection {
  /// One option at a time. Choosing another moves the selection; choosing the
  /// one already on clears it, so "none" stays reachable without a second
  /// control.
  single,

  /// Any number at once.
  multiple,
}

/// The resolved paint of one capsule toggle.
@immutable
class UiCapsuleToggleStyle {
  /// Binds every token a capsule toggle draws with.
  const UiCapsuleToggleStyle({
    required this.background,
    required this.foreground,
    required this.side,
    required this.checkFill,
    required this.checkOutline,
    required this.onCheck,
    required this.label,
    required this.padding,
    required this.minHeight,
    required this.discSize,
    required this.gap,
    required this.spacing,
  });

  /// The capsule's fill, by state.
  final WidgetStateProperty<Color> background;

  /// The label colour, by state.
  final WidgetStateProperty<Color> foreground;

  /// The capsule's edge, by state. `emphasis` once the option is on, which is
  /// the second cue that keeps selection off colour alone.
  final WidgetStateProperty<BorderSide> side;

  /// What the check disc fills with, by state.
  final WidgetStateProperty<Color> checkFill;

  /// The empty disc's edge, by state.
  final WidgetStateProperty<Color> checkOutline;

  /// The check drawn inside the filled disc.
  final Color onCheck;

  /// The label's type role.
  final TextStyle label;

  /// The padding inside the capsule.
  final EdgeInsetsGeometry padding;

  /// The visual height of one option.
  final double minHeight;

  /// The check disc, 16 dp.
  final double discSize;

  /// The space between the label and the disc.
  final double gap;

  /// The space between two options.
  final double spacing;

  /// The style for [size] in [ui], at [textScaler].
  static UiCapsuleToggleStyle resolve(
    UiThemeData ui,
    UiSize size, {
    TextScaler textScaler = TextScaler.noScaling,
  }) {
    Color fill(Set<WidgetState> states) => states.contains(WidgetState.disabled)
        ? ui.color.disabledFill
        : ui.color.paper;

    Color text(Set<WidgetState> states) => states.contains(WidgetState.disabled)
        ? ui.color.disabledContent
        : ui.color.ink;

    BorderSide edge(Set<WidgetState> states) {
      if (states.contains(WidgetState.disabled)) {
        return BorderSide(
          color: ui.color.disabledOutline,
          width: ui.shape.stroke.boundary,
        );
      }
      return states.contains(WidgetState.selected)
          ? BorderSide(color: ui.color.ink, width: ui.shape.stroke.emphasis)
          : BorderSide(
              color: ui.color.boundary,
              width: ui.shape.stroke.boundary,
            );
    }

    return UiCapsuleToggleStyle(
      background: WidgetStateProperty.resolveWith(fill),
      foreground: WidgetStateProperty.resolveWith(text),
      side: WidgetStateProperty.resolveWith(edge),
      checkFill: WidgetStateProperty.resolveWith(
        (Set<WidgetState> states) => states.contains(WidgetState.disabled)
            ? ui.color.disabledContent
            : ui.color.ink,
      ),
      checkOutline: WidgetStateProperty.resolveWith(
        (Set<WidgetState> states) => states.contains(WidgetState.disabled)
            ? ui.color.disabledOutline
            : ui.color.boundary,
      ),
      onCheck: ui.color.paper,
      label: ui.type.label,
      padding: EdgeInsetsDirectional.only(start: ui.space.s4, end: ui.space.s3),
      // The resting height of the size table, grown around the role a
      // capsule actually draws. An option is set in `label` at every size,
      // so the height that holds it derives from `label` too.
      minHeight: UiType.heightAroundAt(
        UiButtonStyle.restingHeightOf(ui, size),
        ui.type.label,
        textScaler,
      ),
      discSize: ui.space.iconSmall,
      gap: ui.space.s3,
      spacing: ui.space.s2,
    );
  }
}

/// A row of capsules, each with a check disc that fills when it is on.
///
/// Retires `FilterChip` in filter rows and `ChoiceChip`.
///
/// Arrow keys move focus between the options and `Space` toggles the focused
/// one, which is the WAI-ARIA pattern for a group of toggles: one Tab stop
/// into the group, then arrows inside it.
class UiCapsuleToggle<T> extends StatefulWidget {
  /// A group of [options], of which [selected] are on.
  const UiCapsuleToggle({
    super.key,
    required this.options,
    required this.selected,
    required this.onChanged,
    this.selection = UiToggleSelection.multiple,
    this.size = UiSize.md,
    this.disabledReason,
  });

  /// The options, in the order they are drawn.
  final List<UiToggleOption<T>> options;

  /// Which options are on.
  final Set<T> selected;

  /// Reports the whole new set, never one option, so a caller never has to
  /// reconstruct it. Null disables the group.
  final ValueChanged<Set<T>>? onChanged;

  /// How many options may be on at once.
  final UiToggleSelection selection;

  /// The size the options are drawn at.
  final UiSize size;

  /// Why the group is disabled, in the reviewer's words.
  final String? disabledReason;

  @override
  State<UiCapsuleToggle<T>> createState() => _UiCapsuleToggleState<T>();
}

class _UiCapsuleToggleState<T> extends State<UiCapsuleToggle<T>> {
  List<FocusNode> _nodes = <FocusNode>[];

  @override
  void initState() {
    super.initState();
    _syncNodes();
  }

  @override
  void didUpdateWidget(UiCapsuleToggle<T> oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.options.length != widget.options.length) _syncNodes();
  }

  @override
  void dispose() {
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
    super.dispose();
  }

  void _syncNodes() {
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
    _nodes = List<FocusNode>.generate(
      widget.options.length,
      (int index) => FocusNode(debugLabel: widget.options[index].label),
      growable: false,
    );
  }

  void _toggle(T value) {
    final ValueChanged<Set<T>>? onChanged = widget.onChanged;
    if (onChanged == null) return;
    final bool wasOn = widget.selected.contains(value);
    final Set<T> next = switch (widget.selection) {
      UiToggleSelection.single => wasOn ? <T>{} : <T>{value},
      UiToggleSelection.multiple =>
        wasOn
            ? (Set<T>.of(widget.selected)..remove(value))
            : (Set<T>.of(widget.selected)..add(value)),
    };
    onChanged(next);
  }

  /// Moves focus [step] options along, stopping at the ends.
  ///
  /// Stopping rather than wrapping: a reviewer holding the arrow key should
  /// end up somewhere they can predict, and a wrap makes the last option and
  /// the first indistinguishable by feel.
  void _move(int step) {
    if (_nodes.isEmpty) return;
    final int from = _nodes.indexWhere((FocusNode node) => node.hasFocus);
    final int to = (from < 0 ? 0 : from + step).clamp(0, _nodes.length - 1);
    _nodes[to].requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiCapsuleToggleStyle style = UiCapsuleToggleStyle.resolve(
      ui,
      widget.size,
      textScaler: MediaQuery.textScalerOf(context),
    );
    final bool rtl = Directionality.of(context) == TextDirection.rtl;
    return FocusTraversalGroup(
      policy: WidgetOrderTraversalPolicy(),
      child: Shortcuts(
        shortcuts: _shortcuts,
        child: Actions(
          actions: <Type, Action<Intent>>{
            _MoveFocusIntent: CallbackAction<_MoveFocusIntent>(
              onInvoke: (_MoveFocusIntent intent) {
                _move(intent.horizontal && rtl ? -intent.step : intent.step);
                return null;
              },
            ),
          },
          child: Wrap(
            spacing: style.spacing,
            runSpacing: style.spacing,
            children: <Widget>[
              for (int i = 0; i < widget.options.length; i++)
                _ToggleOption<T>(
                  option: widget.options[i],
                  style: style,
                  focusNode: _nodes[i],
                  selected: widget.selected.contains(widget.options[i].value),
                  disabledReason: widget.disabledReason,
                  onPressed: widget.onChanged == null
                      ? null
                      : () => _toggle(widget.options[i].value),
                ),
            ],
          ),
        ),
      ),
    );
  }

  /// Arrow keys move within the group. Stated here rather than left to
  /// `WidgetsApp`'s directional traversal, because traversal reads geometry
  /// and this group has an order of its own that wrapping to a second run
  /// must not change.
  static const Map<ShortcutActivator, Intent> _shortcuts =
      <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.arrowRight): _MoveFocusIntent(1),
        SingleActivator(LogicalKeyboardKey.arrowLeft): _MoveFocusIntent(-1),
        SingleActivator(LogicalKeyboardKey.arrowDown): _MoveFocusIntent(
          1,
          horizontal: false,
        ),
        SingleActivator(LogicalKeyboardKey.arrowUp): _MoveFocusIntent(
          -1,
          horizontal: false,
        ),
      };
}

/// Move focus one option along.
class _MoveFocusIntent extends Intent {
  const _MoveFocusIntent(this.step, {this.horizontal = true});

  /// How far, and in which direction, in option order.
  final int step;

  /// True for the left and right keys, which mirror under RTL. Up and down
  /// do not: reading order runs top to bottom in both directions.
  final bool horizontal;
}

/// One capsule with its check disc.
class _ToggleOption<T> extends StatelessWidget {
  const _ToggleOption({
    required this.option,
    required this.style,
    required this.focusNode,
    required this.selected,
    required this.onPressed,
    required this.disabledReason,
  });

  final UiToggleOption<T> option;
  final UiCapsuleToggleStyle style;
  final FocusNode focusNode;
  final bool selected;
  final VoidCallback? onPressed;
  final String? disabledReason;

  /// The narrowest width this option draws the whole of its label at.
  double _intrinsicWidth(BuildContext context, UiCapsuleToggleStyle style) =>
      math.max(
        UiDensity.hitBox,
        style.padding.horizontal +
            measureLabel(context, option.label, style.label).width +
            style.gap +
            style.discSize,
      );

  @override
  Widget build(BuildContext context) {
    // A group of capsules is arranged by its `Wrap`, which is the parent
    // owning arrangement (11 section 3.3). One option has no compact variant
    // of its own: given less than it needs it ellipsises and its tooltip
    // carries the word, which is rule 4.
    return FitBuilder(
      variants: <FitVariant>[
        FitVariant(
          intrinsicWidth: _intrinsicWidth(context, style),
          builder: (BuildContext context, bool lastResort) {
            final Widget capsule = _capsule(context);
            return lastResort
                ? UiTooltip(message: option.label, child: capsule)
                : capsule;
          },
        ),
      ],
    );
  }

  Widget _capsule(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Pressable(
      semanticsLabel: option.spokenLabel,
      onPressed: onPressed,
      disabledReason: disabledReason,
      role: PressableRole.toggle,
      checked: selected,
      selected: selected,
      capsule: true,
      scaleOnPress: true,
      focusNode: focusNode,
      builder: (BuildContext context, Set<WidgetState> states) {
        final Color foreground = style.foreground.resolve(states);
        return DecoratedBox(
          decoration: ShapeDecoration(
            shape: StadiumBorder(side: style.side.resolve(states)),
            color: style.background.resolve(states),
          ),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: style.minHeight),
            child: Padding(
              padding: style.padding,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Flexible(
                    child: UiLabel(
                      option.label,
                      style: style.label.copyWith(color: foreground),
                    ),
                  ),
                  SizedBox(width: style.gap),
                  _CheckDisc(
                    style: style,
                    selected: selected,
                    states: states,
                    motion: ui.motion,
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

/// The 16 dp disc that fills from its centre when the option goes on.
///
/// Signature motion 2 (09 section 8): `short`, the standard curve, and the
/// check fading in after 40 percent of the fill. Under reduced motion the
/// duration is zero, so the fill and the check arrive together, which is what
/// the same row of 09 says should happen.
class _CheckDisc extends StatelessWidget {
  const _CheckDisc({
    required this.style,
    required this.selected,
    required this.states,
    required this.motion,
  });

  final UiCapsuleToggleStyle style;
  final bool selected;
  final Set<WidgetState> states;
  final MotionTokens motion;

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
    tween: Tween<double>(begin: selected ? 1 : 0, end: selected ? 1 : 0),
    duration: motion.capsuleFill,
    curve: MotionTokens.standardCurve,
    builder: (BuildContext context, double t, Widget? child) => SizedBox.square(
      dimension: style.discSize,
      child: CustomPaint(
        painter: _CheckDiscPainter(
          fill: style.checkFill.resolve(states),
          outline: style.checkOutline.resolve(states),
          stroke: context.ui.shape.stroke.boundary,
          fillFraction: t,
        ),
        child: Center(
          child: Opacity(
            opacity: _checkOpacity(t),
            child: UiIcon(
              UiIcons.check,
              size: UiIconSize.small,
              color: style.onCheck,
            ),
          ),
        ),
      ),
    ),
  );

  /// The check is invisible for the first 40 percent of the fill and then
  /// fades in over the rest.
  double _checkOpacity(double t) {
    const double start = MotionTokens.capsuleCheckDelayFraction;
    if (t <= start) return 0;
    return ((t - start) / (1 - start)).clamp(0, 1);
  }
}

class _CheckDiscPainter extends CustomPainter {
  const _CheckDiscPainter({
    required this.fill,
    required this.outline,
    required this.stroke,
    required this.fillFraction,
  });

  final Color fill;
  final Color outline;
  final double stroke;
  final double fillFraction;

  @override
  void paint(Canvas canvas, Size size) {
    final Offset centre = size.center(Offset.zero);
    final double radius = size.shortestSide / 2;
    canvas.drawCircle(
      centre,
      radius - stroke / 2,
      Paint()
        ..color = outline
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke,
    );
    if (fillFraction <= 0) return;
    canvas.drawCircle(centre, radius * fillFraction, Paint()..color = fill);
  }

  @override
  bool shouldRepaint(_CheckDiscPainter oldDelegate) =>
      oldDelegate.fill != fill ||
      oldDelegate.outline != outline ||
      oldDelegate.stroke != stroke ||
      oldDelegate.fillFraction != fillFraction;
}
