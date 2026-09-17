/// Every colour role on every surface (10 section 6).
///
/// The same set the `contrast_composite` gate walks, drawn rather than
/// measured: ground, paper, matte and each glass level, with every text role
/// and every status triple on it.
library;

import 'package:flutter/widgets.dart';

import '../../../specimen_ui.dart';
import '../gallery_shell.dart';

/// Builds the colour page.
Widget buildColourPage(BuildContext context) {
  final UiThemeData ui = context.ui;
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      GallerySection(
        title: 'Text roles on every solid surface',
        child: Wrap(
          spacing: ui.space.s4,
          runSpacing: ui.space.s4,
          children: <Widget>[
            for (final MapEntry<String, Color> surface
                in ui.color.surfaces.entries)
              _TextRolesOn(label: surface.key, background: surface.value),
          ],
        ),
      ),
      GallerySection(
        title: 'Text roles on each glass level',
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
                  child: _TextRoles(label: 'glass.${level.key}'),
                ),
              ),
          ],
        ),
      ),
      GallerySection(
        title: 'Status triples',
        child: Wrap(
          spacing: ui.space.s3,
          runSpacing: ui.space.s3,
          children: <Widget>[
            for (final MapEntry<String, UiStatusTriple> triple
                in ui.color.status.triples.entries)
              _Triple(name: triple.key, triple: triple.value),
          ],
        ),
      ),
      GallerySection(
        title: 'Edges, disabled and the mark',
        child: Wrap(
          spacing: ui.space.s3,
          runSpacing: ui.space.s3,
          children: <Widget>[
            _Swatch(name: 'hairline', colour: ui.color.hairline),
            _Swatch(name: 'boundary', colour: ui.color.boundary),
            _Swatch(name: 'focus.ring', colour: ui.color.focusRing),
            _Swatch(name: 'disabled.content', colour: ui.color.disabledContent),
            _Swatch(name: 'disabled.outline', colour: ui.color.disabledOutline),
            _Swatch(name: 'accent', colour: ui.color.accent),
            _Swatch(name: 'on.accent', colour: ui.color.onAccent),
          ],
        ),
      ),
    ],
  );
}

class _TextRolesOn extends StatelessWidget {
  const _TextRolesOn({required this.label, required this.background});

  final String label;
  final Color background;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return SizedBox(
      width: 200,
      child: DecoratedBox(
        decoration: ShapeDecoration(
          color: background,
          shape: Squircle.border(
            ui.shape.tile,
            side: BorderSide(color: ui.color.hairline),
          ),
        ),
        child: Padding(
          padding: EdgeInsetsDirectional.all(ui.space.s3),
          child: _TextRoles(label: label),
        ),
      ),
    );
  }
}

class _TextRoles extends StatelessWidget {
  const _TextRoles({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (final MapEntry<String, Color> role in ui.color.textRoles.entries)
          Text(role.key, style: ui.type.body.copyWith(color: role.value)),
        SizedBox(height: ui.space.s1),
        Text(
          label,
          style: ui.type.mono.digest.copyWith(color: ui.color.inkTertiary),
        ),
      ],
    );
  }
}

class _Triple extends StatelessWidget {
  const _Triple({required this.name, required this.triple});

  final String name;
  final UiStatusTriple triple;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return GallerySpecimen(
      label: name,
      child: SizedBox(
        width: 168,
        child: DecoratedBox(
          decoration: ShapeDecoration(
            color: triple.fill,
            shape: Squircle.border(ui.shape.inner),
          ),
          child: Padding(
            padding: EdgeInsetsDirectional.all(ui.space.s3),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  'on fill',
                  style: ui.type.label.copyWith(color: triple.onFill),
                ),
                Text(
                  'content',
                  style: ui.type.label.copyWith(color: triple.content),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Swatch extends StatelessWidget {
  const _Swatch({required this.name, required this.colour});

  final String name;
  final Color colour;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return GallerySpecimen(
      label: name,
      child: SizedBox(
        width: 120,
        height: 40,
        child: DecoratedBox(
          decoration: ShapeDecoration(
            color: colour,
            shape: Squircle.border(
              ui.shape.inner,
              side: BorderSide(color: ui.color.hairline),
            ),
          ),
        ),
      ),
    );
  }
}
