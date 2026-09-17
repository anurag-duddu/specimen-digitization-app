/// The navigation sidebar (10 section 4.4, `UiSidebar`).
library;

import 'package:flutter/semantics.dart' show SemanticsRole;
import 'package:flutter/widgets.dart';

import '../../foundation/glass.dart';
import '../../foundation/icons.dart';
import '../../foundation/theme.dart';
import '../../primitives/glass_surface.dart';
import '../data/list_row.dart';
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

  /// The pane's width. 280 dp (10 section 4.4).
  final double width;

  /// The least a destination row may be. Grows with the words in it.
  ///
  /// Carried for one version and no longer read: a destination is a
  /// `UiListRow`, which takes its height from `UiListRowStyle`.
  @Deprecated(
    'Replaced by UiListRowStyle.heightOf. Drop the argument; this member '
    'goes in the next minor version.',
  )
  final double? rowMinHeight;

  /// The padding inside one destination row, past the leading bar.
  ///
  /// Carried for one version and no longer read: see [rowMinHeight].
  @Deprecated(
    'Replaced by UiListRowStyle.padding. Drop the argument; this member goes '
    'in the next minor version.',
  )
  final EdgeInsetsGeometry? rowPadding;

  /// The padding around the header and the footer slots.
  final EdgeInsetsGeometry slotPadding;

  /// The leading bar on the current row. 3 dp (09 section 5).
  ///
  /// Carried for one version and no longer read: see [rowMinHeight].
  @Deprecated(
    'Replaced by UiListRowStyle.barWidth. Drop the argument; this member goes '
    'in the next minor version.',
  )
  final double? barWidth;

  /// The bar's colour.
  ///
  /// Carried for one version and no longer read: see [rowMinHeight].
  @Deprecated(
    'Replaced by UiListRowStyle.bar. Drop the argument; this member goes in '
    'the next minor version.',
  )
  final Color? barColor;

  /// The glyph of the current destination.
  final Color currentContent;

  /// The glyph of every other destination.
  final Color restContent;

  /// The 280 dp pane of 10 section 4.4.
  static const double defaultWidth = 280;

  /// The style for [ui].
  static UiSidebarStyle resolve(UiThemeData ui) => UiSidebarStyle(
    width: defaultWidth,
    slotPadding: EdgeInsetsDirectional.all(ui.space.s4),
    currentContent: ui.color.ink,
    restContent: ui.color.inkSecondary,
  );
}

/// A 280 dp `glass.flat` pane of destinations for a large window.
///
/// The header slot carries the mark and the product name; the footer slot
/// carries whatever belongs at the bottom of the pane. Destinations are
/// `UiListRow`s rather than discs, and the current one is marked four ways:
/// the 6 percent `ink` fill and the 3 dp leading bar the selectable row of
/// 10 section 4.5 draws, plus the `fill` weight of its glyph and `ink` rather
/// than `ink.secondary` for it.
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
                              _row(
                                style,
                                i,
                                current: i == current,
                                focusNode: nodes[i],
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

  /// One destination.
  ///
  /// The selectable `UiListRow` of 10 section 4.5, in its `tab` mode: the
  /// pane publishes a tab list, so every row in it has to be a tab. The row
  /// draws the fill and the bar; the glyph carries the other two channels.
  Widget _row(
    UiSidebarStyle style,
    int index, {
    required bool current,
    required FocusNode focusNode,
  }) {
    final UiNavDestination destination = destinations[index];
    return UiListRow(
      title: destination.label,
      mode: UiListRowMode.tab,
      selected: current,
      focusNode: focusNode,
      onPressed: () => onSelect(index),
      leading: UiIcon(
        destination.icon,
        size: UiIconSize.action,
        current: current,
        color: current ? style.currentContent : style.restContent,
      ),
    );
  }
}
