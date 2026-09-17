/// The three sky presets, each under the three glass levels (10 section 6).
///
/// The page the "instrument under frosted glass" register is judged on: if a
/// field reads as coloured paint or a pane reads as a texture rather than a
/// container, it shows here first.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the fields and glass page.
Widget buildFieldsPage(BuildContext context) {
  final UiThemeData ui = context.ui;
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      for (final SkyPreset preset in SkyPreset.values)
        GallerySection(
          title: 'sky.${preset.name}',
          child: SizedBox(height: 220, child: _Preset(preset: preset)),
        ),
      GallerySection(
        title: 'The five fields at their centre alpha',
        child: Wrap(
          spacing: ui.space.s3,
          runSpacing: ui.space.s3,
          children: <Widget>[
            for (final MapEntry<String, UiFieldStyle> field
                in ui.field.all.entries)
              GallerySpecimen(
                label: 'field.${field.key}',
                note: 'alpha ${field.value.centreAlpha}',
                child: SizedBox(
                  width: 120,
                  height: 80,
                  child: DecoratedBox(
                    decoration: ShapeDecoration(
                      color: field.value.extremeOver(ui.color.ground),
                      shape: Squircle.border(ui.shape.inner),
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

/// One preset with a pane of each glass level over it.
class _Preset extends StatelessWidget {
  const _Preset({required this.preset});

  final SkyPreset preset;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Squircle.clip(
      radius: ui.shape.tile,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          FieldLayer(preset: preset),
          Padding(
            padding: EdgeInsetsDirectional.all(ui.space.s4),
            child: Wrap(
              spacing: ui.space.s4,
              runSpacing: ui.space.s4,
              children: <Widget>[
                for (final MapEntry<String, UiGlassStyle> level
                    in ui.glass.all.entries)
                  SizedBox(
                    width: 200,
                    child: GlassSurface(
                      level: level.value.level,
                      padding: EdgeInsetsDirectional.all(ui.space.s3),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: <Widget>[
                          Text(
                            'glass.${level.key}',
                            style: ui.type.title.copyWith(color: ui.color.ink),
                          ),
                          Text(
                            'sigma ${level.value.sigma.toStringAsFixed(0)}',
                            style: ui.type.bodySmall.copyWith(
                              color: ui.color.inkSecondary,
                            ),
                          ),
                          Text(
                            'ink.tertiary reads here',
                            style: ui.type.bodySmall.copyWith(
                              color: ui.color.inkTertiary,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
