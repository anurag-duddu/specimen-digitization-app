/// The markers the composition gates read (13 section 5).
///
/// A screen's composition is measured rather than reviewed: the chrome budget
/// is a sum of pinned heights over the viewport height, and the fold rule is
/// the primary region's rectangle inside the first viewport. Neither is
/// readable from a widget tree on its own, because "pinned" and "primary" are
/// facts about the arrangement and not about any one widget's type. These two
/// markers are where a screen states them.
///
/// Both are zero cost. Each builds its child and nothing else, so it adds one
/// element and no render object, and `element.findRenderObject()` returns the
/// child's. A gate finds a marker by type and reads either the box under it or
/// the extent it declares.
library;

import 'package:flutter/widgets.dart';

/// Which job a piece of pinned chrome does (13 section 2.4).
///
/// Named rather than free text so the budget's failure can say which region
/// spent the height, and so `one_job` can hold two regions to different rules.
/// `UiScaffold` marks the four it owns; a header inside the body marks itself.
enum UiPinnedRegion {
  /// The bar across the top: the screen's name and the way out.
  topBar,

  /// The environment band under the top bar.
  band,

  /// A collapsing header pinned at the top of the body, at its minimum
  /// extent. The thing under review.
  header,

  /// The sticky actions above the navigation. The decision bar.
  actionBar,

  /// The floating navigation pill.
  ///
  /// A rail and a sidebar are columns beside the body rather than chrome over
  /// it, so they take no height from the viewport and are not marked.
  navigation,
}

/// Marks a region that is pinned, and how much height it takes.
///
/// The `chrome_budget` gate sums [extentOf] over every marker on the screen
/// and divides by the viewport height: at most 28 percent at compact, 24 at
/// medium and 20 from expanded up (13 section 2.3). The `one_job` gate reads
/// the text under each marker and fails on two pinned regions that say the
/// same words.
///
/// ```dart
/// PinnedChrome(
///   region: UiPinnedRegion.band,
///   child: UiBanner.strip(message: 'Synthetic data', onTap: explain),
/// )
/// ```
///
/// Most screens mark nothing: `UiScaffold` marks its own top bar, banner,
/// action bar and floating navigation, which is four of the five regions a
/// screen pins. The fifth is a collapsing header, which pins part of itself
/// and marks itself with the part it pins.
class PinnedChrome extends StatelessWidget {
  /// Marks [child] as the pinned chrome of [region].
  ///
  /// [extent] is the height the region actually pins, for a region whose own
  /// box is not the answer: a sliver has no box at all, and a collapsing
  /// header's box is its current extent rather than the minimum it holds the
  /// viewport to.
  const PinnedChrome({
    super.key,
    required this.region,
    required this.child,
    this.extent,
  });

  /// Which job this chrome does.
  final UiPinnedRegion region;

  /// The marked region.
  final Widget child;

  /// The height this region pins, or null to measure the box under it.
  final double? extent;

  /// The height the marker at [element] contributes to the chrome budget.
  ///
  /// The declared [extent] where there is one, and the height of the render
  /// box under the marker otherwise. One rule, published here, so that the
  /// gate and a control's own test never disagree about what a region cost.
  ///
  /// Throws when a marker declares no extent and has no box, which is a
  /// sliver that forgot to say what it pins.
  static double extentOf(Element element) {
    final PinnedChrome marker = element.widget as PinnedChrome;
    final double? declared = marker.extent;
    if (declared != null) return declared;
    final RenderObject? object = element.findRenderObject();
    if (object is RenderBox && object.hasSize) return object.size.height;
    throw FlutterError(
      'PinnedChrome(region: ${marker.region.name}) has no box to measure, so '
      'it has to declare the height it pins. Pass extent: to the marker.',
    );
  }

  @override
  Widget build(BuildContext context) => child;
}

/// Marks the one region a screen exists to show (13 section 2.5).
///
/// The photograph on the record screen, the list on the queue, the form on
/// intake, the sources list on sources. The `above_the_fold` gate asserts
/// that this region is laid out inside the first viewport at [minExtent],
/// with room left for the first row of whatever follows it, so the work is
/// never below the fold on a phone.
///
/// One per screen. A screen with two is a screen that has not decided.
class PrimaryRegion extends StatelessWidget {
  /// Marks [child] as this screen's primary region.
  ///
  /// [minExtent] is the least height the region is worth showing in, for a
  /// region that can give height back under pressure: a collapsing header
  /// passes the height it pins at, and a list leaves it null because the rows
  /// it shows are whatever fits.
  const PrimaryRegion({super.key, required this.child, this.minExtent});

  /// The marked region.
  final Widget child;

  /// The least height the region is worth showing in, or null for whatever
  /// the region was given.
  final double? minExtent;

  /// The height the region at [element] has to be shown in.
  ///
  /// The declared [minExtent] where there is one, and the height of the box
  /// under the marker otherwise.
  static double minExtentOf(Element element) {
    final PrimaryRegion marker = element.widget as PrimaryRegion;
    final double? declared = marker.minExtent;
    if (declared != null) return declared;
    final RenderObject? object = element.findRenderObject();
    if (object is RenderBox && object.hasSize) return object.size.height;
    throw FlutterError(
      'PrimaryRegion has no box to measure, so it has to declare the height '
      'it is worth showing in. Pass minExtent: to the marker.',
    );
  }

  @override
  Widget build(BuildContext context) => child;
}
