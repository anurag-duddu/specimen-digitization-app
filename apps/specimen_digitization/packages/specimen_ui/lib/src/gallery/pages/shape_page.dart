/// Every radius and every stroke (10 section 6).
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the shape page.
Widget buildShapePage(BuildContext context) {
  final UiThemeData ui = context.ui;
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      GallerySection(
        title: 'Radii',
        child: Wrap(
          spacing: ui.space.s4,
          runSpacing: ui.space.s4,
          children: <Widget>[
            for (final MapEntry<String, double> radius
                in ui.shape.radii.entries)
              GallerySpecimen(
                label: radius.key,
                note: '${radius.value.toStringAsFixed(0)} dp',
                child: SizedBox(
                  width: 120,
                  height: 80,
                  child: DecoratedBox(
                    decoration: ShapeDecoration(
                      color: ui.color.paper,
                      shape: Squircle.border(
                        radius.value,
                        side: BorderSide(color: ui.color.boundary),
                      ),
                    ),
                  ),
                ),
              ),
            GallerySpecimen(
              label: 'radius.capsule',
              note: 'a stadium, never a large radius',
              child: SizedBox(
                width: 120,
                height: 48,
                child: DecoratedBox(
                  decoration: ShapeDecoration(
                    color: ui.color.paper,
                    shape: StadiumBorder(
                      side: BorderSide(color: ui.color.boundary),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
      GallerySection(
        title: 'Strokes',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            for (final MapEntry<String, double> stroke
                in ui.shape.strokes.entries)
              Padding(
                padding: EdgeInsetsDirectional.only(bottom: ui.space.s3),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: <Widget>[
                    SizedBox(
                      width: 160,
                      height: stroke.value,
                      child: ColoredBox(
                        color: stroke.key == 'hairline'
                            ? ui.color.hairline
                            : ui.color.ink,
                      ),
                    ),
                    SizedBox(width: ui.space.s3),
                    Text(
                      '${stroke.key}  ${stroke.value.toStringAsFixed(0)} dp',
                      style: ui.type.mono.identifier.copyWith(
                        color: ui.color.inkSecondary,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
      GallerySection(
        title: 'Optical nesting',
        child: Wrap(
          children: <Widget>[
            GallerySpecimen(
              label: 'tile 20, inset 12, inner 8',
              child: SizedBox(
                width: 160,
                height: 120,
                child: DecoratedBox(
                  decoration: ShapeDecoration(
                    color: ui.color.paper,
                    shape: Squircle.border(
                      ui.shape.tile,
                      side: BorderSide(color: ui.color.hairline),
                    ),
                  ),
                  child: Padding(
                    padding: EdgeInsetsDirectional.all(ui.space.s3),
                    child: DecoratedBox(
                      decoration: ShapeDecoration(
                        color: ui.color.ground,
                        shape: Squircle.border(
                          ui.shape.nested(ui.shape.tile, ui.space.s3),
                          side: BorderSide(color: ui.color.hairline),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    ],
  );
}
