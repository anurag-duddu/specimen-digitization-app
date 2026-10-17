// What the source gates added on 2026-10-17 share: the list of files they
// read and the prose mask they read them through.
//
// `no_literal_geometry_test.dart` owns the mask. It is the one scanner in this
// directory that blanks strings as well as comments without shifting a line,
// so the newer gates take it from there rather than carrying a second copy that
// could drift from it.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

export 'no_literal_geometry_test.dart'
    show generatedFile, maskProse, modelsPrefix, painterPaintBodies;

/// A numeric literal that is not part of an identifier, including the
/// leading-dot form `.06`.
final RegExp numericLiteral = RegExp(
  r'(?<![A-Za-z0-9_$.])(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?',
);

/// The end of the bracketed expression that opens at [open] in masked [code],
/// one past its closing bracket.
int endOfBracket(String code, int open) {
  int depth = 0;
  for (int i = open; i < code.length; i++) {
    final String c = code[i];
    if (c == '(' || c == '[' || c == '{') {
      depth++;
    } else if (c == ')' || c == ']' || c == '}') {
      depth--;
      if (depth == 0) return i + 1;
    }
  }
  return code.length;
}

/// Where the expression that starts at [start] in masked [code] ends: the
/// first `,`, `;` or closing bracket at its own depth.
int endOfExpression(String code, int start) {
  int depth = 0;
  for (int i = start; i < code.length; i++) {
    final String c = code[i];
    if (c == '(' || c == '[' || c == '{') {
      depth++;
    } else if (c == ')' || c == ']' || c == '}') {
      if (depth == 0) return i;
      depth--;
    } else if ((c == ',' || c == ';') && depth == 0) {
      return i;
    }
  }
  return code.length;
}

/// The 1-based line of [offset] in [source].
int lineOf(String source, int offset) =>
    '\n'.allMatches(source.substring(0, offset)).length + 1;

/// One Dart file a gate reads: the path a reviewer opens and its text.
class GateSource {
  /// Records a file's [path], relative to the application root, and [text].
  const GateSource(this.path, this.text);

  /// The path relative to the application root, `lib/src/...`.
  final String path;

  /// The file as it is on disk.
  final String text;
}

/// Every Dart file under `lib/` of the application at [base], by path relative
/// to [base], sorted.
///
/// [base] is the application root, which is where `flutter test` runs. A test
/// that plants a violation passes a temporary directory laid out the same way,
/// so the gate it proves is the gate that runs, not a copy of its regex.
List<GateSource> libSources({String base = '.'}) {
  final Directory lib = Directory(base == '.' ? 'lib' : '$base/lib');
  expect(
    lib.existsSync(),
    isTrue,
    reason:
        'run this test from the application root; looked in '
        '${lib.absolute.path}',
  );
  final int strip = base == '.' ? 0 : base.length + 1;
  return <GateSource>[
    for (final FileSystemEntity entity in lib.listSync(recursive: true))
      if (entity is File && entity.path.endsWith('.dart'))
        GateSource(entity.path.substring(strip), entity.readAsStringSync()),
  ]..sort((GateSource a, GateSource b) => a.path.compareTo(b.path));
}

/// Writes [files], path to text, under a new temporary application root and
/// returns the root. The directory is deleted when the test ends.
String plantedApplication(Map<String, String> files) {
  final Directory root = Directory.systemTemp.createTempSync('planted_gate_');
  addTearDown(() => root.deleteSync(recursive: true));
  files.forEach((String path, String text) {
    File('${root.path}/$path')
      ..createSync(recursive: true)
      ..writeAsStringSync(text);
  });
  return root.path;
}

/// A comment or a string literal in a Dart source, by offsets.
class ProseSpan {
  /// Records the span from [start] to [end] and whether it is a [comment].
  const ProseSpan(this.start, this.end, {required this.comment});

  /// The offset of its first character: `/` for a comment, the quote for a
  /// string.
  final int start;

  /// One past its last character.
  final int end;

  /// True for a comment, false for a string.
  final bool comment;
}

/// The comments and strings of [source], in order.
///
/// The reading [maskProse] does, keeping which span is which, because the
/// sign-off gate has to find the comment attached to an entry and the string
/// that names it. `exemptions_owner_approved_test.dart` holds the two readers
/// equal on every file either gate scans.
List<ProseSpan> proseSpans(String source) {
  final List<ProseSpan> spans = <ProseSpan>[];
  int i = 0;
  while (i < source.length) {
    if (source.startsWith('//', i)) {
      final int newline = source.indexOf('\n', i);
      final int end = newline < 0 ? source.length : newline;
      spans.add(ProseSpan(i, end, comment: true));
      i = end;
    } else if (source.startsWith('/*', i)) {
      int depth = 1;
      int j = i + 2;
      while (j < source.length && depth > 0) {
        if (source.startsWith('/*', j)) {
          depth++;
          j += 2;
        } else if (source.startsWith('*/', j)) {
          depth--;
          j += 2;
        } else {
          j++;
        }
      }
      spans.add(ProseSpan(i, j, comment: true));
      i = j;
    } else if (source[i] == "'" || source[i] == '"') {
      final int end = _stringEnd(source, i);
      spans.add(ProseSpan(i, end, comment: false));
      i = end;
    } else {
      i++;
    }
  }
  return spans;
}

bool _identifierPart(String c) => RegExp(r'[A-Za-z0-9_$]').hasMatch(c);

int _interpolationEnd(String source, int open) {
  int depth = 0;
  int i = open;
  while (i < source.length) {
    final String c = source[i];
    if (c == '{') {
      depth++;
      i++;
    } else if (c == '}') {
      depth--;
      i++;
      if (depth == 0) return i;
    } else if (c == "'" || c == '"') {
      i = _stringEnd(source, i);
    } else {
      i++;
    }
  }
  return source.length;
}

int _stringEnd(String source, int start) {
  final int n = source.length;
  final String quote = source[start];
  final bool raw =
      start > 0 &&
      source[start - 1] == 'r' &&
      (start < 2 || !_identifierPart(source[start - 2]));
  final bool triple = source.startsWith(quote * 3, start);
  int i = start + (triple ? 3 : 1);
  while (i < n) {
    final String c = source[i];
    if (!raw && c == r'\') {
      i += 2;
      continue;
    }
    if (!raw && c == r'$' && i + 1 < n && source[i + 1] == '{') {
      i = _interpolationEnd(source, i + 1);
      continue;
    }
    if (c == quote) {
      if (!triple) return i + 1;
      if (source.startsWith(quote * 3, i)) return i + 3;
    }
    if (!triple && c == '\n') return i;
    i++;
  }
  return n;
}
