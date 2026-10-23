import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'contrast_composite_test.dart' show contrast, surfacesFor;

void main() {
  test('the five identity seeds match the owner reference exactly', () {
    const UiBrandColors brand = UiBrandColors.light;
    expect(brand.obsidian.toARGB32(), 0xFF0E0E11);
    expect(brand.paper.toARGB32(), 0xFFFAF9F6);
    expect(brand.amber.toARGB32(), 0xFFF5A45B);
    expect(brand.iris.toARGB32(), 0xFF7B61FF);
    expect(brand.mist.toARGB32(), 0xFFE6E6EA);
    expect(brand.heroGradient.colors, <Color>[brand.amber, brand.iris]);
    expect(UiBrandColors.dark.heroGradient, brand.heroGradient);
    expect(UiFonts.referenceSans, 'Söhne');
    expect(UiFonts.sans, 'Geist');
  });

  for (final UiThemeData theme in <UiThemeData>[
    UiThemeData.light(),
    UiThemeData.dark(),
  ]) {
    final String mode = theme.isDark ? 'dark' : 'light';
    test('$mode secondary emphasis passes text contrast on every surface', () {
      final UiStatusTriple secondary = theme.brand.secondary;
      for (final MapEntry<String, Color> entry in surfacesFor(theme).entries) {
        expect(
          contrast(secondary.content, entry.value),
          greaterThanOrEqualTo(4.5),
          reason: 'secondary content on ${entry.key}',
        );
      }
      expect(
        contrast(secondary.content, secondary.fill),
        greaterThanOrEqualTo(4.5),
      );
      expect(
        contrast(secondary.onFill, secondary.fill),
        greaterThanOrEqualTo(4.5),
      );
    });

    test('$mode classification does not introduce decorative hues', () {
      final UiStatusColors status = theme.color.status;
      expect(status.processing.content, theme.brand.secondary.content);
      expect(status.authority.content, status.processing.content);
      expect(status.deferred.content, theme.color.inkSecondary);
      expect(status.model.content, status.deferred.content);
      expect(status.cleared.content, status.human.content);
      expect(
        status.triples.values.map((UiStatusTriple t) => t.content).toSet(),
        hasLength(5),
        reason: 'only neutral, Iris, success, warning and error families',
      );
      final Set<Color> approvedFieldSeeds = <Color>{
        theme.brand.amber,
        theme.brand.iris,
        theme.brand.mist,
      };
      expect(theme.field.brandFields.keys, <String>['amber', 'iris', 'mist']);
      for (final UiFieldStyle field in theme.field.all.values) {
        expect(approvedFieldSeeds, contains(field.centre));
      }
      for (final SkyPreset preset in SkyPreset.values) {
        expect(theme.field.sky(preset), isEmpty);
      }
    });
  }

  test(
    'the palette rejects the yellow-green hue family, not only old hex values',
    () {
      final String source = File(
        'lib/src/foundation/palette.dart',
      ).readAsStringSync();
      for (final RegExpMatch match in RegExp(
        r'Color\(0x([0-9a-fA-F]{8})\)',
      ).allMatches(source)) {
        final Color color = Color(int.parse(match.group(1)!, radix: 16));
        if (color.a == 0) continue;
        final HSLColor hsl = HSLColor.fromColor(color);
        final bool rejected =
            hsl.hue >= 55 &&
            hsl.hue <= 95 &&
            hsl.saturation > 0.4 &&
            hsl.lightness > 0.25;
        expect(
          rejected,
          isFalse,
          reason: 'Rejected yellow-green seed: ${match.group(0)}',
        );
      }
    },
  );

  test('rejected yellow cannot return through active brand source files', () {
    // Scan source, including generators: repainting an icon must not silently
    // restore an obsolete palette. Historical documents and golden images
    // are evidence, not executable sources, and are intentionally outside this.
    final List<Directory> roots = <Directory>[
      Directory('lib'),
      Directory('../../lib'),
      Directory('../../assets/brand'),
      Directory('../../tool/brand'),
      Directory('../../android/app/src/main/res'),
      Directory('../../ios/Runner/Assets.xcassets'),
      Directory('../../web'),
    ];
    final RegExp rejected = RegExp(
      r'(?:0x(?:ff)?|#)(?:e8ff47|f2ff66|b7c700)\b|\b(?:232,\s*255,\s*71|242,\s*255,\s*102|183,\s*199,\s*0)\b',
      caseSensitive: false,
    );
    final List<String> violations = <String>[];
    for (final Directory root in roots) {
      expect(
        root.existsSync(),
        isTrue,
        reason: 'Missing scan root ${root.path}',
      );
      for (final FileSystemEntity item in root.listSync(recursive: true)) {
        if (item is! File ||
            !RegExp(
              r'\.(dart|svg|py|json|css|xml|html)$',
            ).hasMatch(item.path)) {
          continue;
        }
        final List<String> lines = item.readAsLinesSync();
        for (int i = 0; i < lines.length; i++) {
          if (rejected.hasMatch(lines[i])) {
            violations.add('${item.path}:${i + 1}');
          }
        }
      }
    }
    expect(violations, isEmpty, reason: violations.join('\n'));
  });
}
