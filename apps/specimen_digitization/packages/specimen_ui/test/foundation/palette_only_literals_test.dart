// The colour-literal gate, package half (10 section 8, `no_color_literals`).
//
// The application runs the same scan over both trees. This one runs from the
// package, so a change here fails before it reaches the application's suite.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The only file in the package allowed to hold a colour literal.
const String paletteFile = 'lib/src/foundation/palette.dart';

final RegExp _colorLiteral = RegExp(r'Color\(0x');

/// Drops line and doc comments, so a comment that names the pattern is not
/// read as a use of it. The gate is about code.
String withoutComments(String source) => source.replaceAll(RegExp(r'//.*'), '');

void main() {
  test('only the palette carries a colour literal', () {
    final Map<String, int> found = <String, int>{};
    for (final FileSystemEntity entity in Directory(
      'lib',
    ).listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      if (entity.path == paletteFile) continue;
      final int count = _colorLiteral
          .allMatches(withoutComments(entity.readAsStringSync()))
          .length;
      if (count > 0) found[entity.path] = count;
    }
    expect(
      found,
      isEmpty,
      reason:
          'every colour in this package is a role. Add the value to '
          '$paletteFile and give it a name that says what it does: $found',
    );
  });

  test('the palette is where the literals live', () {
    final File palette = File(paletteFile);
    expect(palette.existsSync(), isTrue);
    expect(
      _colorLiteral
          .allMatches(withoutComments(palette.readAsStringSync()))
          .length,
      greaterThan(50),
      reason:
          'if the palette holds almost no literal, either this gate is '
          'scanning the wrong path or the token table has moved',
    );
  });

  test('the palette imports nothing but Color', () {
    // Kept pure so a contrast test can run without a binding, and so the one
    // file holding the values cannot grow a dependency on a widget.
    final String source = File(paletteFile).readAsStringSync();
    final Iterable<String> imports = RegExp(
      r"^import '([^']+)'",
      multiLine: true,
    ).allMatches(source).map((RegExpMatch m) => m.group(1)!);
    expect(imports, <String>['dart:ui']);
  });
}
