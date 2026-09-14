/// Loading placeholders (design system, 7.2; motion, 2.5; accessibility, 3.1).
///
/// Tonal blocks, no shimmer. A shimmer is a repeating animation, and repeating
/// animations are not auto shortened by Flutter's reduced motion handling, so
/// the only safe sweep is no sweep. Placeholders are hidden from the semantics
/// tree and paired with exactly one live "Loading" node.
library;

import 'package:flutter/material.dart';

import '../theme/icons.dart';

/// One tonal bar. The building block of [SkeletonRow] and [SkeletonBlock].
class SkeletonBar extends StatelessWidget {
  const SkeletonBar({super.key, required this.widthFactor, this.height});

  /// Fraction of the available width, 0 to 1.
  final double widthFactor;

  /// Bar height. Defaults to the inline icon size, which is the height of a
  /// `bodyMedium` line with its leading.
  final double? height;

  @override
  Widget build(BuildContext context) => Align(
    alignment: AlignmentDirectional.centerStart,
    child: FractionallySizedBox(
      widthFactor: widthFactor,
      child: Container(
        height: height ?? context.sizes.iconInline,
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(context.shape.radiusXs),
        ),
      ),
    ),
  );
}

/// Three bars at 60, 40 and 80 percent width, standing in for one row of
/// text. Excluded from the semantics tree.
class SkeletonRow extends StatelessWidget {
  const SkeletonRow({super.key});

  /// The three widths, in order.
  static const List<double> widthFactors = <double>[0.6, 0.4, 0.8];

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (int i = 0; i < widthFactors.length; i++) ...<Widget>[
          if (i > 0) SizedBox(height: context.space.space1),
          SkeletonBar(widthFactor: widthFactors[i]),
        ],
      ],
    ),
  );
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
  Widget build(BuildContext context) => ExcludeSemantics(
    child: Container(
      width: width,
      height: height ?? context.sizes.rowExpanded,
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHigh,
        borderRadius: BorderRadius.circular(context.shape.radiusSm),
      ),
    ),
  );
}

/// The one live node that says something is loading.
///
/// Pair exactly one of these with any number of placeholders, so a screen
/// reader hears "Loading queue" once rather than hearing nothing at all from
/// a screen full of hidden boxes.
class LoadingAnnouncement extends StatelessWidget {
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
  /// (UX writing, section 4.7). Placeholders alone carry a shorter wait.
  final bool visible;

  /// The exact phrase this widget exposes.
  String get message => 'Loading $thing';

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    label: message,
    excludeSemantics: true,
    child: visible
        ? Text(
            // The ellipsis character, never three periods.
            '$message…',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          )
        : const SizedBox.shrink(),
  );
}
