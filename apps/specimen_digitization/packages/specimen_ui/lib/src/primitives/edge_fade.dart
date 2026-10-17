/// A row too wide for its column, scrolled with fading edges
/// (11 section 3.3, the compact variant of a tab strip and a navigation row).
///
/// The row inside keeps its intrinsic width: 11 section 3.3 rule 2 is that a
/// control never shrinks itself, and a navigation disc's hit box is 48 dp at
/// every density and every text scale. What gives is the column, which
/// scrolls, and the fade is what says so.
library;

import 'dart:math' as math;

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
    this.revealInitially = false,
    this.extent,
  }) : assert(
         !revealInitially || extent != null,
         'revealInitially places the row before it is first painted, which '
         'needs the row\'s own width: pass extent',
       );

  /// The row, at its own intrinsic width.
  final Widget child;

  /// The item to bring into view when it changes.
  final int index;

  /// How many items the row holds.
  final int length;

  /// How wide the fade is at each edge, in logical pixels. A token from the
  /// control, because a primitive makes no styling decisions of its own.
  final double fadeExtent;

  /// True to start the row already scrolled to item [index], and not only to
  /// scroll there when [index] changes.
  ///
  /// False by default, which is what a strip or a pill that always opens on
  /// its first item wants, and what leaves `UiTabs` and `UiPillNav` exactly as
  /// they were. A bar that can open on any of its items, such as the tab bar
  /// on a deep link, sets it. The offset is set **before the row is first
  /// laid out and painted**: it is the scroll controller's initial offset,
  /// worked out from [extent] and the width the row is given, so the first
  /// frame already shows where the reviewer is, with nothing to travel from
  /// and no frame at the wrong place first. The row is also put back on
  /// [index] when the width it is given changes, for example on rotation.
  ///
  /// Expected not to change for the life of the widget: it decides whether the
  /// row measures its own width.
  final bool revealInitially;

  /// The row's own width, which [child] has at its intrinsic size.
  ///
  /// Read only when [revealInitially] is set. The row's scroll reach is this
  /// minus the width it is given, and item [index] of [length] sits that
  /// fraction of the way along it (see the class comment), so the caller, who
  /// owns the row, says how wide it is rather than the scroller measuring a
  /// child it cannot see.
  final double? extent;

  @override
  State<EdgeFadedRow> createState() => _EdgeFadedRowState();
}

class _EdgeFadedRowState extends State<EdgeFadedRow> {
  /// Created in [initState] for a row that starts at the beginning, and by the
  /// first build for one that starts on an item, because its initial offset
  /// needs the width the row is given and that is not known until then.
  ScrollController? _controller;

  /// The width the row was last laid out in, for putting it back on its item
  /// when that changes.
  double? _viewport;

  ScrollController _controllerAt(double initialOffset) {
    return _controller ??= ScrollController(initialScrollOffset: initialOffset)
      ..addListener(_edgesChanged);
  }

  @override
  void initState() {
    super.initState();
    if (!widget.revealInitially) _controllerAt(0);
  }

  @override
  void didUpdateWidget(EdgeFadedRow old) {
    super.didUpdateWidget(old);
    if (old.index != widget.index) _reveal();
  }

  @override
  void dispose() {
    _controller
      ?..removeListener(_edgesChanged)
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
  void _reveal({bool animate = true}) {
    WidgetsBinding.instance.addPostFrameCallback(
      (Duration _) => _scroll(animate: animate),
    );
  }

  /// Where item [index] of [length] sits along a row that can scroll [reach].
  double _offsetFor(double reach) => widget.length < 2
      ? 0
      : reach *
            (widget.index.clamp(0, widget.length - 1) / (widget.length - 1));

  void _scroll({bool animate = true}) {
    final ScrollController? controller = _controller;
    if (!mounted ||
        controller == null ||
        !controller.hasClients ||
        widget.length < 2) {
      return;
    }
    final ScrollPosition position = controller.position;
    final double target = _offsetFor(position.maxScrollExtent);
    final MotionTokens motion = context.ui.motion;
    if (!animate || motion.reduced) {
      controller.jumpTo(target);
      return;
    }
    controller.animateTo(
      target,
      duration: motion.medium,
      curve: MotionTokens.standardCurve,
    );
  }

  bool get _fadeStart =>
      (_controller?.hasClients ?? false) &&
      _controller!.position.extentBefore > 0;

  bool get _fadeEnd =>
      (_controller?.hasClients ?? false) &&
      _controller!.position.extentAfter > 0;

  @override
  Widget build(BuildContext context) {
    if (!widget.revealInitially) return _scroller(context, _controllerAt(0));
    // The row starts on its item, so its first offset needs the width it is
    // given: a `LayoutBuilder` above the scroller hands it to the controller
    // before the scroller exists, which is what makes the first frame right.
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final double viewport = constraints.maxWidth;
        final double reach = viewport.isFinite
            ? math.max(0, widget.extent! - viewport)
            : 0;
        final double? before = _viewport;
        _viewport = viewport;
        if (before != null && before != viewport) _reveal(animate: false);
        return _scroller(context, _controllerAt(_offsetFor(reach)));
      },
    );
  }

  Widget _scroller(BuildContext context, ScrollController controller) {
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
        controller: controller,
        scrollDirection: Axis.horizontal,
        child: widget.child,
      ),
    );
  }
}
