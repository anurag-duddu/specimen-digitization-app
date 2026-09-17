/// The collapsing header (13 section 3.1, `UiCollapsingHeader`).
library;

import 'dart:math' as math;
import 'dart:ui' show lerpDouble;

import 'package:flutter/foundation.dart' show listEquals;
import 'package:flutter/widgets.dart';

import '../../foundation/density.dart';
import '../../foundation/glass.dart';
import '../../foundation/theme.dart';
import '../../foundation/type.dart';
import '../../primitives/composition_markers.dart';
import '../../primitives/glass_surface.dart';

/// The resolved measurements of one collapsing header (10 section 1.5).
@immutable
class UiCollapsingHeaderStyle {
  /// Binds every token the header lays out with.
  const UiCollapsingHeaderStyle({
    required this.chromeRowHeight,
    required this.chromePadding,
    required this.chromeGap,
    required this.radius,
  });

  /// The height of one row of the chrome band.
  ///
  /// Derived from the type it holds rather than declared, so a capsule of
  /// controls at 200 percent text grows the band instead of being clipped by
  /// it (11 section 2.2).
  final double chromeRowHeight;

  /// The padding around the chrome band.
  final EdgeInsetsGeometry chromePadding;

  /// The gap between two chrome rows.
  final double chromeGap;

  /// The corner radius of the pane behind the collapsed chrome.
  ///
  /// `radius.none`: the band spans the header edge to edge, and a corner on
  /// a full width band is a corner against the window's own edge.
  final double radius;

  /// The style for [ui] at the text scale [context] is painted at.
  static UiCollapsingHeaderStyle resolve(UiThemeData ui, BuildContext context) {
    final UiDensity density = Density.of(context);
    return UiCollapsingHeaderStyle(
      chromeRowHeight: math.max(
        UiDensity.hitBox,
        UiType.controlHeightFor(density, ui.type.label, context),
      ),
      chromePadding: EdgeInsetsDirectional.symmetric(
        horizontal: ui.space.s4,
        vertical: ui.space.s2,
      ),
      chromeGap: ui.space.s2,
      radius: ui.shape.none,
    );
  }
}

/// The thing under review, pinned at the top of the one scroll.
///
/// A `SliverPersistentHeader` between [maxFraction] and [minFraction] of the
/// viewport height: the record screen's photograph at 0.55 and 0.40
/// (07 section 6.1). [content] is the thing itself and [chrome] is the rows of
/// controls that ride its lower edge. As the reviewer scrolls, the header
/// collapses toward its minimum and the chrome band shrinks to its last row,
/// which stays welded to the lower edge while the rows above it clip and fade
/// away.
///
/// It is pinned and it never floats: a header that flew back in on an upward
/// scroll would put the evidence somewhere different depending on which way
/// the reviewer last moved. `glass.flat` paints behind the chrome only once
/// the header is collapsed, and it appears at the threshold rather than
/// fading in (09 section 11).
///
/// **Amends 13 section 3.1.** That section gives this pane the compact
/// window's one frosted surface. A record screen has an action bar as well,
/// and 13 section 2.2 allows compact exactly one pane, so the two clauses
/// cannot both hold: `UiScaffold` spends the pane on the chrome it floats and
/// turns the blur off elsewhere inside itself, and this band is then the
/// solid form of the same surface at compact and frosted from medium up. The
/// band is drawn either way; what the class of window decides is whether it
/// costs a save layer.
///
/// Under reduced motion the collapse still tracks the scroll. It is a
/// position and not a transition: the reviewer's finger is what moves it, and
/// freezing it would leave the header at whichever extent the scroll started
/// at (04 section 1.5).
///
/// ```dart
/// CustomScrollView(
///   slivers: <Widget>[
///     UiCollapsingHeader(
///       primary: true,
///       content: photograph,
///       chrome: <Widget>[viewControls, regionToggles],
///     ),
///     SliverToBoxAdapter(child: statusStrip),
///   ],
/// )
/// ```
class UiCollapsingHeader extends StatelessWidget {
  /// A header showing [content], pinned between [minFraction] and
  /// [maxFraction] of the viewport.
  const UiCollapsingHeader({
    super.key,
    required this.content,
    this.chrome = const <Widget>[],
    this.maxFraction = defaultMaxFraction,
    this.minFraction = defaultMinFraction,
    this.primary = false,
    this.style,
  }) : assert(
         minFraction > 0 && minFraction <= maxFraction && maxFraction <= 1,
         'the fractions are of the viewport height, and the minimum is the '
         'floor of the maximum',
       );

  /// The thing under review. The photograph on the record screen.
  final Widget content;

  /// The rows of controls riding the header's lower edge, top to bottom.
  ///
  /// The last row rides the edge and survives the collapse; the rows above it
  /// are what the header gives back as it shrinks to one row at the minimum.
  /// Most headers pass one row, and a header that passes none is [content]
  /// alone.
  final List<Widget> chrome;

  /// The fraction of the viewport the header takes at rest.
  final double maxFraction;

  /// The fraction of the viewport the header holds once collapsed.
  final double minFraction;

  /// True when this header is the screen's primary region (13 section 2.5).
  ///
  /// It then marks itself with [PrimaryRegion] at the extent it pins, which
  /// is the number the `above_the_fold` gate measures. The screen does not
  /// have to restate a height only the header can compute.
  final bool primary;

  /// Overrides the resolved style. A code review event (10 section 1.5).
  final UiCollapsingHeaderStyle? style;

  /// The fraction of the viewport the record screen's source header takes at
  /// rest (07 section 6.1).
  static const double defaultMaxFraction = 0.55;

  /// The fraction it holds once collapsed.
  static const double defaultMinFraction = 0.40;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiCollapsingHeaderStyle paint =
        style ?? UiCollapsingHeaderStyle.resolve(ui, context);
    final double viewport = MediaQuery.sizeOf(context).height;
    final double vertical = paint.chromePadding
        .resolve(Directionality.of(context))
        .vertical;

    final int rows = chrome.length;
    final double minChrome = rows == 0 ? 0 : paint.chromeRowHeight + vertical;
    final double maxChrome = rows == 0
        ? 0
        : paint.chromeRowHeight * rows +
              paint.chromeGap * (rows - 1) +
              vertical;

    // The band a header holds is never smaller than the row it must still
    // show. Everything else is a fraction of the window; this is the floor
    // under the fraction, and it is what makes the promise "no overflow at
    // any text scale" true on a short window at 200 percent text.
    final double minExtent = math.max(minFraction * viewport, minChrome);
    final double maxExtent = math.max(
      maxFraction * viewport,
      math.max(minExtent, maxChrome),
    );

    Widget header = SliverPersistentHeader(
      pinned: true,
      delegate: _CollapsingHeaderDelegate(
        content: content,
        chrome: chrome,
        style: paint,
        minExtent: minExtent,
        maxExtent: maxExtent,
        minChrome: minChrome,
        maxChrome: maxChrome,
      ),
    );
    header = PinnedChrome(
      region: UiPinnedRegion.header,
      extent: minExtent,
      child: header,
    );
    if (!primary) return header;
    return PrimaryRegion(minExtent: minExtent, child: header);
  }
}

class _CollapsingHeaderDelegate extends SliverPersistentHeaderDelegate {
  const _CollapsingHeaderDelegate({
    required this.content,
    required this.chrome,
    required this.style,
    required this.minExtent,
    required this.maxExtent,
    required this.minChrome,
    required this.maxChrome,
  });

  final Widget content;
  final List<Widget> chrome;
  final UiCollapsingHeaderStyle style;
  final double minChrome;
  final double maxChrome;

  @override
  final double minExtent;

  @override
  final double maxExtent;

  /// How far the header has collapsed, from 0 at rest to 1 at the minimum.
  ///
  /// The framework reports a shrink offset up to [maxExtent] rather than up
  /// to the range the header actually travels, so the ratio is clamped and
  /// the threshold is read off the range.
  double _progress(double shrinkOffset) {
    final double range = maxExtent - minExtent;
    if (range <= 0) return 1;
    return (shrinkOffset / range).clamp(0, 1);
  }

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    final double progress = _progress(shrinkOffset);
    final bool collapsed = progress >= 1;
    final double band = chrome.isEmpty
        ? 0
        : lerpDouble(maxChrome, minChrome, progress)!;

    return Column(
      // Stretched, because the thing under review is the width of the window:
      // a `Column` centres its children by default, and a photograph on its
      // matte then sits as wide as whatever it happens to contain.
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        // The thing under review takes whatever the band leaves, and is
        // clipped rather than allowed to paint over the evidence below it.
        Expanded(child: ClipRect(child: content)),
        if (chrome.isNotEmpty)
          SizedBox(
            height: band,
            child: _ChromeBand(
              rows: chrome,
              style: style,
              progress: progress,
              collapsed: collapsed,
              naturalHeight: maxChrome,
            ),
          ),
      ],
    );
  }

  @override
  bool shouldRebuild(_CollapsingHeaderDelegate old) =>
      old.content != content ||
      !listEquals(old.chrome, chrome) ||
      old.style != style ||
      old.minExtent != minExtent ||
      old.maxExtent != maxExtent ||
      old.minChrome != minChrome ||
      old.maxChrome != maxChrome;
}

/// The rows riding the header's lower edge.
///
/// The band is laid out at its natural height and aligned to the bottom of
/// whatever height it has been given, so the last row never moves while the
/// rows above it are taken away. They fade as they go, which is a paint
/// property of a scroll position rather than a transition, so reduced motion
/// has nothing to object to and the band still shrinks under the reviewer's
/// finger.
class _ChromeBand extends StatelessWidget {
  const _ChromeBand({
    required this.rows,
    required this.style,
    required this.progress,
    required this.collapsed,
    required this.naturalHeight,
  });

  final List<Widget> rows;
  final UiCollapsingHeaderStyle style;
  final double progress;
  final bool collapsed;
  final double naturalHeight;

  @override
  Widget build(BuildContext context) {
    final int last = rows.length - 1;
    final Widget column = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        for (int i = 0; i < rows.length; i++) ...<Widget>[
          if (i != 0) SizedBox(height: style.chromeGap),
          SizedBox(
            height: style.chromeRowHeight,
            child: i == last
                ? rows[i]
                : Opacity(opacity: 1 - progress, child: rows[i]),
          ),
        ],
      ],
    );

    final Widget band = ClipRect(
      child: OverflowBox(
        alignment: AlignmentDirectional.bottomStart,
        minHeight: 0,
        maxHeight: naturalHeight,
        child: Padding(padding: style.chromePadding, child: column),
      ),
    );

    // The one frosted pane a compact window may spend, and only once the
    // header has stopped moving. It appears at the threshold rather than
    // fading in: 09 section 11 rejects glass that animates its opacity.
    if (!collapsed) return band;
    return GlassSurface(
      level: GlassLevel.flat,
      radius: style.radius,
      child: band,
    );
  }
}
