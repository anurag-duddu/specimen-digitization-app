// The Material import gate (10 section 8, `no_material_imports`).
//
// A screen, a pattern or a route builder that still imports `material.dart` is
// still built from Material anatomy, whatever its widgets look like. The
// backlog names every file that does today and may only shrink.
//
// Scope, from 10 section 8: `lib/src/screens/`, `lib/src/widgets/` and
// `lib/src/app/` except `app_router.dart`, which builds `MaterialPage` routes
// and keeps its import until the navigation family lands. `lib/src/theme/` is
// the adapter layer that feeds `ThemeData`, so it is out of scope by
// construction.
//
// In the package the rule is absolute rather than a backlog: three files may
// import it and no others.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The application directories this gate holds.
const List<String> appRoots = <String>[
  'lib/src/screens/',
  'lib/src/widgets/',
  'lib/src/app/',
];

/// The one application file in scope that keeps its import for now.
const String routerException = 'lib/src/app/app_router.dart';

/// The only files in the package allowed to import `material.dart`.
///
/// `field_core.dart` needs `TextField`'s editing behaviour, `theme.dart`
/// builds the `ThemeData` the carrier application expects, and
/// `overlays/tooltip.dart` needs `MaterialLocalizations` for its dismissal
/// strings. The third does not exist yet; it is listed so slot C3 does not
/// have to edit this gate to add it.
const Set<String> packageMaterialFiles = <String>{
  'packages/specimen_ui/lib/src/primitives/field_core.dart',
  'packages/specimen_ui/lib/src/foundation/theme.dart',
  'packages/specimen_ui/lib/src/controls/overlays/tooltip.dart',
};

/// Files that still import `material.dart`. Shrink only.
///
/// Wave 2, slot E1 removed the shell, the entry screens and the D1 patterns
/// from it.
const List<String> importBacklog = <String>[
  'lib/src/screens/intake/capture_card.dart',
  'lib/src/screens/intake/manifest_panel.dart',
  'lib/src/screens/sources/source_screen.dart',
  'lib/src/screens/sources/sources_screen.dart',
  'lib/src/screens/workbench/source_pane.dart',
  'lib/src/widgets/region_overlay.dart',
  'lib/src/widgets/source_import_sheet.dart',
  'lib/src/widgets/source_object_row.dart',
  'lib/src/widgets/upload_item.dart',
];

final RegExp _materialImport = RegExp(
  r"import\s+'package:flutter/material\.dart'",
);

/// Every file under [roots] that imports `material.dart`.
List<String> importersUnder(List<String> roots, {String? except}) {
  final List<String> found = <String>[];
  for (final FileSystemEntity entity in Directory(
    'lib',
  ).listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith('.dart')) continue;
    final String path = entity.path;
    if (!roots.any(path.startsWith)) continue;
    if (path == except) continue;
    if (_materialImport.hasMatch(entity.readAsStringSync())) found.add(path);
  }
  found.sort();
  return found;
}

void main() {
  test('no screen or pattern gained a Material import', () {
    final List<String> found = importersUnder(
      appRoots,
      except: routerException,
    );
    final Iterable<String> unexpected = found.where(
      (String path) => !importBacklog.contains(path),
    );
    expect(
      unexpected,
      isEmpty,
      reason:
          'these files import material.dart and are not in the backlog: '
          '${unexpected.join(', ')}',
    );
  });

  test('the backlog only lists files that still import it', () {
    final List<String> found = importersUnder(
      appRoots,
      except: routerException,
    );
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

  test('only three files in the package may import material.dart', () {
    final List<String> found = <String>[];
    for (final FileSystemEntity entity in Directory(
      'packages/specimen_ui/lib',
    ).listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      if (_materialImport.hasMatch(entity.readAsStringSync())) {
        found.add(entity.path);
      }
    }
    expect(
      found.toSet().difference(packageMaterialFiles),
      isEmpty,
      reason:
          'the design system is built on widgets.dart. Only ${packageMaterialFiles.join(', ')} '
          'may import material.dart, and each says why on the import line.',
    );
  });
}
