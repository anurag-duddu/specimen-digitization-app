/// A label region drawn over the specimen photograph
/// (09 sections 3.4 and 3.6; 07 section 6.2; 06 sections 3.1 and 3.2).
///
/// The stroke is drawn with a casing on the outside, because a line over an
/// arbitrary photograph has to survive whatever pixel is behind it. The hit
/// box is independent of the drawn box, so a region three pixels tall is
/// still reachable by a finger and by a switch. The name the overlay speaks
/// is the same "Label N" the region list shows, never the raw region id.
library;

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
    // The selected region is the one accent on this screen: 09 section 3.4
    // names "the active region marker over the photograph" as an accent use,
    // and the same section's wave 1 amendment gives the accent a 1 dp `ink`
    // casing wherever it is the only thing saying where a value is. The
    // painter already casings both sides of the stroke, which is what carries
    // it over a pale label as well as a dark pin.
    final Color stroke = selected
        ? ui.color.accent
        : ui.color.status.regionOverlayStroke;
    final Color casing = selected
        ? ui.color.ink
        : ui.color.status.regionOverlayCasing;
    final double minTarget = ui.space.targetMin / viewerScale;
    final double hitWidth = rect.width < minTarget ? minTarget : rect.width;
    final double hitHeight = rect.height < minTarget ? minTarget : rect.height;
    final Offset center = rect.center;
    final double tabGap = (ui.space.iconInline + ui.space.s1) / viewerScale;

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
              child: _NumberTab(index: index, fill: stroke, content: casing),
            ),
          ),
        ),
        Positioned(
          left: center.dx - hitWidth / 2,
          top: center.dy - hitHeight / 2,
          width: hitWidth,
          height: hitHeight,
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
