// The layering gate (10 sections 1.1 and 8, `layering`).
//
// A design system is only layered while something checks the direction. This
// parses the imports of every file under `lib/src/` and asserts that
// foundation imports no primitive and no control, and that a primitive imports
// no control. The package cannot import the application at all, because the
// path dependency points one way.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The layers, in order. A file may import its own layer and any below it.
enum Layer {
  /// Tokens. Imports the SDK and nothing of ours.
  foundation,

  /// Geometry and state. Imports the SDK and the foundation.
  primitives,

  /// Components. Imports the SDK, the foundation and the primitives.
  controls,
}

/// The layer [path] belongs to, or null for anything outside `lib/src/`.
Layer? layerOf(String path) {
  if (path.contains('/foundation/')) return Layer.foundation;
  if (path.contains('/primitives/')) return Layer.primitives;
  if (path.contains('/controls/')) return Layer.controls;
  return null;
}

/// The only files allowed to import `material.dart` (10 section 8).
const Set<String> materialAllowlist = <String>{
  'lib/src/primitives/field_core.dart',
  'lib/src/foundation/theme.dart',
  'lib/src/controls/overlays/tooltip.dart',
};

final RegExp _import = RegExp(r"^\s*(?:import|export)\s+'([^']+)'", multiLine: true);

/// Every Dart file under `lib/src/`, by path relative to the package root.
List<String> sourceFiles() {
  final Directory root = Directory('lib/src');
  expect(
    root.existsSync(),
    isTrue,
    reason: 'run this test from the package root',
  );
  return <String>[
    for (final FileSystemEntity entity in root.listSync(recursive: true))
      if (entity is File && entity.path.endsWith('.dart')) entity.path,
  ]..sort();
}

/// The import and export targets of [path].
List<String> targetsOf(String path) => _import
    .allMatches(File(path).readAsStringSync())
    .map((RegExpMatch m) => m.group(1)!)
    .toList();

/// The layer a relative import resolves into, or null when it leaves `src/`.
Layer? targetLayer(String target) => layerOf(target);

void main() {
  test('the gate is looking at the package it thinks it is', () {
    final List<String> files = sourceFiles();
    expect(files, isNotEmpty);
    expect(
      files.where((String f) => layerOf(f) == Layer.foundation),
      isNotEmpty,
    );
    expect(
      files.where((String f) => layerOf(f) == Layer.primitives),
      isNotEmpty,
    );
  });

  test('a file never imports a layer above its own', () {
    for (final String path in sourceFiles()) {
      final Layer? layer = layerOf(path);
      if (layer == null) continue;
      for (final String target in targetsOf(path)) {
        final Layer? imported = targetLayer(target);
        if (imported == null) continue;
        expect(
          imported.index,
          lessThanOrEqualTo(layer.index),
          reason:
              '$path is ${layer.name} and imports $target, which is '
              '${imported.name}. The direction is one way (10 section 1.1).',
        );
      }
    }
  });

  test('the package never imports the application', () {
    for (final String path in sourceFiles()) {
      for (final String target in targetsOf(path)) {
        expect(
          target.startsWith('package:specimen_digitization'),
          isFalse,
          reason:
              '$path imports $target. The path dependency points one way; a '
              'design system that knows what a specimen is is not one.',
        );
      }
    }
  });

  test('only three files import material.dart', () {
    final List<String> found = <String>[
      for (final String path in sourceFiles())
        if (targetsOf(path).contains('package:flutter/material.dart')) path,
    ];
    expect(
      found.toSet().difference(materialAllowlist),
      isEmpty,
      reason:
          'the design system is built on widgets.dart. `material.dart` is '
          'infrastructure, and each of the three files allowed to import it '
          'says why on the import line (10 section 1.3).',
    );
  });

  test('the foundation does not reach for a widget of ours', () {
    // A token is a value. The moment a token file imports a primitive, a
    // widget can no longer be swapped without moving the token with it.
    for (final String path in sourceFiles()) {
      if (layerOf(path) != Layer.foundation) continue;
      for (final String target in targetsOf(path)) {
        expect(
          target.contains('primitives/') || target.contains('controls/'),
          isFalse,
          reason: '$path is a token file and imports $target',
        );
      }
    }
  });
}
