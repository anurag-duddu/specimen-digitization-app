/// The frosted pane (09 section 3.3; 10 section 3, `GlassSurface`).
///
/// Glass is a container, not a texture: one pane the reviewer reads as one
/// thing. The recipe is a clip around a blur, then the fill, then the top edge
/// highlight, then the stroke, then the shadow at the floating and modal
/// levels.
///
/// A pane costs a save layer, so the budget in 09 section 3.3 is a design
/// rule the `glass_budget` gate enforces: at most four panes per window, at
/// most one modal, and never inside a scrolling list.
library;

import 'dart:ui' as ui show ImageFilter;

import 'package:flutter/widgets.dart';

import '../foundation/glass.dart';
import '../foundation/theme.dart';
import 'squircle.dart';

/// A frosted pane at one glass level.
class GlassSurface extends StatelessWidget {
  /// Frosts what is behind [child] at [level].
  const GlassSurface({
    super.key,
    required this.child,
    this.level = GlassLevel.flat,
    this.radius,
    this.capsule = false,
    this.padding,
    this.allowInList = false,
  });

  /// What the pane contains.
  final Widget child;

  /// Which level of 09 section 3.3 to paint.
  final GlassLevel level;

  /// The corner radius. Defaults to `radius.tile`.
  final double? radius;

  /// True to draw the pane as a capsule, which is what the navigation is.
  final bool capsule;

  /// Padding inside the pane.
  final EdgeInsetsGeometry? padding;

  /// Suppresses the debug assertion that this pane is not inside a scrolling
  /// list.
  ///
  /// The rule it guards is real: a blurred pane per row multiplies save layers
  /// by the row count and is the single most expensive mistake this system can
  /// make. The escape hatch exists because the check cannot distinguish a
  /// pane that scrolls as one object, such as a sheet whose whole body is one
  /// scroll view under one pane, from a pane repeated per row. Set it only for
  /// the first case, and say why at the call site.
  final bool allowInList;

  @override
  Widget build(BuildContext context) {
    assert(_assertNotRepeatedInList(context), '');
    final UiThemeData theme = context.ui;
    final UiGlassStyle style = theme.glass[level];
    final double corner = radius ?? theme.shape.tile;
    final double sigma = style.sigmaFor(theme.quality);
    final BorderSide side = BorderSide(
      color: style.stroke,
      width: theme.shape.stroke.hairline,
    );
    final ShapeBorder shape = capsule
        ? StadiumBorder(side: side)
        : Squircle.border(corner, side: side);

    Widget content = child;
    if (padding != null) content = Padding(padding: padding!, child: content);

    Widget pane = Stack(
      fit: StackFit.passthrough,
      children: <Widget>[
        // The fill over the blur. The highlight is drawn above the fill and
        // below the content, so content never sits on a bright line.
        Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(color: style.fillFor(theme.quality)),
            ),
          ),
        ),
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          child: IgnorePointer(
            child: _TopHighlight(
              color: style.highlight,
              thickness: theme.shape.stroke.hairline,
            ),
          ),
        ),
        content,
      ],
    );

    if (sigma > 0) {
      pane = BackdropFilter(
        filter: ui.ImageFilter.blur(
          sigmaX: sigma,
          sigmaY: sigma,
          // Mirror rather than clamp: a clamped edge smears the outermost
          // pixel of what is behind the pane along the pane's edge, which
          // reads as a stripe wherever a field meets the pane.
          tileMode: TileMode.mirror,
        ),
        child: pane,
      );
    }

    pane = capsule
        ? ClipPath(clipper: ShapeBorderClipper(shape: shape), child: pane)
        : Squircle.clip(radius: corner, child: pane);

    return DecoratedBox(
      decoration: ShapeDecoration(
        shape: shape,
        shadows: style.shadow == null
            ? null
            : <BoxShadow>[style.shadow!],
      ),
      child: pane,
    );
  }

  /// True unless this pane is a scrolling list's repeated item.
  ///
  /// Checked in debug builds only. `Scrollable.maybeOf` finds a viewport
  /// ancestor, which a sheet's own body also has, so the check is narrowed to
  /// a pane that sits inside a sliver list's item: those are the repeated
  /// ones.
  bool _assertNotRepeatedInList(BuildContext context) {
    if (allowInList) return true;
    bool repeated = false;
    context.visitAncestorElements((Element element) {
      final Widget widget = element.widget;
      if (widget is SliverMultiBoxAdaptorWidget) {
        repeated = true;
        return false;
      }
      // Stop at the viewport: anything above it is the page, not the list.
      if (widget is Viewport || widget is ShrinkWrappingViewport) return false;
      return true;
    });
    assert(
      !repeated,
      'GlassSurface is inside a scrolling list item. 09 section 3.3 forbids '
      'glass on repeated items: the list container may be glass, its rows are '
      'paper or transparent. Use Surface, or set allowInList and say why.',
    );
    return true;
  }
}

/// The 1 dp inner line along the top edge, as a vertical gradient so it fades
/// before the corners.
class _TopHighlight extends StatelessWidget {
  const _TopHighlight({required this.color, required this.thickness});

  final Color color;
  final double thickness;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: thickness,
    child: DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
          colors: <Color>[
            color.withValues(alpha: 0),
            color,
            color,
            color.withValues(alpha: 0),
          ],
          stops: const <double>[0, 0.12, 0.88, 1],
        ),
      ),
    ),
  );
}
