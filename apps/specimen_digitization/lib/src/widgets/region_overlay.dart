/// A label region drawn over the specimen photograph
/// (design system, 7.3 `RegionOverlay`; accessibility, 3.1 and 3.2).
///
/// The stroke is drawn with a casing on the outside, because a line over an
/// arbitrary photograph has to survive whatever pixel is behind it. The hit
/// box is independent of the drawn box, so a region three pixels tall is
/// still reachable by a finger and by a switch. The name the overlay speaks
/// is the same "Label N" the region list shows, never the raw region id.
library;

import 'package:flutter/material.dart';

import '../theme/icons.dart';

/// One region box, its number tab, and its hit target.
///
/// Place this so it fills the same box the image fills; [rect] is in this
/// widget's own coordinate space.
class RegionOverlay extends StatelessWidget {
  const RegionOverlay({
    super.key,
    required this.index,
    required this.rect,
    this.selected = false,
    this.onTap,
    this.viewerScale = 1,
  }) : assert(viewerScale > 0, 'a viewer scale is a magnification, never zero');

  /// The region's one based position in the region list.
  final int index;

  /// The region's box, in this widget's coordinate space.
  final Rect rect;

  /// True when this is the region the reviewer is working on.
  final bool selected;

  /// Selects the region.
  final VoidCallback? onTap;

  /// The magnification the enclosing `InteractiveViewer` is currently at.
  ///
  /// The overlay is drawn inside the transformed subtree, so everything it
  /// paints is multiplied by this. Stroke widths, the number tab and the
  /// minimum hit box are therefore divided by it, which is what keeps a 2dp
  /// outline 2dp on the glass at 12x instead of a 24dp band over the label
  /// the reviewer is trying to read (motion and microinteractions, catalog
  /// row 38 and section 6.4).
  final double viewerScale;

  /// The name shown on the tab and spoken by the overlay. Computed once, and
  /// shared with the region list so the two can never disagree.
  String get label => 'Label $index';

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    // 48dp: the app's own minimum target, which is stricter than the 44
    // logical pixels the accessibility document requires for this overlay.
    final double minTarget = context.sizes.targetMin / viewerScale;
    final double hitWidth = rect.width < minTarget ? minTarget : rect.width;
    final double hitHeight = rect.height < minTarget ? minTarget : rect.height;
    final Offset center = rect.center;
    final double tabGap =
        (context.sizes.iconInline + context.space.space1) / viewerScale;

    return Stack(
      clipBehavior: Clip.none,
      children: <Widget>[
        Positioned.fill(
          child: IgnorePointer(
            child: CustomPaint(
              painter: RegionBoxPainter(
                rect: rect,
                stroke: selected
                    ? context.tokens.regionSelectedCore
                    : context.tokens.regionOverlayStroke,
                casing: selected
                    ? context.tokens.regionSelectedCasing
                    : context.tokens.regionOverlayCasing,
                strokeWidth:
                    (selected
                        ? context.shape.strokeStrong
                        : context.shape.strokeEmphasis) /
                    viewerScale,
                casingWidth: context.shape.strokeHairline / viewerScale,
              ),
            ),
          ),
        ),
        // The numbered tab sits outside the box, above its leading corner, so
        // it never covers the pixels the reviewer is reading.
        Positioned(
          left: rect.left,
          top: rect.top - tabGap,
          child: IgnorePointer(
            // The tab is type, so it is counter-scaled rather than redrawn:
            // a legible number at 1x is an unreadable slab at 12x.
            child: Transform.scale(
              scale: 1 / viewerScale,
              alignment: AlignmentDirectional.bottomStart,
              child: _NumberTab(index: index, selected: selected),
            ),
          ),
        ),
        Positioned(
          left: center.dx - hitWidth / 2,
          top: center.dy - hitHeight / 2,
          width: hitWidth,
          height: hitHeight,
          child: MergeSemantics(
            child: Semantics(
              label: label,
              selected: selected,
              child: Material(
                type: MaterialType.transparency,
                child: InkWell(
                  onTap: onTap,
                  // The focus ring has to clear 3:1 against an arbitrary
                  // photograph, so it is the reserved focus token, not the
                  // default Material tint.
                  focusColor: context.tokens.focusRing.withValues(
                    alpha: _focusFillOpacity,
                  ),
                  overlayColor: WidgetStatePropertyAll<Color>(
                    theme.colorScheme.onSurface.withValues(
                      alpha: _pressedOpacity,
                    ),
                  ),
                  child: const SizedBox.expand(),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  static const double _focusFillOpacity = 0.32;
  static const double _pressedOpacity = 0.1;
}

/// Draws one region box: a stroke with a casing on each side of it.
class RegionBoxPainter extends CustomPainter {
  const RegionBoxPainter({
    required this.rect,
    required this.stroke,
    required this.casing,
    required this.strokeWidth,
    required this.casingWidth,
  });

  final Rect rect;
  final Color stroke;
  final Color casing;
  final double strokeWidth;
  final double casingWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final Paint casingPaint = Paint()
      ..style = PaintingStyle.stroke
      ..color = casing
      ..strokeWidth = casingWidth;
    final Paint corePaint = Paint()
      ..style = PaintingStyle.stroke
      ..color = stroke
      ..strokeWidth = strokeWidth;

    final double half = strokeWidth / 2 + casingWidth / 2;
    canvas
      ..drawRect(rect.inflate(half), casingPaint)
      ..drawRect(rect, corePaint)
      ..drawRect(rect.deflate(half), casingPaint);
  }

  @override
  bool shouldRepaint(RegionBoxPainter oldDelegate) =>
      rect != oldDelegate.rect ||
      stroke != oldDelegate.stroke ||
      casing != oldDelegate.casing ||
      strokeWidth != oldDelegate.strokeWidth ||
      casingWidth != oldDelegate.casingWidth;
}

/// The region's number, in a tab that reads over any photograph.
class _NumberTab extends StatelessWidget {
  const _NumberTab({required this.index, required this.selected});

  final int index;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    final Color fill = selected
        ? context.tokens.regionSelectedCore
        : context.tokens.regionOverlayCasing;
    final Color content = selected
        ? context.tokens.regionSelectedCasing
        : context.tokens.regionOverlayStroke;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(context.shape.radiusXs),
        border: Border.all(color: content, width: context.shape.strokeHairline),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: context.space.space1),
        child: Text(
          '$index',
          style: Theme.of(
            context,
          ).textTheme.labelSmall?.copyWith(color: content),
        ),
      ),
    );
  }
}
