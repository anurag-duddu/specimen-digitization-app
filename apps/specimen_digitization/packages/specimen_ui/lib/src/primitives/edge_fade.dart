/// A row too wide for its column, scrolled with fading edges
/// (11 section 3.3, the compact variant of a tab strip and a navigation row).
///
/// The row inside keeps its intrinsic width: 11 section 3.3 rule 2 is that a
/// control never shrinks itself, and a navigation disc's hit box is 48 dp at
/// every density and every text scale. What gives is the column, which
/// scrolls, and the fade is what says so.
library;

import 'package:flutter/widgets.dart';

import '../foundation/motion.dart';
import '../foundation/theme.dart';

/// Scrolls [child] horizontally, fading the edge there is more beyond.
///
/// The fade is drawn only on a side there is something to scroll to, so an
/// edge that is the end of the row stays crisp and a faded edge always means
/// "there is more this way". It is a mask over the row rather than a gradient
/// painted on top of it, because the row is drawn over the sky and a solid
/// gradient would have to know which surface it is covering.
///
/// [index] of [length] is the item to keep in view. The offset is the
/// reviewer's position along the row rather than the item's own box: the
/// boxes belong to the control inside, and a scroller that reached in to
/// measure one would be a second copy of that control's layout. With the two
/// to five items a strip or a pill carries, the first lands at the start, the
/// last at the end, and the ones between are in the middle.
class EdgeFadedRow extends StatefulWidget {
  /// Scrolls [child], keeping item [index] of [length] in view.
  const EdgeFadedRow({
    super.key,
    required this.child,
    required this.index,
    required this.length,
    required this.fadeExtent,
  });

  /// The row, at its own intrinsic width.
  final Widget child;

  /// The item to bring into view when it changes.
  final int index;

  /// How many items the row holds.
  final int length;

  /// How wide the fade is at each edge, in logical pixels. A token from the
  /// control, because a primitive makes no styling decisions of its own.
  final double fadeExtent;

  @override
  State<EdgeFadedRow> createState() => _EdgeFadedRowState();
}

class _EdgeFadedRowState extends State<EdgeFadedRow> {
  final ScrollController _controller = ScrollController();

  @override
  void initState() {
    super.initState();
    _controller.addListener(_edgesChanged);
  }

  @override
  void didUpdateWidget(EdgeFadedRow old) {
    super.didUpdateWidget(old);
    if (old.index != widget.index) _reveal();
  }

  @override
  void dispose() {
    _controller
      ..removeListener(_edgesChanged)
      ..dispose();
    super.dispose();
  }

  void _edgesChanged() {
    if (mounted) setState(() {});
  }

  /// Brings the chosen item into view, after the frame it was chosen in.
  ///
  /// After rather than during: a listener runs before the rebuild it caused,
  /// and the extent has to be read from a viewport that has been laid out.
  void _reveal() {
    WidgetsBinding.instance.addPostFrameCallback((Duration _) => _scroll());
  }

  void _scroll() {
    if (!mounted || !_controller.hasClients || widget.length < 2) return;
    final ScrollPosition position = _controller.position;
    final double target =
        position.maxScrollExtent *
        (widget.index.clamp(0, widget.length - 1) / (widget.length - 1));
    final MotionTokens motion = context.ui.motion;
    if (motion.reduced) {
      _controller.jumpTo(target);
      return;
    }
    _controller.animateTo(
      target,
      duration: motion.medium,
      curve: MotionTokens.standardCurve,
    );
  }

  bool get _fadeStart =>
      _controller.hasClients && _controller.position.extentBefore > 0;

  bool get _fadeEnd =>
      _controller.hasClients && _controller.position.extentAfter > 0;

  @override
  Widget build(BuildContext context) {
    final TextDirection direction = Directionality.of(context);
    // The mask is always in the tree, opaque at both ends when there is
    // nothing to fade. Adding and removing it instead would change the
    // scroller's position in the tree, which re-inflates the `Scrollable`,
    // which throws away its `ScrollPosition` and with it the animation that
    // was bringing the chosen item into view.
    return ShaderMask(
      blendMode: BlendMode.dstIn,
      shaderCallback: (Rect bounds) {
        final double fade = bounds.width == 0
            ? 0
            : (widget.fadeExtent / bounds.width).clamp(0, 0.5);
        return LinearGradient(
          begin: AlignmentDirectional.centerStart,
          end: AlignmentDirectional.centerEnd,
          stops: <double>[0, fade, 1 - fade, 1],
          colors: <Color>[
            Color.fromRGBO(0, 0, 0, _fadeStart ? 0 : 1),
            const Color.fromRGBO(0, 0, 0, 1),
            const Color.fromRGBO(0, 0, 0, 1),
            Color.fromRGBO(0, 0, 0, _fadeEnd ? 0 : 1),
          ],
        ).createShader(bounds, textDirection: direction);
      },
      child: SingleChildScrollView(
        controller: _controller,
        scrollDirection: Axis.horizontal,
        child: widget.child,
      ),
    );
  }
}
