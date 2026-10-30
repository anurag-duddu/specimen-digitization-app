/// Controlled progress through a multi-step task.
library;

import 'package:flutter/widgets.dart';
import '../../foundation/theme.dart';
import '../../foundation/icons.dart';
import '../../primitives/pressable.dart';
import '../../primitives/surface.dart';

/// A step's meaning, independent of its position.
enum UiStepState {
  /// Not started.
  upcoming,

  /// The step currently being worked on.
  current,

  /// Finished successfully.
  complete,

  /// Requires correction before continuing.
  error,
}

/// A step with optional supporting text and a caller-owned navigation action.
@immutable
class UiStep {
  /// Describes one step.
  const UiStep({
    required this.label,
    this.description,
    this.state = UiStepState.upcoming,
    this.onSelected,
    this.icon,
  });

  /// The task performed at this step.
  final String label;

  /// Supporting guidance. Wraps in full.
  final String? description;

  /// Current, complete, upcoming or requiring correction.
  final UiStepState state;

  /// Enables navigation when the host allows it.
  final VoidCallback? onSelected;

  /// The optional Phosphor glyph preceding the label.
  final IconSpec? icon;
}

/// Step anatomy, with independent task state and host navigation permissions.
enum UiStepsStyle {
  /// Each step in a neutral card.
  cards,

  /// Step text beneath a progress rule.
  textLine,

  /// A status marker before the step text.
  iconLeft,

  /// A status marker above the step text.
  iconTop,

  /// A leading marker and text within a card.
  featuredLeft,

  /// A top marker and text within a card.
  featuredTop,

  /// A compact marker with a complete spoken step description.
  iconOnly,
}

/// Visual marker scale; interactive steps always retain the shared hit target.
enum UiStepSize {
  /// Compact task marker.
  small,

  /// Standard task marker.
  medium,

  /// Emphasized task marker.
  large,
}

/// A step list that becomes vertical when complete labels need more room.
class UiSteps extends StatelessWidget {
  /// Shows [steps] in task order.
  const UiSteps({
    super.key,
    required this.steps,
    this.style = UiStepsStyle.cards,
    this.axis,
    this.compact = false,
    this.connected = false,
    this.size = UiStepSize.medium,
  });

  /// The host owns state and navigation permissions.
  final List<UiStep> steps;

  /// The visual treatment, independent of the content or controlled state.
  final UiStepsStyle style;

  /// Null adapts to available space. Horizontal uses a scroll strip if needed.
  final Axis? axis;

  /// Whether compact token spacing is used.
  final bool compact;

  /// Whether adjacent steps are joined by a decorative progress connector.
  final bool connected;

  /// Visual marker scale, independent of task state and layout.
  final UiStepSize size;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    if (steps.isEmpty) return const SizedBox.shrink();
    return LayoutBuilder(
      builder: (context, constraints) {
        final minWidth =
            ui.space.labelMin * MediaQuery.textScalerOf(context).scale(2);
        final horizontal =
            axis == Axis.horizontal ||
            (axis != Axis.vertical &&
                constraints.hasBoundedWidth &&
                constraints.maxWidth >=
                    steps.length * minWidth + (steps.length - 1) * ui.space.s4);
        final children = <Widget>[
          for (var i = 0; i < steps.length; i++)
            _StepTile(
              step: steps[i],
              position: i + 1,
              total: steps.length,
              style: style,
              compact: compact,
              size: size,
            ),
        ];
        if (!horizontal) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var i = 0; i < children.length; i++) ...[
                if (i > 0)
                  connected
                      ? Padding(
                          padding: EdgeInsetsDirectional.only(
                            start: ui.space.targetMin / 2,
                          ),
                          child: Align(
                            alignment: AlignmentDirectional.centerStart,
                            child: SizedBox(
                              width: ui.shape.stroke.emphasis,
                              height: ui.space.s4,
                              child: ColoredBox(
                                color:
                                    steps[i - 1].state == UiStepState.complete
                                    ? ui.brand.secondary.content
                                    : ui.color.boundary,
                              ),
                            ),
                          ),
                        )
                      : SizedBox(height: ui.space.s2),
                children[i],
              ],
            ],
          );
        }
        final row = Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var i = 0; i < children.length; i++) ...[
              if (i > 0)
                SizedBox(
                  width: ui.space.s4,
                  child: connected
                      ? Padding(
                          padding: EdgeInsets.only(top: ui.space.targetMin / 2),
                          child: SizedBox(
                            height: ui.shape.stroke.emphasis,
                            child: ColoredBox(
                              color: steps[i - 1].state == UiStepState.complete
                                  ? ui.brand.secondary.content
                                  : ui.color.boundary,
                            ),
                          ),
                        )
                      : null,
                ),
              Expanded(child: children[i]),
            ],
          ],
        );
        if (axis == Axis.horizontal &&
            constraints.maxWidth < steps.length * minWidth) {
          return SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SizedBox(
              width: steps.length * minWidth + (steps.length - 1) * ui.space.s4,
              child: row,
            ),
          );
        }
        return row;
      },
    );
  }
}

class _StepTile extends StatelessWidget {
  const _StepTile({
    required this.step,
    required this.position,
    required this.total,
    required this.style,
    required this.compact,
    required this.size,
  });

  /// The caller-supplied step.
  final UiStep step;

  /// The caller-supplied position.
  final int position;

  /// The caller-supplied total.
  final int total;

  /// The visual treatment, independent of the content or controlled state.
  final UiStepsStyle style;

  /// Whether compact token spacing is used.
  final bool compact;
  final UiStepSize size;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final status = switch (step.state) {
      UiStepState.upcoming => 'Upcoming',
      UiStepState.current => 'Current step',
      UiStepState.complete => 'Complete',
      UiStepState.error => 'Needs correction',
    };
    final colour = switch (step.state) {
      UiStepState.error => ui.color.status.blocked.content,
      UiStepState.complete => ui.color.status.cleared.content,
      _ => ui.color.ink,
    };
    final label = 'Step $position of $total, ${step.label}, $status';
    final icon = step.state == UiStepState.complete
        ? UiIcons.check
        : step.state == UiStepState.error
        ? UiIcons.blocked
        : step.icon;
    final markerSize = switch (size) {
      UiStepSize.small => ui.space.s8,
      UiStepSize.medium => ui.space.targetMin,
      UiStepSize.large => ui.space.s8 * 2,
    };
    final marker = Container(
      constraints: BoxConstraints(minWidth: markerSize, minHeight: markerSize),
      padding: EdgeInsets.all(ui.space.s2),
      decoration: BoxDecoration(
        color: step.state == UiStepState.current
            ? ui.brand.secondary.fill
            : null,
        borderRadius: BorderRadius.circular(ui.space.targetMin),
        border: Border.all(
          color: step.state == UiStepState.current
              ? ui.brand.secondary.content
              : ui.color.boundary,
          width: ui.shape.stroke.boundary,
        ),
      ),
      child: Center(
        child: icon != null
            ? UiIcon(icon, color: colour)
            : Text('$position', style: ui.type.label.copyWith(color: colour)),
      ),
    );
    final labels = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(step.label, style: ui.type.label.copyWith(color: ui.color.ink)),
        Text(status, style: ui.type.bodySmall.copyWith(color: colour)),
        if (step.description != null)
          Text(
            step.description!,
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
      ],
    );
    Widget alternative() {
      if (style == UiStepsStyle.iconOnly) {
        return Align(
          alignment: AlignmentDirectional.centerStart,
          child: marker,
        );
      }
      if (style == UiStepsStyle.textLine) {
        return Container(
          padding: EdgeInsets.only(top: ui.space.s3),
          decoration: BoxDecoration(
            border: Border(
              top: BorderSide(
                color: step.state == UiStepState.current
                    ? ui.brand.secondary.content
                    : ui.color.boundary,
                width: ui.shape.stroke.emphasis,
              ),
            ),
          ),
          child: labels,
        );
      }
      final left =
          style == UiStepsStyle.iconLeft || style == UiStepsStyle.featuredLeft;
      final body = left
          ? Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                marker,
                SizedBox(width: ui.space.s3),
                Expanded(child: labels),
              ],
            )
          : Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: marker,
                ),
                SizedBox(height: ui.space.s3),
                labels,
              ],
            );
      return style == UiStepsStyle.featuredLeft ||
              style == UiStepsStyle.featuredTop
          ? Surface(
              hairline: true,
              radius: ui.shape.tile,
              padding: EdgeInsets.all(compact ? ui.space.s2 : ui.space.s4),
              child: body,
            )
          : body;
    }

    Widget tile() => style != UiStepsStyle.cards
        ? alternative()
        : Surface(
            hairline: true,
            radius: ui.shape.tile,
            padding: EdgeInsets.all(compact ? ui.space.s2 : ui.space.s4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '$position / $total · $status',
                  style: ui.type.labelSmall.copyWith(color: colour),
                ),
                SizedBox(height: ui.space.s2),
                Text(
                  step.label,
                  style: ui.type.title.copyWith(color: ui.color.ink),
                ),
                if (step.description != null) ...[
                  SizedBox(height: ui.space.s1),
                  Text(
                    step.description!,
                    style: ui.type.bodySmall.copyWith(
                      color: ui.color.inkSecondary,
                    ),
                  ),
                ],
              ],
            ),
          );
    if (step.onSelected == null) {
      return Semantics(
        label: label,
        value: step.description,
        excludeSemantics: true,
        child: tile(),
      );
    }
    return Pressable(
      semanticsLabel: label,
      semanticsValue: step.description,
      selected: step.state == UiStepState.current,
      onPressed: step.onSelected,
      radius: ui.shape.tile,
      builder: (_, _) => tile(),
    );
  }
}
