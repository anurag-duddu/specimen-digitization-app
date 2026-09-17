// The dash gate (10 section 8, `no_dashes`; 02 section 6 item 1).
//
// No em dash and no en dash in any Dart string literal under `lib/` or the
// package, and none in `design/*.md`. Use a period, a comma, a colon or a
// hyphen.
//
// Both characters are written as escapes here on purpose: this file is covered
// by the rule it enforces, and a literal one would be a finding for anyone
// grepping the tree.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The em dash.
const String emDash = '—';

/// The en dash, banned with it.
const String enDash = '–';

/// A Dart string literal: triple quoted, single quoted or double quoted, raw
/// or not.
final RegExp _stringLiteral = RegExp(
  "r?'''[\\s\\S]*?'''"
  '|r?"""[\\s\\S]*?"""'
  "|r?'(?:\\\\.|[^'\\\\\\n])*'"
  '|r?"(?:\\\\.|[^"\\\\\\n])*"',
);

/// Drops line comments, so a note to a maintainer is not read as a string.
String withoutLineComments(String source) =>
    source.replaceAll(RegExp(r'//.*'), '');

/// The line numbers in [source] whose string literal carries a dash.
List<int> dashesInLiterals(String source) {
  final String code = withoutLineComments(source);
  final List<int> lines = <int>[];
  for (final RegExpMatch match in _stringLiteral.allMatches(code)) {
    final String literal = match.group(0)!;
    if (literal.contains(emDash) || literal.contains(enDash)) {
      lines.add('\n'.allMatches(code.substring(0, match.start)).length + 1);
    }
  }
  return lines;
}

/// Every Dart file the gate scans: the application and the package.
List<File> dartFiles() {
  final List<File> files = <File>[];
  for (final String root in <String>['lib', 'packages/specimen_ui/lib']) {
    final Directory directory = Directory(root);
    expect(
      directory.existsSync(),
      isTrue,
      reason: 'run this test from the application root',
    );
    for (final FileSystemEntity entity in directory.listSync(recursive: true)) {
      if (entity is File && entity.path.endsWith('.dart')) files.add(entity);
    }
  }
  return files;
}

void main() {
  test('no dash in any Dart string literal', () {
    final Map<String, List<int>> found = <String, List<int>>{};
    for (final File file in dartFiles()) {
      final List<int> lines = dashesInLiterals(file.readAsStringSync());
      if (lines.isNotEmpty) found[file.path] = lines;
    }
    expect(
      found,
      isEmpty,
      reason:
          'an em dash or an en dash reached a string. Use a period, a comma, '
          'a colon or a hyphen: $found',
    );
  });

  test('no dash in a design document', () {
    final Directory design = Directory('design');
    expect(
      design.existsSync(),
      isTrue,
      reason: 'run this test from the application root',
    );
    final Map<String, int> found = <String, int>{};
    for (final FileSystemEntity entity in design.listSync()) {
      if (entity is! File || !entity.path.endsWith('.md')) continue;
      final String text = entity.readAsStringSync();
      final int count =
          emDash.allMatches(text).length + enDash.allMatches(text).length;
      if (count > 0) found[entity.path] = count;
    }
    expect(
      found,
      isEmpty,
      reason: '09 section 12 bans both characters, the documents included',
    );
  });

  test('the scanner finds a dash the way a reviewer would', () {
    expect(dashesInLiterals("const String a = 'one${emDash}two';"), <int>[1]);
    expect(dashesInLiterals("const String a = 'one-two';"), isEmpty);
    expect(dashesInLiterals('const String a = "one${enDash}two";'), <int>[1]);
    // A dash in a comment is a matter for the prose, not for this gate.
    expect(dashesInLiterals('// one${emDash}two'), isEmpty);
  });
}
