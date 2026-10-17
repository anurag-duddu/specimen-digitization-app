// The named pixel gate (10 section 8, `no_named_pixels`).
//
// `no_literal_geometry_test.dart` counts a number written into a call:
// `SizedBox(width: 280)` fails it. `static const double switcherMaxWidth = 280`
// followed by `SizedBox(width: switcherMaxWidth)` passed it, because the call
// reads a name and the name is not a call. Twenty five sizes sat behind that
// gap on 2026-10-17. A name is not a token: density cannot retune it, nothing
// else can reuse it, and it is still a number nobody recorded as a decision.
//
// So a `const` declared `double` or `num`, at the top level, as a static
// member or as a local, fails when its initializer writes a number above 1.
// An untyped `const` fails the same way when that number is written as a
// double, `280.0`. Fractions of a size, 0 to 1, are what 11 section 1 asks
// for and stay. The mechanism is the geometry gate's: a per-file count that may
// go down, never up, and a file at zero leaves the map. It reads the same files
// that gate reads, `lib/` without generated files and without the wire types
// under `lib/src/models`, and makes its one allowance: the `paint` method of a
// `CustomPainter`, where geometry is arithmetic on the size the canvas was
// given.

import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';

/// Per-file counts on 2026-10-17, when the gate was written. Shrink only.
///
/// Twenty five constants over fourteen files. Most are widths, heights and
/// breakpoints in screen code. Three are factors rather than sizes, the source
/// pane's `sourceMaxScale` and `sourceZoomStep` and the workbench's
/// `layoutTextScrollThreshold`; the gate cannot tell a factor from a size, so
/// they are counted, and the change that burns a file down decides where each
/// belongs.
const Map<String, int> namedPixelBacklog = <String, int>{
  'lib/src/app/auth_layout.dart': 1,
  'lib/src/app/shell.dart': 1,
  'lib/src/capture/capture_screen.dart': 1,
  'lib/src/large_record.dart': 1,
  'lib/src/region_editor.dart': 2,
  'lib/src/screens/queue/queue_screen.dart': 3,
  'lib/src/screens/sources/source_screen.dart': 1,
  'lib/src/screens/workbench/readings_panel.dart': 1,
  'lib/src/screens/workbench/source_pane.dart': 2,
  'lib/src/screens/workbench/workbench_layout.dart': 6,
  'lib/src/widgets/adaptive_form.dart': 3,
  'lib/src/widgets/motion_reveal.dart': 1,
  'lib/src/widgets/queue_row.dart': 1,
  'lib/src/widgets/upload_item.dart': 1,
};

final RegExp _constDeclaration = RegExp(
  r'\bconst\s+(?:(double|num)\s+)?([A-Za-z_$][\w$]*)\s*=(?!=)',
);

/// Every named constant in [source] that holds a size above 1, as
/// `line N, name = value`.
List<String> namedPixelsIn(String source) {
  final String code = maskProse(source);
  final List<List<int>> painting = painterPaintBodies(code);
  final List<String> found = <String>[];
  for (final RegExpMatch declaration in _constDeclaration.allMatches(code)) {
    if (painting.any(
      (List<int> span) =>
          declaration.start >= span[0] && declaration.start < span[1],
    )) {
      continue;
    }
    final bool typed = declaration.group(1) != null;
    final int end = endOfExpression(code, declaration.end);
    final String initializer = code.substring(declaration.end, end);
    final bool holdsSize = numericLiteral
        .allMatches(initializer)
        .map((RegExpMatch m) => m.group(0)!)
        .any(
          (String text) =>
              double.parse(text) > 1 &&
              (typed || text.contains(RegExp('[.eE]'))),
        );
    if (holdsSize) {
      found.add(
        'line ${lineOf(source, declaration.start)}, '
        '${declaration.group(2)} = ${initializer.trim()}',
      );
    }
  }
  return found;
}

/// Every scanned file under `lib/` of the application at [base] that names a
/// size, with its findings.
Map<String, List<String>> namedPixelCensus({String base = '.'}) {
  final Map<String, List<String>> found = <String, List<String>>{};
  for (final GateSource source in libSources(base: base)) {
    if (generatedFile.hasMatch(source.path) ||
        source.path.startsWith(modelsPrefix)) {
      continue;
    }
    final List<String> findings = namedPixelsIn(source.text);
    if (findings.isNotEmpty) found[source.path] = findings;
  }
  return found;
}

/// What the gate objects to in [census]: a file not in the backlog, or one
/// that holds more than its count.
List<String> namedPixelViolations(Map<String, List<String>> census) {
  final List<String> found = <String>[];
  census.forEach((String path, List<String> findings) {
    final int allowed = namedPixelBacklog[path] ?? 0;
    if (findings.length > allowed) {
      found.add(
        '$path holds ${findings.length}, allowed $allowed:\n'
        '    ${findings.join('\n    ')}',
      );
    }
  });
  return found;
}

void main() {
  test('the scanner reads a named size the way a reviewer would', () {
    expect(
      namedPixelsIn('static const double switcherMaxWidth = 280;'),
      <String>['line 1, switcherMaxWidth = 280'],
    );
    expect(namedPixelsIn('const double paneWidth = 320;'), <String>[
      'line 1, paneWidth = 320',
    ]);
    expect(namedPixelsIn('const num travel = 56;'), <String>[
      'line 1, travel = 56',
    ]);
    expect(namedPixelsIn('void f() {\n  const double gap = 12;\n}'), <String>[
      'line 2, gap = 12',
    ]);
    expect(namedPixelsIn('static const _width = 280.0;'), <String>[
      'line 1, _width = 280.0',
    ]);
    expect(namedPixelsIn('static const double _edge = -24;'), <String>[
      'line 1, _edge = -24',
    ]);
    expect(namedPixelsIn('static const double _w = 2 * kGap;'), <String>[
      'line 1, _w = 2 * kGap',
    ]);

    // A fraction, a token, an int count and prose are not sizes.
    expect(namedPixelsIn('static const double share = 0.55;'), isEmpty);
    expect(namedPixelsIn('static const double one = 1.0;'), isEmpty);
    expect(namedPixelsIn('const double min = WindowClass.mediumMin;'), isEmpty);
    expect(namedPixelsIn('static const _retries = 3;'), isEmpty);
    expect(namedPixelsIn('static const String label = "280 wide";'), isEmpty);
    expect(namedPixelsIn('/// Was `const double w = 280;`.'), isEmpty);
    expect(namedPixelsIn('final x = const EdgeInsets.all(s4);'), isEmpty);

    // A painter's `paint` is arithmetic on the size it was handed; its fields
    // are not.
    const String painter = '''
class P extends CustomPainter {
  static const double inset = 12;
  @override
  void paint(Canvas canvas, Size size) {
    const y = 7.0;
  }
}
''';
    expect(namedPixelsIn(painter), <String>['line 2, inset = 12']);
  });

  test('a planted named size fails the gate', () {
    // The same census and verdict the gate runs, over a temporary
    // application: a new file with a named width, a backlog file that gained
    // one, a generated file and a wire type, which are skipped.
    final String base = plantedApplication(<String, String>{
      'lib/src/widgets/new_panel.dart':
          'class P {\n  static const double panelWidth = 360;\n}\n',
      'lib/src/large_record.dart':
          'const double pageHeight = 320;\n'
          'const double pageGap = 24;\n',
      'lib/src/widgets/thing.g.dart': 'const double generated = 99;\n',
      'lib/src/models.dart': 'const double wireLimit = 500;\n',
    });
    expect(namedPixelViolations(namedPixelCensus(base: base)), <String>[
      'lib/src/large_record.dart holds 2, allowed 1:\n'
          '    line 1, pageHeight = 320\n'
          '    line 2, pageGap = 24',
      'lib/src/widgets/new_panel.dart holds 1, allowed 0:\n'
          '    line 2, panelWidth = 360',
    ]);
  });

  test('no file gained a named size', () {
    final List<String> violations = namedPixelViolations(namedPixelCensus());
    expect(
      violations,
      isEmpty,
      reason:
          'a size given a name is still a size no token names. Read it from '
          'a specimen_ui token (09 sections 4.2, 5 and 6), derive it from the '
          'type scale (11 section 2.2), or write it as a fraction of the '
          'space the layout was given:\n${violations.join('\n')}',
    );
  });

  test('the backlog matches the tree exactly', () {
    final Map<String, List<String>> census = namedPixelCensus();
    namedPixelBacklog.forEach((String path, int allowed) {
      expect(
        census[path]?.length ?? 0,
        allowed,
        reason:
            '$path is in the backlog at $allowed and now holds '
            '${census[path]?.length ?? 0}; lower its count, or remove it at '
            'zero',
      );
    });
  });
}
