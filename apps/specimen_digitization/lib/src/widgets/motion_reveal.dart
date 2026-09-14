/// The one way a block of content arrives on a screen
/// (motion and microinteractions, catalog rows 10, 45, 46, 51, 63, 69 and 80).
///
/// Seven rows of the catalog say the same thing in the same words: "height
/// plus opacity", `standard` 200 on the `enter` curve going in, `quick` 100 on
/// the `exit` curve coming out, and nothing at all under reduced motion. They
/// are one component rather than seven copies, so a banner, a conflict card
/// and a lazily loaded evidence payload cannot drift apart.
///
/// It is deliberately not a slide. None of these blocks came from anywhere;
/// they became true. A slide would say they arrived from off screen.
library;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../theme/icons.dart';
import '../theme/motion.dart';
import 'measured_height.dart';

/// Reveals [child] when [visible] turns true, and collapses it when it turns
/// false.
class MotionReveal extends StatefulWidget {
  const MotionReveal({
    super.key,
    required this.visible,
    required this.child,
    this.alignment = Alignment.topLeft,
    this.heightCap,
  });

  /// True when the content belongs on the screen.
  final bool visible;

  /// What arrives. Not built at all while [visible] is false, so a closed
  /// block is not in the semantics tree either.
  final Widget child;

  /// Which edge stays put while the height changes.
  final AlignmentGeometry alignment;

  /// Above this measured height the size animation is dropped and only the
  /// opacity runs (catalog row 45).
  ///
  /// The lazy evidence payloads are unbounded JSON dumps. Animating a three
  /// thousand pixel expansion is a two second scroll lurch, which is the
  /// opposite of the orientation the animation exists to give.
  final double? heightCap;

  /// The cap the evidence payloads use. Named so the rule is one number in
  /// one place rather than a literal at each call site.
  static const double evidenceHeightCap = 400;

  @override
  State<MotionReveal> createState() => _MotionRevealState();
}

class _MotionRevealState extends State<MotionReveal> {
  /// True once the content has measured taller than the cap. Sticky: a block
  /// that is too tall to animate does not become animatable again when the
  /// window gets shorter.
  bool _tooTall = false;

  /// True from the frame after the content is inserted, which is what gives
  /// `AnimatedOpacity` a value to animate away from.
  bool _shown = false;

  @override
  void initState() {
    super.initState();
    // Content that is already there on the first build has not arrived; it
    // was always there. It appears at full opacity, with no animation.
    _shown = widget.visible;
  }

  @override
  void didUpdateWidget(covariant MotionReveal oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.visible == oldWidget.visible) return;
    if (!widget.visible) {
      _shown = false;
      return;
    }
    _shown = false;
    SchedulerBinding.instance.addPostFrameCallback((_) {
      if (mounted && widget.visible) setState(() => _shown = true);
    });
  }

  void _measured(double height) {
    final double? cap = widget.heightCap;
    if (cap == null || _tooTall || height <= cap) return;
    setState(() => _tooTall = true);
  }

  @override
  Widget build(BuildContext context) {
    final MotionTokens motion = context.motion;
    final bool visible = widget.visible;

    // Under reduced motion the block simply is or is not there. A zero
    // duration `AnimatedSize` re-dirties itself during its own layout, so it
    // is not merely pointless here, it is wrong.
    if (motion.reduced) {
      return visible ? _measuredChild() : const SizedBox.shrink();
    }

    final Duration duration = visible ? motion.standard : motion.quick;
    final Widget content = visible
        ? AnimatedOpacity(
            opacity: _shown ? 1 : 0,
            duration: duration,
            curve: MotionTokens.enterCurve,
            child: _measuredChild(),
          )
        : const SizedBox(width: double.infinity);

    if (_tooTall) return content;

    return AnimatedSize(
      duration: duration,
      curve: visible ? MotionTokens.enterCurve : MotionTokens.exitCurve,
      alignment: widget.alignment,
      child: content,
    );
  }

  Widget _measuredChild() => widget.heightCap == null
      ? widget.child
      : MeasuredHeight(onHeight: _measured, child: widget.child);
}
