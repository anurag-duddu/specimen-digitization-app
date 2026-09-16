/// Loading placeholders (10 sections 4.5 and 5; 04 section 2.5; 06 section 3).
///
/// Tonal blocks on `UiSkeleton`, no shimmer. A shimmer is a sweep across the
/// content, and a sweep is decoration; what is left is a slow opacity pulse
/// that stops outright under reduced motion. Placeholders are hidden from the
/// semantics tree and paired with exactly one live "Loading" node.
library;

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// One tonal bar. The building block of [SkeletonRow] and [SkeletonBlock].
class SkeletonBar extends StatelessWidget {
  const SkeletonBar({super.key, required this.widthFactor, this.height});

  /// Fraction of the available width, 0 to 1.
  final double widthFactor;

  /// Bar height. Defaults to one line of body text with its leading.
  final double? height;

  @override
  Widget build(BuildContext context) =>
      UiSkeleton.line(widthFactor: widthFactor, height: height);
}

/// Three bars at 60, 40 and 80 percent width, standing in for one row of
/// text. Excluded from the semantics tree.
class SkeletonRow extends StatelessWidget {
  const SkeletonRow({super.key});

  /// The three widths, in order.
  static const List<double> widthFactors = <double>[0.6, 0.4, 0.8];

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return ExcludeSemantics(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          for (int i = 0; i < widthFactors.length; i++) ...<Widget>[
            if (i > 0) SizedBox(height: ui.space.s1),
            SkeletonBar(widthFactor: widthFactors[i]),
          ],
        ],
      ),
    );
  }
}

/// A single rectangle standing in for a block of content, such as a thumbnail
/// or a panel. Excluded from the semantics tree.
class SkeletonBlock extends StatelessWidget {
  const SkeletonBlock({super.key, this.width, this.height});

  /// Width in logical pixels. Fills the parent when null.
  final double? width;

  /// Height in logical pixels. Defaults to the expanded row height.
  final double? height;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return ExcludeSemantics(
      child: SizedBox(
        width: width,
        child: UiSkeleton.line(height: height ?? ui.space.rowExpanded),
      ),
    );
  }
}

/// The one live node that says something is loading.
///
/// Pair exactly one of these with any number of placeholders, so a screen
/// reader hears "Loading queue" once rather than hearing nothing at all from
/// a screen full of hidden boxes.
///
/// The invisible form is an announcement, not a node. A live region whose
/// child is a zero-sized box has an empty rect, an empty rect is dropped from
/// the semantics tree, and a reviewer using a screen reader then got silence
/// for the whole first load: finding V-4. A momentary event with no text on
/// screen to host it is exactly what `sendAnnouncement` is for. It is not
/// given a one-pixel box instead: a node a screen reader can focus and nobody
/// can see is worse than the announcement.
class LoadingAnnouncement extends StatefulWidget {
  const LoadingAnnouncement({
    super.key,
    required this.thing,
    this.visible = false,
  });

  /// What is loading, as a noun phrase: "queue", "evidence", "authority
  /// candidates". The word "Loading" is added here so every announcement is
  /// worded the same way.
  final String thing;

  /// When true the label is also drawn, for a wait longer than three seconds
  /// (02 section 4.7). Placeholders alone carry a shorter wait.
  final bool visible;

  /// The exact phrase this widget exposes.
  String get message => 'Loading $thing';

  @override
  State<LoadingAnnouncement> createState() => _LoadingAnnouncementState();
}

class _LoadingAnnouncementState extends State<LoadingAnnouncement> {
  @override
  void initState() {
    super.initState();
    if (!widget.visible) _announce();
  }

  @override
  void didUpdateWidget(covariant LoadingAnnouncement oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.visible && oldWidget.message != widget.message) _announce();
  }

  /// Says it once, after the frame that mounted this widget.
  void _announce() {
    final String message = widget.message;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (!MediaQuery.supportsAnnounceOf(context)) return;
      SemanticsService.sendAnnouncement(
        View.of(context),
        message,
        Directionality.of(context),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.visible) return const SizedBox.shrink();
    final UiThemeData ui = context.ui;
    return Semantics(
      liveRegion: true,
      label: widget.message,
      excludeSemantics: true,
      child: Text(
        // The ellipsis character, never three periods.
        '${widget.message}…',
        style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
      ),
    );
  }
}
