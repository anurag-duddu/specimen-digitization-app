/// The type specimen (10 section 6).
///
/// Every role at its own size and weight, the mono line 09 section 4.1 pins by
/// golden, and a tabular-figure column that shows a changed digit staying in
/// its position.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the type page.
Widget buildTypePage(BuildContext context) {
  final UiThemeData ui = context.ui;
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      GallerySection(
        title: 'Proportional roles',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (final MapEntry<String, TextStyle> role in ui.type.all.entries)
              Padding(
                padding: EdgeInsetsDirectional.only(bottom: ui.space.s3),
                child: _Role(name: role.key, style: role.value),
              ),
          ],
        ),
      ),
      GallerySection(
        title: 'Monospace roles',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (final MapEntry<String, TextStyle> role
                in ui.type.mono.all.entries)
              Padding(
                padding: EdgeInsetsDirectional.only(bottom: ui.space.s3),
                child: _Role(
                  name: role.key,
                  style: role.value,
                  sample: UiType.monoSpecimen,
                ),
              ),
          ],
        ),
      ),
      GallerySection(
        title: 'Tabular figures',
        child: Wrap(
          spacing: ui.space.s8,
          runSpacing: ui.space.s4,
          children: <Widget>[
            _Figures(style: ui.type.displayMedium, label: 'display.medium'),
            _Figures(style: ui.type.body, label: 'body'),
            _Figures(style: ui.type.mono.identifier, label: 'mono.identifier'),
          ],
        ),
      ),
      GallerySection(
        title: 'A numeral and its unit',
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text('1284', style: ui.type.displayHero),
            SizedBox(width: ui.space.s2),
            Text(
              'RECORDS',
              style: ui.type.unit.copyWith(color: ui.color.inkTertiary),
            ),
          ],
        ),
      ),
    ],
  );
}

class _Role extends StatelessWidget {
  const _Role({required this.name, required this.style, this.sample});

  final String name;
  final TextStyle style;
  final String? sample;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          sample ?? 'Needs human review, sorted by age',
          style: style.copyWith(color: ui.color.ink),
        ),
        Text(
          '$name  ${style.fontSize?.toStringAsFixed(0)} px  '
          'wght ${style.fontVariations?.single.value.toStringAsFixed(0)}',
          style: ui.type.mono.digest.copyWith(color: ui.color.inkTertiary),
        ),
      ],
    );
  }
}

class _Figures extends StatelessWidget {
  const _Figures({required this.style, required this.label});

  final TextStyle style;
  final String label;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (final String row in <String>['1284', '1184', '1084'])
          Text(row, style: style.copyWith(color: ui.color.ink)),
        Text(
          label,
          style: ui.type.mono.digest.copyWith(color: ui.color.inkTertiary),
        ),
      ],
    );
  }
}
