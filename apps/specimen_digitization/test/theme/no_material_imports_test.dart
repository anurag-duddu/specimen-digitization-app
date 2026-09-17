// The Material import gate (10 section 8, `no_material_imports`).
//
// A screen, a pattern or a route builder that still imports `material.dart` is
// still built from Material anatomy, whatever its widgets look like. The
// backlog named every file that did and could only shrink; it is empty.
//
// Scope, widened by the cleanup slot from three directories to the whole of
// `lib/`. It used to hold `lib/src/screens/`, `lib/src/widgets/` and
// `lib/src/app/`, which left `lib/main.dart`, `lib/src/theme/` and every file
// directly under `lib/src/` unscanned: `workspace.dart` was carrying an import
// it did not use at all, and nothing would have caught a new one. Every file
// that may import it is named below with what it takes.
//
// In the package the rule is the same shape: three files may import it and no
// others.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The application files that may import `material.dart`, and why.
///
/// All four are the bridge or the transitions 10 section 1.3 keeps as
/// infrastructure. None of them builds a Material component; the
/// `no_material_components` gate holds that separately, over the same tree.
const Map<String, String> infrastructureImporters = <String, String>{
  'lib/main.dart': 'the carrier MaterialApp, which is the bridge itself',
  'lib/src/theme/app_theme.dart': 'it builds the bridge ThemeData',
  'lib/src/app/app_router.dart':
      'MaterialPage, the only page a PageTransitionsTheme reaches',
  'lib/src/capture/capture_screen.dart':
      'MaterialPageRoute, the pushed form of the same transition',
};

/// The only files in the package allowed to import `material.dart`.
///
/// `field_core.dart` needs `TextField`'s editing behaviour, `theme.dart`
/// builds the `ThemeData` the carrier application expects, and
/// `overlays/tooltip.dart` needs `MaterialLocalizations` for its dismissal
/// strings.
const Set<String> packageMaterialFiles = <String>{
  'packages/specimen_ui/lib/src/primitives/field_core.dart',
  'packages/specimen_ui/lib/src/foundation/theme.dart',
  'packages/specimen_ui/lib/src/controls/overlays/tooltip.dart',
};

/// Files that still import `material.dart` and are not infrastructure.
/// Shrink only.
///
/// Empty since wave 2 took the shell, the entry screens and the D1 patterns
/// off it, and waves 3 and cleanup took the rest.
const List<String> importBacklog = <String>[];

final RegExp _materialImport = RegExp(
  r"import\s+'package:flutter/material\.dart'",
);

/// Every file under [root] that imports `material.dart`.
List<String> importersUnder(String root) {
  final List<String> found = <String>[];
  final Directory directory = Directory(root);
  expect(
    directory.existsSync(),
    isTrue,
    reason: 'run this test from the application root',
  );
  for (final FileSystemEntity entity in directory.listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith('.dart')) continue;
    if (_materialImport.hasMatch(entity.readAsStringSync())) {
      found.add(entity.path);
    }
  }
  found.sort();
  return found;
}

void main() {
  test('no file under lib/ gained a Material import', () {
    final List<String> found = importersUnder('lib');
    final Iterable<String> unexpected = found.where(
      (String path) =>
          !infrastructureImporters.containsKey(path) &&
          !importBacklog.contains(path),
    );
    expect(
      unexpected,
      isEmpty,
      reason:
          'these files import material.dart and are neither infrastructure '
          'nor in the backlog: ${unexpected.join(', ')}. Build on widgets.dart '
          'and read tokens through context.ui.',
    );
  });

  test('every named infrastructure importer still needs it', () {
    // The list is a statement about today, not a permission that outlives its
    // reason: a file that stops importing it comes off, so the next reader
    // sees four names and four live reasons.
    final List<String> found = importersUnder('lib');
    infrastructureImporters.forEach((String path, String why) {
      expect(
        File(path).existsSync(),
        isTrue,
        reason: '$path is named as infrastructure but does not exist',
      );
      expect(
        found.contains(path),
        isTrue,
        reason: '$path no longer imports material.dart ($why); remove it',
      );
    });
  });

  test('the backlog only lists files that still import it', () {
    final List<String> found = importersUnder('lib');
    for (final String path in importBacklog) {
      expect(
        File(path).existsSync(),
        isTrue,
        reason: '$path is in the backlog but does not exist',
      );
      expect(
        found.contains(path),
        isTrue,
        reason: '$path no longer imports material.dart; remove it',
      );
    }
  });

  test('a route builder takes the page and nothing else', () {
    // `MaterialPage` and `MaterialPageRoute` are what a `PageTransitionsTheme`
    // reaches, which is the whole reason 10 section 1.3 keeps them. A bare
    // import would let the anatomy back in behind the same reason, so the two
    // route builders name what they take.
    for (final String path in <String>[
      'lib/src/app/app_router.dart',
      'lib/src/capture/capture_screen.dart',
    ]) {
      final String source = File(path).readAsStringSync();
      expect(
        RegExp(
          r"import 'package:flutter/material\.dart' show Material(?:Page|PageRoute);",
        ).hasMatch(source),
        isTrue,
        reason: '$path should import material.dart with a show clause',
      );
    }
  });

  test('only three files in the package may import material.dart', () {
    final List<String> found = importersUnder('packages/specimen_ui/lib');
    expect(
      found.toSet().difference(packageMaterialFiles),
      isEmpty,
      reason:
          'the design system is built on widgets.dart. Only '
          '${packageMaterialFiles.join(', ')} may import material.dart, and '
          'each says why on the import line.',
    );
  });
}
