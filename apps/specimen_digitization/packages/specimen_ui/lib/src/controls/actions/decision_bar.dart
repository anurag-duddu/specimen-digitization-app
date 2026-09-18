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
/// **Fit** (11 section 3.3; clause 15). Three arrangements, tried in order.
/// Every action on the line: the [tertiary] actions and then the [secondary]
/// beside the primary as ghost buttons, the way `UiButtonRow` reads them. Then
/// the tertiary actions in the bar's own overflow menu with the secondary still
/// beside the primary. Then the secondary in the menu too, carrying the same
/// label, so nothing a reviewer could do at 1400 dp is unreachable at 360. The
/// count is a [UiLabel] and ellipsises first. When no arrangement fits, the
/// primary ellipsises (rule 4), taking three parts of the line to the count's
/// one, and a bar carrying only a primary reaches that last resort the same
/// way: a single long decision at 200 percent text on a phone ellipsises
/// rather than overflowing (polish 3).
///
/// The bar measures its buttons through `UiButton.intrinsicWidth`, which
/// counts a glyph as well as the label, so the arrangement it chooses is the
/// one that fits.
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
    this.tertiary = const <UiButton>[],
    this.count,
    this.onPrevious,
    this.onNext,
    this.previousDisabledReason,
    this.nextDisabledReason,
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

  /// Anything else the screen offers from the bar, in reading order, drawn
  /// before [secondary] the way `UiButtonRow` draws its tertiary actions
  /// (11 section 3.4). They are the first to move into the overflow menu.
  ///
  /// A record whose approval has a prerequisite offers the save, the
  /// approval and the confirmation from one bar rather than choosing two.
  final List<UiButton> tertiary;

  /// Where the reviewer is in the run, such as "1 of 4".
  ///
  /// The caller's words: a count in a sentence is product copy.
  final String? count;

  /// Moves to the record before this one. Null where there is none.
  final VoidCallback? onPrevious;

  /// Moves to the record after this one. Null where there is none.
  final VoidCallback? onNext;

  /// Why there is no record before this one, in the reviewer's words, where
  /// [onPrevious] is null.
  ///
  /// The control is then drawn disabled with the reason on its hint and its
  /// tooltip (03 section 3.6), so the end of a queue says why rather than
  /// falling silent. With neither a move nor a reason the control is not
  /// drawn at all: a screen with no queue has nothing to move between, and a
  /// disabled control that never says why is the defect the reason exists to
  /// prevent.
  final String? previousDisabledReason;

  /// Why there is no record after this one, where [onNext] is null.
  final String? nextDisabledReason;

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
    final bool drawPrevious =
        edges && (onPrevious != null || previousDisabledReason != null);
    final bool drawNext =
        edges && (onNext != null || nextDisabledReason != null);
    final UiButton? second = secondary;
    // Everything beside the primary, in the order a row reads them: the
    // tertiary actions, then the secondary, then the primary itself.
    final List<UiButton> beside = <UiButton>[...tertiary, ?second];

    final double fixed = _fixedWidth(
      context,
      paint,
      drawPrevious: drawPrevious,
      drawNext: drawNext,
    );
    double ghostWidth(UiButton action) =>
        _ghost(action).intrinsicWidth(context) + paint.gap;
    final double menu = UiDensity.hitBox + paint.gap;
    final double allDrawn =
        fixed +
        beside.fold<double>(
          0,
          (double sum, UiButton action) => sum + ghostWidth(action),
        );
    final double tertiaryInMenu =
        fixed + (second == null ? 0 : ghostWidth(second)) + menu;
    final double allInMenu = fixed + menu;

    return SizedBox(
      height: paint.height,
      child: FitBuilder(
        variants: <FitVariant>[
          FitVariant(
            intrinsicWidth: allDrawn,
            builder: (BuildContext context, bool lastResort) => _row(
              context,
              paint,
              drawPrevious: drawPrevious,
              drawNext: drawNext,
              beside: beside,
              inMenu: const <UiButton>[],
              squeeze: lastResort,
            ),
          ),
          // The tertiary actions leave the line first, into the bar's own
          // menu, and the secondary stays beside the primary while the line
          // holds the two of them.
          if (tertiary.isNotEmpty && second != null)
            FitVariant(
              intrinsicWidth: tertiaryInMenu,
              builder: (BuildContext context, bool lastResort) => _row(
                context,
                paint,
                drawPrevious: drawPrevious,
                drawNext: drawNext,
                beside: <UiButton>[second],
                inMenu: tertiary,
                squeeze: lastResort,
              ),
            ),
          // Every other decision moves into the menu rather than being
          // dropped or squeezed: it is a decision, and a decision that is
          // unreachable at a phone width is a decision the product does not
          // offer on a phone. Below even that the primary is allowed to
          // ellipsise, which is the last resort 11 section 3.3 gives every
          // control and the only thing left to give.
          if (beside.isNotEmpty)
            FitVariant(
              intrinsicWidth: allInMenu,
              builder: (BuildContext context, bool lastResort) => _row(
                context,
                paint,
                drawPrevious: drawPrevious,
                drawNext: drawNext,
                beside: const <UiButton>[],
                inMenu: beside,
                squeeze: lastResort,
              ),
            ),
        ],
      ),
    );
  }

  /// The width of everything on the bar except the actions beside the
  /// primary: the edge controls that are drawn, the count, and the primary
  /// itself.
  double _fixedWidth(
    BuildContext context,
    UiDecisionBarStyle paint, {
    required bool drawPrevious,
    required bool drawNext,
  }) {
    final String? shown = count;
    return (drawPrevious ? UiDensity.hitBox + paint.gap : 0) +
        (drawNext ? UiDensity.hitBox + paint.gap : 0) +
        (shown == null
            ? 0
            : measureLabel(context, shown, paint.count).width + paint.gap) +
        primary.intrinsicWidth(context);
  }

  /// [action] as the bar draws it beside the primary: the ghost variant, with
  /// everything else the caller said kept.
  UiButton _ghost(UiButton action) => UiButton(
    label: action.label,
    variant: UiButtonVariant.ghost,
    size: action.size,
    onPressed: action.onPressed,
    disabledReason: action.disabledReason,
    leading: action.leading,
    trailing: action.trailing,
    loading: action.loading,
    semanticsLabel: action.semanticsLabel,
  );

  /// [action] as a row of the overflow menu, with the same label, glyph and
  /// reason.
  UiMenuItem _menuItem(UiButton action) => UiMenuItem(
    label: action.label,
    onSelected: action.onPressed,
    icon: action.leading,
    disabledReason: action.disabledReason,
  );

  Widget _row(
    BuildContext context,
    UiDecisionBarStyle paint, {
    required bool drawPrevious,
    required bool drawNext,
    required List<UiButton> beside,
    required List<UiButton> inMenu,
    required bool squeeze,
  }) {
    final String? shown = count;
    final Widget countLabel = UiLabel(
      shown ?? '',
      style: paint.count.copyWith(color: paint.countColor),
    );
    return Row(
      // With no count to hold the line's start, a squeezed row has nothing
      // to align its decisions against and lets the primary take the line.
      mainAxisAlignment: shown == null && squeeze
          ? MainAxisAlignment.end
          : MainAxisAlignment.start,
      children: <Widget>[
        if (drawPrevious) ...<Widget>[
          UiIconButton(
            icon: UiIcons.previous,
            semanticsLabel: previousLabel,
            onPressed: onPrevious,
            disabledReason: previousDisabledReason,
          ),
          SizedBox(width: paint.gap),
        ],
        // The count takes the line the decisions leave and ellipsises first.
        // It says where the reviewer is; the decision is what they came to
        // make, and a bar that shortened "Clear record" to keep "1 of 4"
        // whole would have its priorities backwards. At the last resort the
        // two share the line three to one, the decision's way.
        if (shown == null && !squeeze)
          const Spacer()
        else if (shown != null && squeeze)
          Flexible(child: countLabel)
        else if (shown != null)
          Expanded(child: countLabel),
        if (inMenu.isNotEmpty) ...<Widget>[
          UiMenuTrigger(
            semanticsLabel: overflowLabel,
            items: <UiMenuItem>[
              for (final UiButton action in inMenu) _menuItem(action),
            ],
          ),
          SizedBox(width: paint.gap),
        ],
        for (final UiButton action in beside) ...<Widget>[
          _ghost(action),
          SizedBox(width: paint.gap),
        ],
        if (squeeze) Flexible(flex: 3, child: primary) else primary,
        if (drawNext) ...<Widget>[
          SizedBox(width: paint.gap),
          UiIconButton(
            icon: UiIcons.next,
            semanticsLabel: nextLabel,
            onPressed: onNext,
            disabledReason: nextDisabledReason,
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
