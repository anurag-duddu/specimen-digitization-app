// The grep gate from the design system, section 8.3, as a test rather than a
// shell line, so it runs wherever `flutter test` runs.
//
// `lib/src/theme/tokens.dart` is the only file allowed to carry a
// `Color(0x...)` literal. The files still holding literals today are listed in
// [migrationBacklog]; every later step of the redesign removes entries, and
// the list may only ever shrink.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Widget files that still carry color literals, with the count each holds at
/// the time of writing. Shrink this list; never add to it.
const Map<String, int> migrationBacklog = <String, int>{
  // Four disposition colors plus the synthetic environment band. Migration
  // step 4 and step 5 of the design system.
  'lib/src/workspace.dart': 6,
  // The image matte and the diff highlight. Migration step 6.
  'lib/src/workbench.dart': 2,
};

final RegExp _colorLiteral = RegExp(r'Color\(0x');

void main() {
  test('no widget outside lib/src/theme/ carries a color literal', () {
    final Directory root = Directory('lib/src');
    expect(
      root.existsSync(),
      isTrue,
      reason:
          'run this test from the package root, where lib/src is visible; '
          'looked in ${root.absolute.path}',
    );

    final Map<String, int> found = <String, int>{};
    for (final FileSystemEntity entity in root.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final String path = entity.path;
      if (path.startsWith('lib/src/theme/')) continue;
      final int count = _colorLiteral
          .allMatches(entity.readAsStringSync())
          .length;
      if (count > 0) found[path] = count;
    }

    final int remaining = found.values.fold(0, (int a, int b) => a + b);
    // ignore: avoid_print
    print(
      'Color literals still outside lib/src/theme/: $remaining '
      'in ${found.length} file(s). Allowed while the migration runs: '
      '${migrationBacklog.values.fold(0, (int a, int b) => a + b)} '
      'in ${migrationBacklog.length} file(s).',
    );

    final Iterable<String> unexpected = found.keys.where(
      (String path) => !migrationBacklog.containsKey(path),
    );
    expect(
      unexpected,
      isEmpty,
      reason:
          'these files must read their colors from the theme: '
          '${unexpected.join(', ')}',
    );

    for (final MapEntry<String, int> entry in found.entries) {
      expect(
        entry.value,
        lessThanOrEqualTo(migrationBacklog[entry.key]!),
        reason:
            '${entry.key} gained a color literal. The backlog may only shrink.',
      );
    }
  });

  test('the backlog only lists files that still need migrating', () {
    for (final String path in migrationBacklog.keys) {
      expect(
        File(path).existsSync(),
        isTrue,
        reason: '$path is in the backlog but does not exist',
      );
      expect(
        _colorLiteral.hasMatch(File(path).readAsStringSync()),
        isTrue,
        reason: '$path is clean now, so remove it from the backlog',
      );
    }
  });
}
