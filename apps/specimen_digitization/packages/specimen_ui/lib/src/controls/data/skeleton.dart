/// Loading placeholders (10 section 4.5, `UiSkeleton`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/motion.dart';
import '../../foundation/theme.dart';
import '../actions/button.dart' show UiSize;
import 'data_tile.dart';
import 'list_row.dart';

/// Which shape a placeholder stands in for.
enum _SkeletonForm { line, row, tile }

/// The resolved paint of one placeholder.
@immutable
class UiSkeletonStyle {
  /// Binds every token a placeholder draws with.
  const UiSkeletonStyle({
    required this.block,
    required this.radius,
    required this.lineHeight,
    required this.cycle,
  });

  /// The block's fill at rest.
  final Color block;

  /// The block's corner radius.
  final double radius;

  /// The height of one line of stand-in text.
  final double lineHeight;

  /// One full pulse, out and back.
  final Duration cycle;

  /// The style in [ui].
  static UiSkeletonStyle resolve(UiThemeData ui) => UiSkeletonStyle(
    block: ui.color.stateLayer(restOpacityOf(ui)),
    radius: ui.shape.inner,
    // A `body` line with its leading, so a stand-in line occupies the height
    // the text it replaces will.
    lineHeight: ui.space.iconInline,
    cycle: pulseCycle,
  );

  /// One full pulse, out and back.
  ///
  /// Slow, and composed from the longest duration token rather than written
  /// as a literal. 04 section 2.2 has no token for a repeating cycle because
  /// nothing else in the catalog repeats.
  static final Duration pulseCycle = MotionTokens.slowRaw * 3;

  /// What a block is filled with at rest, in [ui].
  ///
  /// 10 section 4.5 says `paper` at 60 percent. `paper` on `paper` is
  /// nothing at all, and a loading list sits on exactly that surface: the
  /// list body is `paper` and its rows are `paper` or transparent
  /// (09 section 3.3). Over `ground` in light, `paper` at 60 percent
  /// measures 1.02 to 1, which is a placeholder nobody can see.
  ///
  /// The block is therefore the state layer, at the 8 percent the system
  /// already carries for `ink` over a surface. It moves the surface toward
  /// its opposite in both modes, which is the same correction wave 0 made to
  /// that layer for the same reason, and it is visible on `paper`, on
  /// `ground` and under a field.
  static double restOpacityOf(UiThemeData ui) => ui.color.hoverOpacity;

  /// The floor of the pulse, as a fraction of the resting alpha.
  ///
  /// The block dims without leaving the layout it is holding open.
  static const double pulseFloorFraction = 0.5;
}

/// A tonal block in the shape of the content it stands for.
///
/// Carried from the v1 `Skeleton`. No shimmer: a sweep is a repeating
/// animation, Flutter does not shorten repeating animations under
/// `disableAnimations` (04 section 2.5), and the only safe sweep is no sweep.
/// What is left is a slow opacity pulse, and that stops under reduced motion.
///
/// Placeholders are outside the semantics tree. Pair any number of them with
/// exactly one live "Loading" node, so a screen reader hears the wait once
/// rather than hearing nothing at all from a screen of hidden boxes
/// (06 section 3.1).
class UiSkeleton extends StatefulWidget {
  /// One line of stand-in text, [widthFactor] of the width it is given.
  const UiSkeleton.line({super.key, this.widthFactor = 1, this.height})
    : _form = _SkeletonForm.line;

  /// A `UiListRow`: the leading slot, a title line and a subtitle line, at
  /// the row's own height.
  const UiSkeleton.row({super.key})
    : _form = _SkeletonForm.row,
      widthFactor = 1,
      height = null;

  /// A `UiDataTile`: one block at `radius.tile`, the height a tile with a
  /// label and a numeral occupies.
  const UiSkeleton.tile({super.key})
    : _form = _SkeletonForm.tile,
      widthFactor = 1,
      height = null;

  final _SkeletonForm _form;

  /// The fraction of the available width one line covers, 0 to 1.
  final double widthFactor;

  /// The line's height. Defaults to one `body` line with its leading.
  final double? height;

  @override
  State<UiSkeleton> createState() => _UiSkeletonState();
}

class _UiSkeletonState extends State<UiSkeleton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse = AnimationController(
    vsync: this,
    // `preserve`: a repeating controller is the one case Flutter does not
    // compress under `disableAnimations`. [didChangeDependencies] applies the
    // policy by hand instead, by stopping the pulse outright.
    animationBehavior: AnimationBehavior.preserve,
    duration: UiSkeletonStyle.pulseCycle,
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (context.ui.motion.reduced) {
      if (_pulse.isAnimating) _pulse.stop();
      _pulse.value = 0;
    } else if (!_pulse.isAnimating) {
      // Out and back on one controller, so the block fades rather than
      // snapping at the loop point.
      _pulse.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiSkeletonStyle style = UiSkeletonStyle.resolve(ui);
    return ExcludeSemantics(
      child: AnimatedBuilder(
        animation: _pulse,
        builder: (BuildContext context, Widget? child) {
          final double rest = UiSkeletonStyle.restOpacityOf(ui);
          final double floor = rest * UiSkeletonStyle.pulseFloorFraction;
          final Color block = ui.color.stateLayer(
            rest + (floor - rest) * _pulse.value,
          );
          return switch (widget._form) {
            _SkeletonForm.line => _line(style, block, widget.widthFactor),
            _SkeletonForm.row => _row(ui, style, block),
            _SkeletonForm.tile => _tile(ui, style, block),
          };
        },
      ),
    );
  }

  /// One bar, as wide as [widthFactor] of the space it is given.
  ///
  /// It takes the child's width rather than the parent's, so a column of
  /// lines of different lengths shares its start edge without an alignment
  /// at every call site.
  Widget _line(UiSkeletonStyle style, Color block, double widthFactor) =>
      FractionallySizedBox(
        alignment: AlignmentDirectional.centerStart,
        widthFactor: widthFactor,
        child: _block(
          style,
          block,
          height: widget.height ?? style.lineHeight,
          radius: style.radius,
        ),
      );

  /// The row's anatomy: the leading slot, then a title and a subtitle line.
  Widget _row(UiThemeData ui, UiSkeletonStyle style, Color block) => SizedBox(
    height: UiListRowStyle.heightOf(ui),
    child: Padding(
      padding: UiListRowStyle.resolve(ui, UiSize.md).padding,
      child: Row(
        children: <Widget>[
          _block(
            style,
            block,
            height: UiListRowStyle.leadingExtent,
            width: UiListRowStyle.leadingExtent,
            radius: style.radius,
          ),
          SizedBox(width: ui.space.s3),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                _line(style, block, _titleWidthFactor),
                SizedBox(height: ui.space.s1),
                _line(style, block, _subtitleWidthFactor),
              ],
            ),
          ),
        ],
      ),
    ),
  );

  /// The tile's footprint, at the tile's own radius.
  Widget _tile(UiThemeData ui, UiSkeletonStyle style, Color block) => _block(
    style,
    block,
    height: UiDataTileStyle.labelAndNumeralHeight(ui),
    radius: ui.shape.tile,
  );

  Widget _block(
    UiSkeletonStyle style,
    Color block, {
    required double height,
    required double radius,
    double? width,
  }) => SizedBox(
    height: height,
    width: width,
    child: DecoratedBox(
      decoration: ShapeDecoration(
        shape: RoundedSuperellipseBorder(
          borderRadius: BorderRadius.circular(radius),
        ),
        color: block,
      ),
    ),
  );

  /// A title line is longer than the subtitle under it, which is what the
  /// two lines of a row look like before they arrive.
  static const double _titleWidthFactor = 0.55;

  /// The subtitle line.
  static const double _subtitleWidthFactor = 0.35;
}
