/// Joined commands with independent selection and availability.
library;

import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/fit.dart';
import '../../primitives/pressable.dart';
import '../overlays/tooltip.dart';

/// One command in a [UiButtonGroup].
@immutable
class UiButtonGroupItem {
  /// Creates the component with explicit caller-owned configuration.
  const UiButtonGroupItem({
    required this.label,
    this.icon,
    this.leadingDot = false,
    this.onPressed,
    this.selected = false,
    this.disabledReason,
  });

  /// The visible and accessible name of the control.
  final String label;

  /// The optional Phosphor command icon.
  final IconSpec? icon;

  /// Whether a dot replaces the optional leading icon.
  final bool leadingDot;

  /// The host action; `null` makes the command unavailable.
  final VoidCallback? onPressed;

  /// Whether current selection accepted by the host.
  final bool selected;

  /// The explanation shown when the control is unavailable.
  final String? disabledReason;
}

/// Commands sharing a boundary, without implying mutually exclusive values.
///
/// Selection and callbacks remain caller-owned. Arrow keys move between
/// commands; Enter/Space activate through [Pressable]. When the complete
/// labels cannot fit, the group stacks vertically rather than clipping.
class UiButtonGroup extends StatefulWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiButtonGroup({
    super.key,
    required this.label,
    required this.items,
    this.iconOnly = false,
  }) : assert(items.length > 0);

  /// The visible and accessible name of the control.
  final String label;

  /// The ordered commands in the group.
  final List<UiButtonGroupItem> items;

  /// Whether the visual label is omitted while its accessible name remains.
  final bool iconOnly;

  @override
  State<UiButtonGroup> createState() => _UiButtonGroupState();
}

class _UiButtonGroupState extends State<UiButtonGroup> {
  final List<FocusNode> _nodes = <FocusNode>[];

  @override
  void initState() {
    super.initState();
    _syncNodes();
  }

  void _syncNodes() {
    while (_nodes.length < widget.items.length) {
      _nodes.add(FocusNode(debugLabel: 'Joined command'));
    }
    while (_nodes.length > widget.items.length) {
      _nodes.removeLast().dispose();
    }
  }

  @override
  void didUpdateWidget(UiButtonGroup oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncNodes();
  }

  @override
  void dispose() {
    for (final FocusNode node in _nodes) {
      node.dispose();
    }
    super.dispose();
  }

  KeyEventResult _key(FocusNode node, KeyEvent event, bool vertical) {
    if (event is! KeyDownEvent && event is! KeyRepeatEvent) {
      return KeyEventResult.ignored;
    }
    final int index = _nodes.indexWhere((FocusNode n) => n.hasFocus);
    if (index < 0) return KeyEventResult.ignored;
    final bool rtl = Directionality.of(context) == TextDirection.rtl;
    final int? delta = vertical
        ? switch (event.logicalKey) {
            LogicalKeyboardKey.arrowDown => 1,
            LogicalKeyboardKey.arrowUp => -1,
            _ => null,
          }
        : switch (event.logicalKey) {
            LogicalKeyboardKey.arrowRight => rtl ? -1 : 1,
            LogicalKeyboardKey.arrowLeft => rtl ? 1 : -1,
            _ => null,
          };
    final bool first = event.logicalKey == LogicalKeyboardKey.home;
    final bool last = event.logicalKey == LogicalKeyboardKey.end;
    if (!first && !last && delta == null) return KeyEventResult.ignored;
    int? target;
    // Pressable deliberately keeps a disabled command with a reason focusable
    // so it can explain itself. Honor its actual focusability rather than
    // equating a missing callback with an unreachable command.
    for (int distance = 0; distance < _nodes.length; distance++) {
      final int candidate = first
          ? distance
          : last
          ? _nodes.length - 1 - distance
          : (index + delta! * (distance + 1)) % _nodes.length;
      if (_nodes[candidate].canRequestFocus) {
        target = candidate;
        break;
      }
    }
    if (target == null) return KeyEventResult.ignored;
    _nodes[target].requestFocus();
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    assert(
      !widget.iconOnly ||
          widget.items.every((item) => item.icon != null || item.leadingDot),
    );
    final List<double> widths = widget.items
        .map((item) {
          if (widget.iconOnly) return UiDensity.hitBox;
          return math.max(
            UiDensity.hitBox,
            measureLabel(context, item.label, ui.type.label).width +
                ui.space.s3 * 2 +
                (item.icon == null && !item.leadingDot
                    ? 0
                    : ui.space.iconInline + ui.space.s2),
          );
        })
        .toList(growable: false);
    return LayoutBuilder(
      builder: (context, constraints) {
        final bool vertical =
            constraints.hasBoundedWidth &&
            widths.fold<double>(0, (a, b) => a + b) +
                    ui.shape.stroke.hairline * (widget.items.length + 1) >
                constraints.maxWidth;
        final List<Widget> children = <Widget>[];
        for (int i = 0; i < widget.items.length; i++) {
          final UiButtonGroupItem item = widget.items[i];
          if (i > 0) {
            children.add(
              SizedBox(
                width: vertical ? null : ui.shape.stroke.hairline,
                height: vertical ? ui.shape.stroke.hairline : UiDensity.hitBox,
                child: ColoredBox(color: ui.color.boundary),
              ),
            );
          }
          Widget control = Pressable(
            semanticsLabel: item.label,
            onPressed: item.onPressed,
            disabledReason: item.disabledReason,
            selected: item.selected,
            focusNode: _nodes[i],
            insetFocusRing: true,
            radius: ui.shape.inner,
            builder: (context, states) {
              final Color foreground = states.contains(WidgetState.disabled)
                  ? ui.color.disabledContent
                  : ui.color.ink;
              return ColoredBox(
                color: item.selected ? ui.color.matte : ui.color.paper,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(
                    minHeight: UiDensity.hitBox,
                  ),
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: ui.space.s3,
                      vertical: ui.space.s2,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: <Widget>[
                        if (item.leadingDot)
                          SizedBox.square(
                            dimension: ui.space.iconInline,
                            child: Center(
                              child: Container(
                                width: ui.space.s2,
                                height: ui.space.s2,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: foreground,
                                ),
                              ),
                            ),
                          )
                        else if (item.icon != null)
                          UiIcon(
                            item.icon!,
                            color: foreground,
                            size: UiIconSize.inline,
                          ),
                        if (!widget.iconOnly) ...<Widget>[
                          if (item.icon != null || item.leadingDot)
                            SizedBox(width: ui.space.s2),
                          Flexible(
                            child: Text(
                              item.label,
                              textAlign: TextAlign.center,
                              style: ui.type.label.copyWith(color: foreground),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              );
            },
          );
          if (widget.iconOnly) {
            control = MergeSemantics(
              child: UiTooltip(
                message: item.disabledReason ?? item.label,
                excludeSemantics: true,
                child: control,
              ),
            );
          }
          children.add(
            vertical ? control : SizedBox(width: widths[i], child: control),
          );
        }
        return Semantics(
          container: true,
          explicitChildNodes: true,
          label: widget.label,
          child: Focus(
            canRequestFocus: false,
            onKeyEvent: (node, event) => _key(node, event, vertical),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: ui.color.paper,
                border: Border.all(color: ui.color.boundary),
                borderRadius: BorderRadius.circular(ui.shape.inner),
              ),
              child: Padding(
                padding: EdgeInsets.all(ui.shape.stroke.hairline),
                child: vertical
                    ? Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: children,
                      )
                    : Row(mainAxisSize: MainAxisSize.min, children: children),
              ),
            ),
          ),
        );
      },
    );
  }
}
