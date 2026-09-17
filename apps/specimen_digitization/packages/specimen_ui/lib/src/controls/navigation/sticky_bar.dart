/// The bar that scrolls up to the header and then stays (13 section 3.5).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../primitives/composition_markers.dart';

/// A pinned sliver of one fixed [extent] for the region that scrolls with the
/// page until it meets the header and then sticks under it: the record's
/// segments, the queue's search and filter row.
///
/// A sticky bar is chrome only while it is stuck (13 section 3.5). In the
/// flow of the page it paints nothing and lets the sky through; once it is
/// pinned, scrolled past the top of the viewport or held under a pinned header
/// above it, it draws `ground` behind its child so what scrolls beneath does
/// not show through, which is also the solid surface the scaffold's compact
/// pane policy asks of every region but the one it floats (13 section 2.2).
/// The fill appears at the threshold and does not fade in, the way a
/// collapsing header takes its chrome fill (09 section 11). Polish 3: the
/// queue's search row, stuck at medium, drew a band of ground across the home
/// sky while it was still in the flow.
///
/// It carries the `header` marker so the chrome budget counts it while it is
/// stuck, and the extent is the child's own height, which the caller derives
/// from type (`UiType.controlHeightFor` plus its padding), never a constant.
class UiStickyBar extends StatelessWidget {
  /// Pins [child] at [extent] once the page has scrolled it to the header.
  const UiStickyBar({super.key, required this.extent, required this.child});

  /// The bar's height, derived from the type it holds.
  final double extent;

  /// The row that sticks.
  final Widget child;

  @override
  Widget build(BuildContext context) => PinnedChrome(
    region: UiPinnedRegion.header,
    extent: extent,
    child: SliverPersistentHeader(
      pinned: true,
      delegate: _StickyBarDelegate(
        extent: extent,
        ground: context.ui.color.ground,
        child: child,
      ),
    ),
  );
}

class _StickyBarDelegate extends SliverPersistentHeaderDelegate {
  const _StickyBarDelegate({
    required this.extent,
    required this.ground,
    required this.child,
  });

  final double extent;
  final Color ground;
  final Widget child;

  @override
  double get minExtent => extent;

  @override
  double get maxExtent => extent;

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    // Stuck at the top of the viewport once anything has scrolled past it,
    // and stuck under a pinned header above it once that header's paint
    // overlaps this sliver, which is the moment the bar's top meets the
    // header's lower edge.
    final bool stuck = shrinkOffset > 0 || overlapsContent;
    // One decoration whatever the state, with no colour while the bar is in
    // the flow: a fill that came and went as a widget would rebuild the row
    // inside it at the threshold, and a search field loses its text that way.
    return SizedBox(
      height: extent,
      child: DecoratedBox(
        decoration: BoxDecoration(color: stuck ? ground : null),
        child: child,
      ),
    );
  }

  @override
  bool shouldRebuild(_StickyBarDelegate oldDelegate) =>
      oldDelegate.extent != extent ||
      oldDelegate.ground != ground ||
      oldDelegate.child != child;
}
