/// A label region drawn over the specimen photograph
/// (09 sections 3.4 and 3.6; 07 section 6.2; 06 sections 3.1 and 3.2).
///
/// The stroke is drawn with a casing on the outside, because a line over an
/// arbitrary photograph has to survive whatever pixel is behind it. The hit
/// box is independent of the drawn box, so a region three pixels tall is
/// still reachable by a finger and by a switch. The name the overlay speaks
/// is the same "Label N" the region list shows, never the raw region id.
library;

import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

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
  /// the reviewer is trying to read (04 catalog row 38 and section 6.4).
  final double viewerScale;

  /// The name shown on the tab and spoken by the overlay. Computed once, and
  /// shared with the region list so the two can never disagree.
  String get label => 'Label $index';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // Pair the selected accent with its contrasting ink, independently of the
    // surrounding app brightness. General dark-theme ink is pale and would
    // disappear on both the accent number tab and a pale specimen label.
    // The contrasting casing on both sides keeps the outline legible over
    // pale paper while the accent itself stays visible over dark image pixels.
    final Color stroke = selected
        ? ui.color.accent
        : ui.color.status.regionOverlayStroke;
    final Color casing = selected
        ? ui.color.onAccent
        : ui.color.status.regionOverlayCasing;
    final double minTarget = ui.space.targetMin / viewerScale;
    final double hitWidth = rect.width < minTarget ? minTarget : rect.width;
    final double hitHeight = rect.height < minTarget ? minTarget : rect.height;
    final Offset center = rect.center;
    final numberSize = measureLabel(context, '$index', ui.type.labelSmall);
    final tabWidth = (numberSize.width + 2 * ui.space.s1) / viewerScale;
    final tabHeight = numberSize.height / viewerScale;

    return LayoutBuilder(
      builder: (context, constraints) {
        final double tabLeft = rect.left.clamp(
          0.0,
          math.max(0.0, constraints.maxWidth - tabWidth),
        );
        final double tabTop = (rect.top - tabHeight - ui.space.s1 / viewerScale)
            .clamp(0.0, math.max(0.0, constraints.maxHeight - tabHeight));
        // The number is part of the same label action even when it sits above
        // the region. Include its measured, counter-scaled painted bounds in
        // the existing body target without moving the region or adding a
        // second focus/semantics stop.
        final Rect hitRect = Rect.fromCenter(
          center: center,
          width: hitWidth,
          height: hitHeight,
        ).expandToInclude(Rect.fromLTWH(tabLeft, tabTop, tabWidth, tabHeight));
        return Stack(
          clipBehavior: Clip.none,
          children: <Widget>[
            Positioned.fill(
              child: IgnorePointer(
                child: CustomPaint(
                  painter: RegionBoxPainter(
                    rect: rect,
                    stroke: stroke,
                    casing: casing,
                    strokeWidth:
                        (selected
                            ? ui.shape.stroke.bar
                            : ui.shape.stroke.emphasis) /
                        viewerScale,
                    casingWidth: ui.shape.stroke.hairline / viewerScale,
                  ),
                ),
              ),
            ),
            // Prefer the area above the box. At an image edge, keep the complete
            // number within the photograph without moving its region.
            Positioned(
              left: tabLeft,
              top: tabTop,
              child: IgnorePointer(
                // The tab is type, so it is counter-scaled rather than redrawn:
                // a legible number at 1x is an unreadable slab at 12x.
                child: Transform.scale(
                  scale: 1 / viewerScale,
                  alignment: Alignment.topLeft,
                  child: _NumberTab(
                    index: index,
                    fill: stroke,
                    content: casing,
                  ),
                ),
              ),
            ),
            Positioned.fromRect(
              rect: hitRect,
              child: Pressable(
                semanticsLabel: label,
                selected: selected,
                onPressed: onTap,
                radius: ui.shape.inner,
                builder: (BuildContext context, Set<WidgetState> states) =>
                    const SizedBox.expand(),
              ),
            ),
          ],
        );
      },
    );
  }
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
///
/// The tab inverts the box it belongs to, so the two carry one pair of
/// colours between them and a reader never has to match a tab to a stroke by
/// hue alone.
class _NumberTab extends StatelessWidget {
  const _NumberTab({
    required this.index,
    required this.fill,
    required this.content,
  });

  final int index;
  final Color fill;
  final Color content;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return DecoratedBox(
      decoration: ShapeDecoration(
        color: fill,
        shape: Squircle.border(
          ui.shape.inner,
          side: BorderSide(color: content, width: ui.shape.stroke.hairline),
        ),
      ),
      child: Padding(
        padding: EdgeInsetsDirectional.symmetric(horizontal: ui.space.s1),
        child: UiLabel(
          '$index',
          style: ui.type.labelSmall.copyWith(color: content),
        ),
      ),
    );
  }
}
