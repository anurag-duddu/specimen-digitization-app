// The colour-literal gate (10 section 8, `no_color_literals`), as a test
// rather than a shell line, so it runs wherever `flutter test` runs.
//
// One file in the product may carry a `Color(0x...)` literal:
// `packages/specimen_ui/lib/src/foundation/palette.dart`. Everything else
// reads a role. The scan covers the application's `lib/` and the whole
// package, because moving a literal from one to the other is not progress.
//
// The backlog is empty and stays empty: 10 section 8 gives this gate "none
// from day one".

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The only file allowed to hold a colour literal.
const String paletteFile =
    'packages/specimen_ui/lib/src/foundation/palette.dart';

/// Files that still carry a literal, with the count each holds. Shrink this
/// list; never add to it.
const Map<String, int> migrationBacklog = <String, int>{};

final RegExp _colorLiteral = RegExp(r'Color\(0x');

/// Drops line and doc comments, so a comment that names the pattern is not
/// read as a use of it. The gate is about code.
String withoutComments(String source) =>
    source.replaceAll(RegExp(r'//.*'), '');


/// Every Dart file the gate scans: the application's widgets and screens, and
/// the design system package.
List<File> scannedFiles() {
  final List<File> files = <File>[];
  for (final String root in <String>['lib', 'packages/specimen_ui/lib']) {
    final Directory directory = Directory(root);
    expect(
      directory.existsSync(),
      isTrue,
      reason:
          'run this test from the application root, where $root is visible; '
          'looked in ${directory.absolute.path}',
    );
    for (final FileSystemEntity entity in directory.listSync(recursive: true)) {
      if (entity is File && entity.path.endsWith('.dart')) {
        files.add(entity);
      }
    }
  }
  return files;
}

void main() {
  test('only the palette carries a colour literal', () {
    final Map<String, int> found = <String, int>{};
    for (final File file in scannedFiles()) {
      if (file.path == paletteFile) continue;
      final int count = _colorLiteral
          .allMatches(withoutComments(file.readAsStringSync()))
          .length;
      if (count > 0) found[file.path] = count;
    }

    final Iterable<String> unexpected = found.keys.where(
      (String path) => !migrationBacklog.containsKey(path),
    );
    expect(
      unexpected,
      isEmpty,
      reason:
          'these files must read their colours from a role: '
          '${unexpected.join(', ')}',
    );

    for (final MapEntry<String, int> entry in found.entries) {
      expect(
        entry.value,
        lessThanOrEqualTo(migrationBacklog[entry.key]!),
        reason:
            '${entry.key} gained a colour literal. The backlog may only '
            'shrink.',
      );
    }
  });

  test('the palette itself is where the literals live', () {
    final File palette = File(paletteFile);
    expect(
      palette.existsSync(),
      isTrue,
      reason: 'the one file allowed to hold a literal is missing',
    );
    expect(
      _colorLiteral.allMatches(withoutComments(palette.readAsStringSync())).length,
      greaterThan(0),
      reason:
          'if the palette holds no literal, either the gate is scanning the '
          'wrong path or the token table has moved',
    );
  });

  test('the backlog only lists files that still need migrating', () {
    for (final String path in migrationBacklog.keys) {
      final File file = File(path);
      expect(
        file.existsSync(),
        isTrue,
        reason: '$path is in the backlog but does not exist',
      );
      expect(
        _colorLiteral.hasMatch(withoutComments(file.readAsStringSync())),
        isTrue,
        reason: '$path is clean now, so remove it from the backlog',
      );
    }
  });
}
