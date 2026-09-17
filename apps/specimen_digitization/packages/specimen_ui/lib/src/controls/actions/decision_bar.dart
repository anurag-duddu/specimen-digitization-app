/// The decision bar (13 section 3.3, `UiDecisionBar`).
library;

import 'dart:math' as math;

import 'package:flutter/gestures.dart' show kMinFlingVelocity;
import 'package:flutter/semantics.dart' show CustomSemanticsAction;
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../foundation/window.dart';
import '../../primitives/fit.dart';
import '../../primitives/label.dart';
import '../overlays/popover_menu.dart';
import 'button.dart';
import 'icon_button.dart';

/// The resolved measurements of one decision bar (10 section 1.5).
@immutable
class UiDecisionBarStyle {
  /// Binds every token the bar draws with.
  const UiDecisionBarStyle({
    required this.height,
    required this.gap,
    required this.count,
    required this.countColor,
  });

  /// The bar's one row: `density.controlHeight` grown by the text it holds,
  /// floored at the hit box the edge buttons need (13 section 2.3).
  ///
  /// The padding around it belongs to the scaffold's action bar pane, which
  /// is where the bar sits, so 48 here is 64 on screen.
  final double height;

  /// The gap between the bar's parts.
  final double gap;

  /// The type role the count is set in.
  final TextStyle count;

  /// The ink the count is drawn in.
  final Color countColor;

  /// The style for [ui] at the text scale [context] is painted at.
  static UiDecisionBarStyle resolve(UiThemeData ui, BuildContext context) {
    final UiDensity density = Density.of(context);
    return UiDecisionBarStyle(
      height: math.max(
        UiDensity.hitBox,
        UiType.controlHeightFor(density, ui.type.label, context),
      ),
      gap: ui.space.s2,
      count: ui.type.label,
      countColor: ui.color.inkSecondary,
    );
  }
}

/// The one row at the bottom of a screen that decides (13 section 3.3).
///
/// A primary action, an optional secondary, the count of where the reviewer
/// is, and, from `medium` up, previous and next as buttons on the bar's two
/// edges. At compact those two are a swipe instead, which is what
/// [UiDecisionSwipe] is for: five controls do not fit on a phone's line and
/// the two that move between records are the two the reviewer's thumb can do
/// without.
///
/// **Fit** (11 section 3.3; clause 15). Two arrangements. The secondary sits
/// beside the primary as a ghost button while the line holds both; below that
/// it moves into the bar's own overflow menu, carrying the same label, so
/// nothing a reviewer could do at 1400 dp is unreachable at 360. The count is
/// a [UiLabel] and ellipsises last.
///
/// It goes in the scaffold's action bar, which a routed screen fills through
/// `UiScaffoldSlots.of(context).setActionBar`, so the shell owns the bottom
/// of the screen and the chrome budget with it.
///
/// ```dart
/// UiScaffoldSlots.of(context)?.setActionBar(
///   UiDecisionBar(
///     primary: UiButton(label: 'Clear record', onPressed: clear),
///     secondary: UiButton(label: 'Defer', onPressed: defer),
///     count: '1 of 4',
///     onPrevious: previous,
///     onNext: next,
///   ),
/// );
/// ```
class UiDecisionBar extends StatelessWidget {
  /// A bar whose decision is [primary].
  const UiDecisionBar({
    super.key,
    required this.primary,
    this.secondary,
    this.count,
    this.onPrevious,
    this.onNext,
    this.previousLabel = defaultPreviousLabel,
    this.nextLabel = defaultNextLabel,
    this.overflowLabel = defaultOverflowLabel,
    this.style,
  });

  /// The action the screen exists to take.
  ///
  /// Typed rather than a `Widget` slot, because "one primary action" is a
  /// rule and a type states a rule better than a comment does
  /// (10 section 4.5).
  final UiButton primary;

  /// The other decision, beside the primary or in the overflow.
  final UiButton? secondary;

  /// Where the reviewer is in the run, such as "1 of 4".
  ///
  /// The caller's words: a count in a sentence is product copy.
  final String? count;

  /// Moves to the record before this one. Null where there is none.
  final VoidCallback? onPrevious;

  /// Moves to the record after this one. Null where there is none.
  final VoidCallback? onNext;

  /// What the previous control is called.
  final String previousLabel;

  /// What the next control is called.
  final String nextLabel;

  /// What the overflow trigger is called.
  final String overflowLabel;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiDecisionBarStyle? style;

  /// The default label of the previous control.
  static const String defaultPreviousLabel = 'Previous record';

  /// The default label of the next control.
  static const String defaultNextLabel = 'Next record';

  /// The default label of the overflow trigger.
  static const String defaultOverflowLabel = 'More decisions';

  /// True where the bar draws previous and next as edge buttons.
  ///
  /// From `medium` up. The bar is a pattern rather than a control, and a
  /// pattern chooses its arrangement by window class (11 section 3.1).
  static bool edgesAt(BuildContext context) =>
      WindowClass.of(context).isAtLeast(WindowClass.medium);

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiDecisionBarStyle paint =
        style ?? UiDecisionBarStyle.resolve(ui, context);
    final bool edges = edgesAt(context);
    final UiButton? second = secondary;

    final double intrinsic =
        _fixedWidth(context, paint, edges: edges) +
        (second == null
            ? 0
            : _buttonWidth(context, ui, second.label, UiButtonVariant.ghost) +
                  paint.gap);

    return SizedBox(
      height: paint.height,
      child: FitBuilder(
        variants: <FitVariant>[
          FitVariant(
            intrinsicWidth: intrinsic,
            builder: (BuildContext context, bool _) =>
                _row(context, paint, edges: edges, overflowed: false),
          ),
          // The secondary decision moves into the bar's own menu rather than
          // being dropped or squeezed: it is a decision, and a decision that
          // is unreachable at a phone width is a decision the product does
          // not offer on a phone.
          FitVariant(
            intrinsicWidth: 0,
            builder: (BuildContext context, bool _) =>
                _row(context, paint, edges: edges, overflowed: second != null),
          ),
        ],
      ),
    );
  }

  /// The width of everything on the bar except the secondary's own button.
  double _fixedWidth(
    BuildContext context,
    UiDecisionBarStyle paint, {
    required bool edges,
  }) {
    final UiThemeData ui = context.ui;
    final String? shown = count;
    return (edges ? 2 * (UiDensity.hitBox + paint.gap) : 0) +
        (shown == null
            ? 0
            : measureLabel(context, shown, paint.count).width + paint.gap) +
        _buttonWidth(context, ui, primary.label, primary.variant);
  }

  /// What one of the bar's buttons takes: its label at the live text scale
  /// plus the padding its own style gives it.
  ///
  /// Read from `UiButtonStyle` rather than estimated, because a bar that
  /// guesses low keeps an arrangement that does not fit and overflows in the
  /// one case the variants exist to prevent.
  double _buttonWidth(
    BuildContext context,
    UiThemeData ui,
    String label,
    UiButtonVariant variant,
  ) {
    final UiButtonStyle style = UiButtonStyle.resolve(ui, variant, UiSize.md);
    return measureLabel(context, label, style.label).width +
        style.padding.resolve(Directionality.of(context)).horizontal;
  }

  Widget _row(
    BuildContext context,
    UiDecisionBarStyle paint, {
    required bool edges,
    required bool overflowed,
  }) {
    final UiButton? second = secondary;
    final String? shown = count;
    return Row(
      children: <Widget>[
        if (edges) ...<Widget>[
          UiIconButton(
            icon: UiIcons.previous,
            semanticsLabel: previousLabel,
            onPressed: onPrevious,
          ),
          SizedBox(width: paint.gap),
        ],
        // The count takes the line the decisions leave and ellipsises first.
        // It says where the reviewer is; the decision is what they came to
        // make, and a bar that shortened "Clear record" to keep "1 of 4"
        // whole would have its priorities backwards.
        if (shown == null)
          const Spacer()
        else
          Expanded(
            child: UiLabel(
              shown,
              style: paint.count.copyWith(color: paint.countColor),
            ),
          ),
        if (second != null && overflowed) ...<Widget>[
          UiMenuTrigger(
            semanticsLabel: overflowLabel,
            items: <UiMenuItem>[
              UiMenuItem(label: second.label, onSelected: second.onPressed),
            ],
          ),
          SizedBox(width: paint.gap),
        ],
        if (second != null && !overflowed) ...<Widget>[
          UiButton(
            label: second.label,
            variant: UiButtonVariant.ghost,
            onPressed: second.onPressed,
            disabledReason: second.disabledReason,
          ),
          SizedBox(width: paint.gap),
        ],
        primary,
        if (edges) ...<Widget>[
          SizedBox(width: paint.gap),
          UiIconButton(
            icon: UiIcons.next,
            semanticsLabel: nextLabel,
            onPressed: onNext,
          ),
        ],
      ],
    );
  }
}

/// Previous and next as a swipe, for the compact window where
/// [UiDecisionBar] draws no edge buttons (13 section 3.3).
///
/// Wraps the region the reviewer is looking at, which is the evidence rather
/// than the bar: a thumb moves the record, not the control that decides it.
/// A horizontal fling in the reading direction moves forward and one against
/// it moves back, flipped under right to left, so the gesture means the same
/// thing in both directions of text.
///
/// The two moves also reach a screen reader, as named custom actions rather
/// than as a gesture nobody can see. A swipe with no visible control is
/// exactly the case the custom action list exists for.
///
/// ```dart
/// UiDecisionSwipe(
///   onPrevious: previous,
///   onNext: next,
///   child: CustomScrollView(slivers: <Widget>[...]),
/// )
/// ```
class UiDecisionSwipe extends StatelessWidget {
  /// Moves between records by a fling across [child].
  const UiDecisionSwipe({
    super.key,
    required this.child,
    this.onPrevious,
    this.onNext,
    this.previousLabel = UiDecisionBar.defaultPreviousLabel,
    this.nextLabel = UiDecisionBar.defaultNextLabel,
  });

  /// The region the gesture is made over.
  final Widget child;

  /// Moves to the record before this one. Null where there is none.
  final VoidCallback? onPrevious;

  /// Moves to the record after this one. Null where there is none.
  final VoidCallback? onNext;

  /// What the previous move is called, for a screen reader.
  final String previousLabel;

  /// What the next move is called, for a screen reader.
  final String nextLabel;

  @override
  Widget build(BuildContext context) {
    final bool rtl = Directionality.of(context) == TextDirection.rtl;
    final Map<CustomSemanticsAction, VoidCallback> actions =
        <CustomSemanticsAction, VoidCallback>{
          if (onPrevious case final VoidCallback move)
            CustomSemanticsAction(label: previousLabel): move,
          if (onNext case final VoidCallback move)
            CustomSemanticsAction(label: nextLabel): move,
        };
    return Semantics(
      customSemanticsActions: actions.isEmpty ? null : actions,
      child: GestureDetector(
        // Translucent rather than opaque: the evidence under the gesture is
        // still pressable, and a horizontal fling is what this recognises
        // rather than every touch that lands on it.
        behavior: HitTestBehavior.translucent,
        onHorizontalDragEnd: (DragEndDetails details) {
          final double velocity = details.primaryVelocity ?? 0;
          if (velocity.abs() < kMinFlingVelocity) return;
          final bool forward = rtl ? velocity > 0 : velocity < 0;
          (forward ? onNext : onPrevious)?.call();
        },
        child: child,
      ),
    );
  }
}
