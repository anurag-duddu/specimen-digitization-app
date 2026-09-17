// The icon gate (10 section 8, `icons_unique`).
//
// Two parts. One meaning gets one glyph, so no two registry entries may draw
// the same one. And no file under `lib/` may name a Material glyph, which was
// a backlog of 161 uses across 43 files when the refactor started and is now
// nothing at all: the cleanup slot took the last 17 with the adapter that
// held them, and `material_symbols_icons` left the pubspec with them.

import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Every `Symbols.` and `Icons.` use still under `lib/`. Shrink only.
///
/// Empty since the cleanup slot: waves 2 and 3 took every screen, pattern and
/// route off Material Symbols, and `lib/src/theme/icons.dart`, which held the
/// last seventeen behind the v1 `SpecimenIconography` adapter, is gone. The
/// gate now allows nothing, so a glyph named anywhere under `lib/` fails.
///
/// `UiIcons.fromSymbolName` is what a call site was replaced with: it maps
/// the Material name onto a registry key, so the choice of glyph is made once
/// in the registry rather than per call site.
const Map<String, int> glyphBacklog = <String, int>{};

final RegExp _materialGlyph = RegExp(r'\b(?:Symbols|Icons)\.[a-zA-Z_0-9]+');

/// Every file under `lib/` that still names a Material glyph.
Map<String, int> measure() {
  final Map<String, int> found = <String, int>{};
  for (final FileSystemEntity entity in Directory(
    'lib',
  ).listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith('.dart')) continue;
    final int count = _materialGlyph
        .allMatches(entity.readAsStringSync())
        .length;
    if (count > 0) found[entity.path] = count;
  }
  return found;
}

void main() {
  test('every registry entry draws a glyph no other entry draws', () {
    final Map<int, String> byCodePoint = <int, String>{};
    UiIcons.byKey.forEach((String key, IconSpec spec) {
      final IconData glyph = spec.defaultGlyph;
      final String? other = byCodePoint[glyph.codePoint];
      expect(
        other,
        isNull,
        reason:
            'two meanings, one glyph: "$key" and "$other" both draw code '
            'point ${glyph.codePoint}. 09 section 7 calls that a defect.',
      );
      byCodePoint[glyph.codePoint] = key;
    });
    expect(UiIcons.all.length, UiIcons.byKey.length);
  });

  test('every entry that can be current has a fill form', () {
    for (final String key in <String>['queue', 'intake', 'sources']) {
      final IconSpec spec = UiIcons.byKey[key]!;
      expect(
        spec.filled,
        isNotNull,
        reason: '$key is a navigation destination and fills when current',
      );
      expect(spec.resolve(current: true), isNot(spec.resolve()));
    }
    for (final String key in <String>['cleared', 'needsReview', 'deferred']) {
      expect(
        UiIcons.byKey[key]!.weight,
        UiIconWeight.fill,
        reason: '$key is a settled disposition and is drawn filled',
      );
    }
  });

  test('every Material glyph name in the codemod table resolves', () {
    UiIcons.symbolNames.forEach((String name, String key) {
      expect(
        UiIcons.fromSymbolName(name),
        key,
        reason: '$name should map to $key',
      );
      if (key == UiIcons.markKey) return;
      expect(
        UiIcons.spec(key),
        isNotNull,
        reason: '$name maps to $key, which has no entry',
      );
    });
    // The mark is an asset, not a glyph, so it deliberately has no entry.
    expect(UiIcons.spec(UiIcons.markKey), isNull);
    expect(UiIcons.fromSymbolName('not_a_material_glyph'), isNull);
  });

  test('no file gained a Material glyph', () {
    final Map<String, int> found = measure();
    final Iterable<String> unexpected = found.keys.where(
      (String path) => !glyphBacklog.containsKey(path),
    );
    expect(
      unexpected,
      isEmpty,
      reason:
          'these files name a Material glyph and are not in the backlog: '
          '${unexpected.join(', ')}. Use UiIcons.',
    );
    for (final MapEntry<String, int> entry in found.entries) {
      expect(
        entry.value,
        lessThanOrEqualTo(glyphBacklog[entry.key]!),
        reason:
            '${entry.key} went from ${glyphBacklog[entry.key]} to '
            '${entry.value}. The backlog may only shrink.',
      );
    }
  });

  test('the backlog only lists files that still name one', () {
    final Map<String, int> found = measure();
    for (final String path in glyphBacklog.keys) {
      expect(
        File(path).existsSync(),
        isTrue,
        reason: '$path is in the backlog but does not exist',
      );
      expect(
        found.containsKey(path),
        isTrue,
        reason: '$path is clean now, so remove it from the backlog',
      );
    }
  });
}
