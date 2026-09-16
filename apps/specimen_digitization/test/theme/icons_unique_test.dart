// The icon gate (10 section 8, `icons_unique`).
//
// Two parts. One meaning gets one glyph, so no two registry entries may draw
// the same one: that half has no backlog and never will. And no screen may
// name a Material glyph, which is a backlog because 161 uses across 43 files
// move in waves 2 and 3.

import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// Every `Symbols.` and `Icons.` use still under `lib/`. Shrink only.
///
/// Wave 2, slot E1 took the shell, the entry screens and the D1 patterns off
/// it: thirty seven glyphs, every one of them now a `UiIcons` entry.
///
/// `UiIcons.fromSymbolName` is what a screen agent replaces one with: it maps
/// the Material name onto a registry key, so the choice of glyph is made once
/// in the registry rather than per call site.
const Map<String, int> glyphBacklog = <String, int>{
  'lib/src/audit_history.dart': 3,
  'lib/src/capture/capture_screen.dart': 6,
  'lib/src/evidence_panel.dart': 2,
  'lib/src/intake.dart': 3,
  'lib/src/large_record.dart': 1,
  'lib/src/operational_panel.dart': 1,
  'lib/src/reading_declarations.dart': 2,
  'lib/src/region_editor.dart': 5,
  'lib/src/screens/intake/capture_card.dart': 6,
  'lib/src/screens/intake/manifest_panel.dart': 4,
  'lib/src/screens/queue/queue_screen.dart': 6,
  'lib/src/screens/queue/workbench_screen.dart': 1,
  'lib/src/screens/sources/source_screen.dart': 5,
  'lib/src/screens/sources/sources_screen.dart': 4,
  'lib/src/screens/workbench/decision_bar.dart': 3,
  'lib/src/screens/workbench/fields_panel.dart': 2,
  'lib/src/screens/workbench/readings_panel.dart': 3,
  'lib/src/screens/workbench/source_pane.dart': 8,
  'lib/src/screens/workbench/status_strip.dart': 6,
  'lib/src/search_filters.dart': 3,
  'lib/src/theme/icons.dart': 17,
  'lib/src/widgets/authority_candidate_card.dart': 1,
  'lib/src/widgets/evidence_drawer.dart': 2,
  'lib/src/widgets/field_row.dart': 3,
  'lib/src/widgets/queue_row.dart': 1,
  'lib/src/widgets/reading_card.dart': 1,
  'lib/src/widgets/risk_meter.dart': 1,
  'lib/src/widgets/selection_bar.dart': 2,
  'lib/src/widgets/source_import_sheet.dart': 1,
  'lib/src/widgets/source_object_row.dart': 3,
  'lib/src/widgets/thumbnail.dart': 1,
  'lib/src/widgets/upload_item.dart': 9,
  'lib/src/workbench.dart': 8,
};

final RegExp _materialGlyph = RegExp(r'\b(?:Symbols|Icons)\.[a-zA-Z_0-9]+');

/// Every file under `lib/` that still names a Material glyph.
Map<String, int> measure() {
  final Map<String, int> found = <String, int>{};
  for (final FileSystemEntity entity
      in Directory('lib').listSync(recursive: true)) {
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
