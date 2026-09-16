/// The navigation sidebar (10 section 4.4, `UiSidebar`).
library;

import 'package:flutter/semantics.dart' show SemanticsRole;
import 'package:flutter/widgets.dart';

import '../../foundation/glass.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/glass_surface.dart';
import '../../primitives/pressable.dart';
import 'nav_destination.dart';
import 'nav_group.dart';

/// The resolved measurements of one sidebar (10 section 1.5).
@immutable
class UiSidebarStyle {
  /// Binds every token the sidebar draws with.
  const UiSidebarStyle({
    required this.width,
    required this.rowMinHeight,
    required this.rowPadding,
    required this.slotPadding,
    required this.barWidth,
    required this.barColor,
    required this.currentContent,
    required this.restContent,
  });

  /// The pane's width. 280 dp (10 section 4.4).
  final double width;

  /// The least a destination row may be. Grows with the words in it.
  final double rowMinHeight;

  /// The padding inside one destination row, past the leading bar.
  final EdgeInsetsGeometry rowPadding;

  /// The padding around the header and the footer slots.
  final EdgeInsetsGeometry slotPadding;

  /// The leading bar on the current row. 3 dp (09 section 5).
  final double barWidth;

  /// The bar's colour.
  final Color barColor;

  /// The glyph and words of the current destination.
  final Color currentContent;

  /// The glyph and words of every other destination.
  final Color restContent;

  /// The 280 dp pane of 10 section 4.4.
  static const double defaultWidth = 280;

  /// The style for [ui].
  static UiSidebarStyle resolve(UiThemeData ui) => UiSidebarStyle(
    width: defaultWidth,
    rowMinHeight: ui.density.rowHeight,
    rowPadding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s4),
    slotPadding: EdgeInsetsDirectional.all(ui.space.s4),
    barWidth: ui.shape.stroke.bar,
    barColor: ui.color.ink,
    currentContent: ui.color.ink,
    restContent: ui.color.inkSecondary,
  );
}

/// A 280 dp `glass.flat` pane of destinations for a large window.
///
/// The header slot carries the mark and the product name; the footer slot
/// carries whatever belongs at the bottom of the pane. Destinations are rows
/// rather than discs, and the current one is marked three ways: the 3 dp
/// leading bar in `ink`, the `fill` weight of its glyph, and `ink` rather than
/// `ink.secondary` for both. 10 section 4.5 also gives a selected
/// `UiListRow` a 6 percent `ink` fill; there is no token for that value yet
/// and this control does not invent one, so the three channels above carry
/// the state instead.
///
/// The pane needs a bounded height, which is what a scaffold gives it. The
/// header and the footer hold their places and the destinations scroll
/// between them when there are more of them than the pane can show.
///
/// Semantics: a tab list of tabs, one selected. `Up` and `Down` move between
/// them; `Enter` and `Space` select.
///
/// Retires `Drawer` and the permanent drawer.
class UiSidebar extends StatelessWidget {
  /// A sidebar over [destinations], with [currentIndex] current.
  const UiSidebar({
    super.key,
    required this.destinations,
    required this.currentIndex,
    required this.onSelect,
    this.header,
    this.footer,
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

  /// The pane's width.
  static double widthOf(BuildContext context) =>
      UiSidebarStyle.resolve(context.ui).width;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiSidebarStyle style = UiSidebarStyle.resolve(ui);
    final int current = currentIndex.clamp(0, destinations.length - 1);

    return GlassSurface(
      level: GlassLevel.flat,
      // An edge pane, flush with the window. A superellipse corner here would
      // show the ground through the outer corners of a pane that has none.
      radius: ui.shape.none,
      child: SizedBox(
        width: style.width,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            if (header != null)
              Padding(padding: style.slotPadding, child: header),
            // The destinations take the space the header and the footer
            // leave and scroll inside it. A pane 280 dp wide with five
            // destinations at 200 percent text is taller than a window the
            // sidebar is meant for, and a reviewer who cannot reach the last
            // destination has lost the navigation (10 section 2 clause 7).
            Expanded(
              child: SingleChildScrollView(
                child: NavGroup(
                  length: destinations.length,
                  axis: NavAxis.vertical,
                  builder: (BuildContext context, List<FocusNode> nodes) =>
                      Semantics(
                        container: true,
                        explicitChildNodes: true,
                        role: SemanticsRole.tabBar,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          mainAxisSize: MainAxisSize.min,
                          children: <Widget>[
                            for (int i = 0; i < destinations.length; i++)
                              _SidebarRow(
                                destination: destinations[i],
                                current: i == current,
                                style: style,
                                focusNode: nodes[i],
                                onPressed: () => onSelect(i),
                              ),
                          ],
                        ),
                      ),
                ),
              ),
            ),
            if (footer != null)
              Padding(padding: style.slotPadding, child: footer),
          ],
        ),
      ),
    );
  }
}

// TODO(fe/data): replace with UiListRow when it merges.
// The row below is the anatomy 10 section 4.5 gives a selectable `UiListRow`,
// built here on `Pressable` so the navigation family does not wait on the
// data family. When `UiListRow` lands the swap is cosmetic: the leading bar,
// the glyph, the title role and the semantics are the same.
class _SidebarRow extends StatelessWidget {
  const _SidebarRow({
    required this.destination,
    required this.current,
    required this.style,
    required this.focusNode,
    required this.onPressed,
  });

  final UiNavDestination destination;
  final bool current;
  final UiSidebarStyle style;
  final FocusNode focusNode;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final Color content = current ? style.currentContent : style.restContent;
    return Pressable(
      semanticsLabel: destination.label,
      role: PressableRole.tab,
      selected: current,
      radius: ui.shape.inner,
      focusNode: focusNode,
      onPressed: onPressed,
      builder: (BuildContext context, Set<WidgetState> states) => DecoratedBox(
        // Every row carries the bar so the current one does not shift its
        // words 3 dp inward when it becomes current. Only its colour changes.
        decoration: BoxDecoration(
          border: BorderDirectional(
            start: BorderSide(
              color: current
                  ? style.barColor
                  : style.barColor.withValues(alpha: 0),
              width: style.barWidth,
            ),
          ),
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: style.rowMinHeight),
          child: Padding(
            padding: style.rowPadding,
            child: Row(
              children: <Widget>[
                UiIcon(
                  destination.icon,
                  size: UiIconSize.action,
                  current: current,
                  color: content,
                ),
                SizedBox(width: ui.space.s3),
                Expanded(
                  child: Text(
                    destination.label,
                    style: ui.type.title.copyWith(color: content),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
