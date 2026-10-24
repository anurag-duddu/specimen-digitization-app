/// The navigation sidebar (10 section 4.4, `UiSidebar`).
library;

import 'dart:math' as math;

import 'package:flutter/semantics.dart' show SemanticsRole;
import 'package:flutter/widgets.dart';

import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/pressable.dart';
import 'nav_destination.dart';
import 'nav_group.dart';

/// The resolved measurements of one sidebar (10 section 1.5).
@immutable
class UiSidebarStyle {
  /// Binds every token the sidebar draws with.
  const UiSidebarStyle({
    required this.width,
    required this.slotPadding,
    required this.currentContent,
    required this.restContent,
    this.rowMinHeight,
    this.rowPadding,
    this.barWidth,
    this.barColor,
  });

  /// The pane's width, measured from labels and the reader's text scale.
  final double width;

  /// The least a destination row may be. Grows with the words in it.
  ///
  /// Carried for compatibility and no longer read. Destination rows size
  /// from their content and retain the shared 48 dp minimum hit target.
  @Deprecated('Destination rows size from their content. Drop this argument.')
  final double? rowMinHeight;

  /// The padding inside one destination row, past the leading bar.
  ///
  /// Carried for one version and no longer read: see [rowMinHeight].
  @Deprecated('Navigation owns its content padding. Drop this argument.')
  final EdgeInsetsGeometry? rowPadding;

  /// The padding around the header and the footer slots.
  final EdgeInsetsGeometry slotPadding;

  /// The leading bar on the current row. 3 dp (09 section 5).
  ///
  /// Carried for one version and no longer read: see [rowMinHeight].
  @Deprecated('Navigation selection has no leading stripe. Drop this argument.')
  final double? barWidth;

  /// The bar's colour.
  ///
  /// Carried for one version and no longer read: see [rowMinHeight].
  @Deprecated('Navigation selection has no leading stripe. Drop this argument.')
  final Color? barColor;

  /// The glyph of the current destination.
  final Color currentContent;

  /// The glyph of every other destination.
  final Color restContent;

  /// The style for [ui], sized around a short navigation label and its icon.
  ///
  /// Fourteen label ems provide room for the workspace/account slots. Longer
  /// destination labels widen the pane. Icons follow adjacent text; gutters remain fixed.
  static UiSidebarStyle resolve(
    UiThemeData ui, {
    TextScaler textScaler = TextScaler.noScaling,
    TextDirection textDirection = TextDirection.ltr,
    List<UiNavDestination> destinations = const [],
  }) {
    final inset = ui.space.s4;
    final iconAndGap =
        ui.space.iconInline *
            textScaler.scale(ui.type.body.fontSize!) /
            ui.type.body.fontSize! +
        ui.space.s2;
    var labelWidth = 0.0;
    for (final destination in destinations) {
      final painter = TextPainter(
        text: TextSpan(text: destination.label, style: ui.type.body),
        textScaler: textScaler,
        textDirection: textDirection,
        maxLines: 1,
      )..layout();
      labelWidth = math.max(labelWidth, painter.width);
      painter.dispose();
    }
    return UiSidebarStyle(
      width: math.max(
        textScaler.scale(ui.type.label.fontSize!) * 14 + iconAndGap,
        labelWidth + iconAndGap + inset * 4,
      ),
      slotPadding: EdgeInsetsDirectional.all(inset),
      currentContent: ui.brand.secondary.content,
      restContent: ui.color.inkSecondary,
    );
  }
}

/// A quiet, labelled application sidebar on a flat Paper surface.
///
/// Selection is a subtle rounded fill and accent text, with no leading stripe
/// or heavy filled glyph. Header and footer are slots; the footer settles at
/// the bottom when there is room. The entire pane scrolls in short windows,
/// including large text, so account and workspace controls remain reachable.
///
/// Destinations retain the tab semantics and arrow-key behavior shared with
/// compact navigation. Enter and Space activate the focused destination.
class UiSidebar extends StatelessWidget {
  /// A sidebar over [destinations], with [currentIndex] current.
  const UiSidebar({
    super.key,
    required this.destinations,
    required this.currentIndex,
    required this.onSelect,
    this.header,
    this.footer,
    this.semanticsLabel,
  });

  /// The destinations, in order.
  final List<UiNavDestination> destinations;

  /// Which destination the reviewer is on.
  final int currentIndex;

  /// Goes to the destination at the given index.
  final ValueChanged<int> onSelect;

  /// What sits above the destinations: the mark and the product name.
  ///
  /// The collection switcher belongs here too, as a `UiSelect` the shell
  /// passes in, which is why this is a slot rather than a set of fields.
  final Widget? header;

  /// What sits at the bottom of the pane: the account and the help entry.
  final Widget? footer;

  /// Accessible name when the page contains other navigation groups.
  final String? semanticsLabel;

  /// The pane's intrinsic width for these destinations and this reader.
  static double widthOf(
    BuildContext context, {
    List<UiNavDestination> destinations = const [],
  }) => UiSidebarStyle.resolve(
    context.ui,
    textScaler: MediaQuery.textScalerOf(context),
    textDirection: Directionality.of(context),
    destinations: destinations,
  ).width;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final style = UiSidebarStyle.resolve(
      ui,
      textScaler: MediaQuery.textScalerOf(context),
      textDirection: Directionality.of(context),
      destinations: destinations,
    );
    final current = currentIndex.clamp(0, destinations.length - 1);
    return ColoredBox(
      color: ui.color.paper,
      child: SizedBox(
        width: style.width,
        child: LayoutBuilder(
          builder: (context, constraints) => SingleChildScrollView(
            child: ConstrainedBox(
              constraints: BoxConstraints(minHeight: constraints.maxHeight),
              child: Padding(
                padding: style.slotPadding,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (header != null) ...[
                          header!,
                          SizedBox(height: ui.space.s6),
                        ],
                        NavGroup(
                          length: destinations.length,
                          axis: NavAxis.vertical,
                          builder: (context, nodes) => Semantics(
                            container: true,
                            explicitChildNodes: true,
                            role: SemanticsRole.tabBar,
                            label: semanticsLabel,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                for (var i = 0; i < destinations.length; i++)
                                  _row(
                                    context,
                                    style,
                                    i,
                                    current: i == current,
                                    focusNode: nodes[i],
                                  ),
                              ],
                            ),
                          ),
                        ),
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
      ),
    );
  }

  Widget _row(
    BuildContext context,
    UiSidebarStyle style,
    int index, {
    required bool current,
    required FocusNode focusNode,
  }) {
    final ui = context.ui;
    final destination = destinations[index];
    final ink = current ? style.currentContent : style.restContent;
    return Pressable(
      semanticsLabel: destination.label,
      role: PressableRole.tab,
      selected: current,
      focusNode: focusNode,
      radius: ui.shape.inner,
      onPressed: () => onSelect(index),
      builder: (context, states) => DecoratedBox(
        decoration: BoxDecoration(
          color: current ? ui.color.accent.withValues(alpha: .08) : null,
          borderRadius: BorderRadius.circular(ui.shape.inner),
        ),
        child: Padding(
          padding: EdgeInsets.all(ui.space.s2),
          child: Row(
            children: [
              UiIcon(
                destination.icon,
                size: UiIconSize.inline,
                textStyle: ui.type.body,
                color: ink,
              ),
              SizedBox(width: ui.space.s2),
              Expanded(
                child: Text(
                  destination.label,
                  style: ui.type.body.copyWith(
                    color: ink,
                    fontWeight: current ? FontWeight.w600 : FontWeight.w400,
                    fontVariations: [
                      FontVariation('wght', current ? 600 : 400),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
