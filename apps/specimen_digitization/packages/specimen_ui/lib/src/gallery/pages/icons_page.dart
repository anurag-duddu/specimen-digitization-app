/// Every registry key, in regular and in fill (10 section 6).
///
/// The page that makes "two glyphs for one meaning" visible: the registry is
/// drawn in the order it is declared, so a duplicate reads as a repeat.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the icons page.
Widget buildIconsPage(BuildContext context) {
  final UiThemeData ui = context.ui;
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      GallerySection(
        title: 'The registry, ${UiIcons.byKey.length} keys',
        child: Wrap(
          spacing: ui.space.s3,
          runSpacing: ui.space.s3,
          children: <Widget>[
            for (final MapEntry<String, IconSpec> entry
                in UiIcons.byKey.entries)
              _Entry(name: entry.key, spec: entry.value),
          ],
        ),
      ),
      GallerySection(
        title: 'The four sizes',
        child: Wrap(
          spacing: ui.space.s6,
          runSpacing: ui.space.s4,
          crossAxisAlignment: WrapCrossAlignment.end,
          children: <Widget>[
            for (final UiIconSize size in UiIconSize.values)
              GallerySpecimen(
                label: size.name,
                note: '${size.dimension.toStringAsFixed(0)} dp',
                child: UiIcon(UiIcons.queue, size: size),
              ),
          ],
        ),
      ),
      GallerySection(
        title: 'Regular and fill, where 09 names both',
        child: Wrap(
          spacing: ui.space.s6,
          runSpacing: ui.space.s4,
          children: <Widget>[
            for (final String key in <String>['queue', 'intake', 'sources'])
              GallerySpecimen(
                label: key,
                note: 'fill when current',
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    UiIcon(UiIcons.byKey[key]!),
                    SizedBox(width: ui.space.s2),
                    UiIcon(UiIcons.byKey[key]!, current: true),
                  ],
                ),
              ),
          ],
        ),
      ),
    ],
  );
}

class _Entry extends StatelessWidget {
  const _Entry({required this.name, required this.spec});

  final String name;
  final IconSpec spec;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SizedBox(
      width: 132,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          UiIcon(spec),
          SizedBox(height: ui.space.s1),
          Text(
            name,
            style: ui.type.mono.digest.copyWith(color: ui.color.inkSecondary),
            textAlign: TextAlign.center,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
