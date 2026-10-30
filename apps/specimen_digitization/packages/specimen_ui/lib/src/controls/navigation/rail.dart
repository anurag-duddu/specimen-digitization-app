/// The navigation rail (10 section 4.4, `UiRail`).
library;

import 'dart:math' as math;

import 'package:flutter/semantics.dart' show SemanticsRole;
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/icons.dart';
import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../../primitives/label.dart';
import '../../primitives/popover.dart';
import '../../primitives/pressable.dart';
import '../overlays/tooltip.dart';
import 'nav_destination.dart';
import 'nav_group.dart';

/// Whether rail destinations need visible text in addition to named icons.
enum UiRailLabelPresentation {
  /// Icons on pointer-only desktops; labels below on touch or non-hover hosts.
  adaptive,

  /// Icon buttons with hover and keyboard-focus tooltips.
  icons,

  /// Every destination name is visible below its icon.
  below,
}

/// The resolved measurements of one rail (10 section 1.5).
///
/// The rail is the one control in the family whose width is measured rather
/// than fixed. Its collapsed form is a column of the pill's discs and is
/// always [minWidth]; its extended form draws the words under each glyph, and
/// a rail that kept 72 dp at 200 percent text would either clip them or wrap
/// a single word it cannot break. [resolve] measures the widest label at the
/// live text scale and widens the column to hold it, which is clause 7 of the
/// control contract applied to a vertical control: heights grow, widths grow
/// with them.
@immutable
class UiRailStyle {
  /// Binds every token the rail draws with.
  const UiRailStyle({
    required this.width,
    required this.discExtent,
    required this.discVisual,
    required this.itemExtent,
    required this.padding,
    required this.currentFill,
    required this.glide,
    required this.curve,
  });

  /// The column's width: [minWidth], or wider when a label needs it.
  final double width;

  /// The square one glyph is centred in, at the top of its destination.
  final double discExtent;

  /// The diameter of the `ink` disc under the current destination.
  final double discVisual;

  /// The height of one destination: [discExtent], plus the words when the
  /// rail is extended.
  final double itemExtent;

  /// The padding between a label and the column's edge.
  final double padding;

  /// The fill of the current destination's disc.
  final Color currentFill;

  /// How long the disc takes to glide, or zero under reduced motion.
  final Duration glide;

  /// The curve the disc glides on.
  final Curve curve;

  /// The 72 dp column of 10 section 4.4.
  ///
  /// Composed from the tokens rather than written as a number: a 48 dp hit
  /// box with 12 dp of gutter on each side. `space.rail` is the v1 rail at 80
  /// and still belongs to the screens that have not moved yet.
  static double minWidthOf(UiThemeData ui) => ui.space.targetMin + ui.space.s6;

  /// The style for [ui], measured for [destinations].
  ///
  /// [textScaler] and [textDirection] come from the context because the
  /// measurement has to be the one the labels will actually be laid out with.
  static UiRailStyle resolve(
    UiThemeData ui, {
    required bool extended,
    required List<UiNavDestination> destinations,
    required TextScaler textScaler,
    required TextDirection textDirection,
  }) {
    final double padding = ui.space.s2;
    final double minWidth = minWidthOf(ui);
    double widest = 0;
    double lineHeight = 0;
    if (extended) {
      final TextStyle label = ui.type.labelSmall;
      for (final UiNavDestination destination in destinations) {
        final TextPainter painter = TextPainter(
          text: TextSpan(text: destination.label, style: label),
          textDirection: textDirection,
          textScaler: textScaler,
          maxLines: 1,
        )..layout();
        widest = math.max(widest, painter.width);
        lineHeight = math.max(lineHeight, painter.height);
        painter.dispose();
      }
    }
    return UiRailStyle(
      width: extended ? math.max(minWidth, widest + padding * 2) : minWidth,
      discExtent: UiDensity.hitBox,
      discVisual: ui.density.controlHeight,
      itemExtent:
          UiDensity.hitBox +
          (extended ? ui.space.s1 + lineHeight + ui.space.s2 : 0),
      padding: padding,
      currentFill: ui.color.ink.withValues(alpha: ui.color.hoverOpacity),
      glide: ui.motion.navigationGlide,
      curve: MotionTokens.emphasizedCurve,
    );
  }
}

/// Compact primary navigation with quiet selection and filled Phosphor icons.
///
/// Pointer-only desktops expose each name on hover or keyboard focus. Touch
/// tablets and hybrids retain every label below its icon, including with a
/// trackpad attached. This policy reads input capabilities, never screen width.
/// Leading and footer slots share the scroller so short windows and large text
/// cannot strand account access outside the viewport.
///
/// Semantics: a tab list of tabs, one selected. `Up` and `Down` move between
/// them; `Enter` and `Space` select.
///
/// Retires `NavigationRail`.
class UiRail extends StatelessWidget {
  /// A rail over [destinations], with [currentIndex] filled.
  const UiRail({
    super.key,
    required this.destinations,
    required this.currentIndex,
    required this.onSelect,
    this.leading,
    this.footer,
    this.extended,
    this.labelPresentation = UiRailLabelPresentation.adaptive,
    this.semanticsLabel,
  });

  /// The destinations, in order.
  final List<UiNavDestination> destinations;

  /// Which destination the reviewer is on.
  final int currentIndex;

  /// Goes to the destination at the given index.
  final ValueChanged<int> onSelect;

  /// What sits above the destinations. The mark, on every screen that has
  /// one.
  final Widget? leading;

  /// Account or utility actions, at the bottom when height permits.
  final Widget? footer;

  /// Legacy explicit label override. Null uses [labelPresentation].
  /// True keeps labels below icons; false keeps the icon-only presentation.
  final bool? extended;

  /// Label policy, shared by the rendered rail and [widthOf].
  final UiRailLabelPresentation labelPresentation;

  /// What the tab list is called to a screen reader, or null for no name.
  ///
  /// WAI-ARIA asks a tab list for a name when a page has more than one, and
  /// the shell's rail sits beside a record that has tabs of its own, so a
  /// screen reader user hears which list they are in. The destinations keep
  /// their own labels either way.
  final String? semanticsLabel;

  /// The fewest destinations a rail may hold.
  ///
  /// The same floor as the pill: one destination is a title, not a
  /// navigation. There is no ceiling, because a column has room a capsule
  /// does not.
  static const int minDestinations = 2;

  /// Resolves visible names from capabilities without relying on viewport size.
  static bool showsLabelsOf(
    BuildContext context, {
    UiRailLabelPresentation labelPresentation =
        UiRailLabelPresentation.adaptive,
    bool? extended,
  }) {
    if (extended != null) return extended;
    return switch (labelPresentation) {
      UiRailLabelPresentation.icons => false,
      UiRailLabelPresentation.below => true,
      UiRailLabelPresentation.adaptive =>
        Density.inputsOf(context).touch || !Density.inputsOf(context).hover,
    };
  }

  /// The same measured width used to render the rail at this text scale.
  static double widthOf(
    BuildContext context, {
    required List<UiNavDestination> destinations,
    UiRailLabelPresentation labelPresentation =
        UiRailLabelPresentation.adaptive,
    bool? extended,
  }) => UiRailStyle.resolve(
    context.ui,
    extended: showsLabelsOf(
      context,
      labelPresentation: labelPresentation,
      extended: extended,
    ),
    destinations: destinations,
    textScaler: MediaQuery.textScalerOf(context),
    textDirection: Directionality.of(context),
  ).width;

  @override
  Widget build(BuildContext context) {
    assert(
      destinations.length >= minDestinations,
      'A rail holds at least $minDestinations destinations and was given '
      '${destinations.length}. One destination is a title, not a navigation.',
    );
    final UiThemeData ui = context.ui;
    final showLabels = showsLabelsOf(
      context,
      labelPresentation: labelPresentation,
      extended: extended,
    );
    final UiRailStyle style = UiRailStyle.resolve(
      ui,
      extended: showLabels,
      destinations: destinations,
      textScaler: MediaQuery.textScalerOf(context),
      textDirection: Directionality.of(context),
    );
    final int current = currentIndex.clamp(0, destinations.length - 1);

    final navigation = NavGroup(
      length: destinations.length,
      axis: NavAxis.vertical,
      builder: (BuildContext context, List<FocusNode> nodes) => Semantics(
        container: true,
        explicitChildNodes: true,
        role: SemanticsRole.tabBar,
        label: semanticsLabel,
        child: SizedBox(
          height: style.itemExtent * destinations.length,
          child: Stack(
            children: <Widget>[
              // Signature motion 1 (09 section 8), running down the
              // column instead of along the capsule. Start and end are
              // both pinned so the disc stays centred in the column at
              // any width, in either direction.
              AnimatedPositionedDirectional(
                top: style.itemExtent * current,
                start: 0,
                end: 0,
                height: style.discExtent,
                duration: style.glide,
                curve: style.curve,
                child: Center(
                  child: SizedBox.square(
                    dimension: style.discVisual,
                    child: DecoratedBox(
                      decoration: ShapeDecoration(
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(ui.shape.inner),
                        ),
                        color: style.currentFill,
                      ),
                    ),
                  ),
                ),
              ),
              Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  for (int i = 0; i < destinations.length; i++)
                    _destination(
                      context,
                      style,
                      i,
                      current: i == current,
                      showLabel: showLabels,
                      focusNode: nodes[i],
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
    return SizedBox(
      width: style.width,
      child: LayoutBuilder(
        builder: (context, constraints) => SingleChildScrollView(
          child: ConstrainedBox(
            constraints: BoxConstraints(
              minHeight: constraints.hasBoundedHeight
                  ? constraints.maxHeight
                  : 0,
            ),
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: ui.space.s3),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (leading != null) ...[
                        leading!,
                        SizedBox(height: ui.space.s6),
                      ],
                      navigation,
                    ],
                  ),
                  if (footer != null)
                    Padding(
                      padding: EdgeInsets.only(top: ui.space.s6),
                      child: footer,
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _destination(
    BuildContext context,
    UiRailStyle style,
    int index, {
    required bool current,
    required bool showLabel,
    required FocusNode focusNode,
  }) {
    final ui = context.ui;
    final destination = destinations[index];
    final control = Pressable(
      semanticsLabel: destination.label,
      role: PressableRole.tab,
      selected: current,
      focusNode: focusNode,
      radius: ui.shape.inner,
      onPressed: () => onSelect(index),
      builder: (context, states) => SizedBox(
        height: style.itemExtent,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox.square(
              dimension: style.discExtent,
              child: Center(
                child: UiIcon(
                  destination.icon,
                  current: current,
                  color: current ? ui.color.ink : ui.color.inkSecondary,
                ),
              ),
            ),
            if (showLabel) ...[
              SizedBox(height: ui.space.s1),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: style.padding),
                child: UiLabel(
                  destination.label,
                  style: ui.type.labelSmall.copyWith(
                    color: current ? ui.color.ink : ui.color.inkSecondary,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
          ],
        ),
      ),
    );
    return showLabel
        ? control
        : MergeSemantics(
            child: UiTooltip(
              message: destination.label,
              placement: PopoverPlacement.end,
              excludeSemantics: true,
              child: control,
            ),
          );
  }
}
