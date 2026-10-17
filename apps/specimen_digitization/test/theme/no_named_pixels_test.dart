// The named pixel gate (10 section 8, `no_named_pixels`).
//
// `no_literal_geometry_test.dart` counts a number written into a call:
// `SizedBox(width: 280)` fails it. `static const double switcherMaxWidth = 280`
// followed by `SizedBox(width: switcherMaxWidth)` passed it, because the call
// reads a name and the name is not a call. A name is not a token: density
// cannot retune it, nothing else can reuse it, and it is still a number nobody
// recorded as a decision.
//
// What counts as a named size, a size and a layout use is defined once, in
// `pixel_scan.dart`. The mechanism is the geometry gate's: a per-file count
// that may go down, never up, held to the tree exactly, and a file at zero
// leaves the map. It reads every file under `lib/`; it has no allowance by
// path or by method.

import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';
import 'pixel_scan.dart';

/// Per-file counts on 2026-10-17, when the gate was written. Shrink only.
///
/// Nineteen named sizes over fourteen files: pane, column and field widths,
/// breakpoints, a mark size, a hit radius, a thumbnail target, a painter's
/// row offset and a list's prefetch distance. The first version of this gate
/// counted twenty five by type alone; reading the use took out two zoom
/// limits, two text-scale probes and a gesture threshold, which are not
/// layout, and three widths nothing reads, and brought in the painter's
/// offset and the thumbnail target.
const Map<String, int> namedPixelBacklog = <String, int>{
  'lib/src/app/auth_layout.dart': 1,
  'lib/src/audit_history.dart': 1,
  'lib/src/capture/capture_screen.dart': 1,
  'lib/src/intake.dart': 1,
  'lib/src/large_record.dart': 1,
  'lib/src/region_editor.dart': 2,
  'lib/src/screens/queue/queue_screen.dart': 1,
  'lib/src/screens/sources/source_screen.dart': 1,
  'lib/src/screens/workbench/readings_panel.dart': 1,
  'lib/src/screens/workbench/workbench_layout.dart': 3,
  'lib/src/widgets/adaptive_form.dart': 3,
  'lib/src/widgets/motion_reveal.dart': 1,
  'lib/src/widgets/queue_row.dart': 1,
  'lib/src/widgets/upload_item.dart': 1,
};

/// Every named size under `lib/` of the application at [base], by file.
Map<String, List<String>> namedPixelCensus({String base = '.'}) =>
    namedSizes(libSources(base: base));

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
  List<String> sizesOf(String text) =>
      namedSizes(<GateSource>[GateSource('lib/x.dart', text)])['lib/x.dart'] ??
      const <String>[];

  test('the scanner reads a named size the way the compiler does', () {
    expect(
      sizesOf(
        'class S {\n'
        '  static const double switcherMaxWidth = 280;\n'
        '  Widget b() => SizedBox(width: switcherMaxWidth);\n'
        '}\n',
      ),
      <String>['line 2, switcherMaxWidth = 280'],
    );
    // Every declarator, every spelling of the number, every kind of name.
    expect(
      sizesOf(
        'const double neutral = 1, panelWidth = 280;\n'
        'Widget b() => SizedBox(width: panelWidth + neutral);\n',
      ),
      <String>['line 1, panelWidth = 280'],
    );
    expect(
      sizesOf(
        'const double w = 0x118;\n'
        'const double x = 280 * 1;\n'
        'const double y = 35 * 8;\n'
        'final z = 280.0;\n'
        'Widget b() => Padding(padding: EdgeInsets.fromLTRB(w, x, y, z));\n',
      ),
      <String>[
        'line 1, w = 0x118',
        'line 2, x = 280 * 1',
        'line 3, y = 35 * 8',
        'line 4, z = 280.0',
      ],
    );
    expect(
      sizesOf(
        'class S {\n'
        '  final double paneWidth = 320;\n'
        '  static late final double _gap = 12;\n'
        '  double get rail => 72;\n'
        '  double get sheet { return 480; }\n'
        '  double column() => 360;\n'
        '  Widget b() => Row(children: <Widget>[\n'
        '    SizedBox(width: paneWidth, height: _gap),\n'
        '    ConstrainedBox(constraints: BoxConstraints(maxWidth: rail)),\n'
        '    SizedBox(width: sheet + column()),\n'
        '  ]);\n'
        '}\n',
      ),
      <String>[
        'line 2, paneWidth = 320',
        'line 3, _gap = 12',
        'line 4, rail = 72',
        'line 5, sheet = 480',
        'line 6, column = 360',
      ],
    );
    // Layout reached through arithmetic, a local, a comparison and another
    // name.
    expect(
      sizesOf(
        'const double paneMin = 320;\n'
        'const double gutter = 24;\n'
        'const double both = paneMin + gutter;\n'
        'Widget b(BoxConstraints c) {\n'
        '  final available = c.maxWidth - gutter;\n'
        '  return c.maxWidth >= paneMin\n'
        '      ? SizedBox(width: available) : SizedBox(width: both);\n'
        '}\n',
      ),
      <String>['line 1, paneMin = 320', 'line 2, gutter = 24'],
    );

    // A factor of a value, a fraction, an index, a token and a number with no
    // layout use are not named sizes.
    expect(
      sizesOf(
        'double get buffer => math.max(ui.space.targetMin * 2, h + s2 * 2);\n'
        'Widget b() => SizedBox(width: buffer);\n',
      ),
      isEmpty,
    );
    expect(
      sizesOf(
        'const double share = 0.55;\n'
        'const double one = 1.0;\n'
        'const double min = WindowClass.mediumMin;\n'
        'Widget b() => SizedBox(width: share + one + min);\n',
      ),
      isEmpty,
    );
    expect(
      sizesOf(
        'double width(List<double> box) => box[2] - box[0];\n'
        'Widget b(List<double> box) => SizedBox(width: width(box));\n',
      ),
      isEmpty,
    );
    expect(
      sizesOf(
        'const double timeoutSeconds = 30;\n'
        'const double sourceMaxScale = 12;\n'
        'Future<void> f() => wait(Duration(seconds: timeoutSeconds.toInt()));\n'
        'Widget v() => InteractiveViewer(maxScale: sourceMaxScale);\n',
      ),
      isEmpty,
    );
    expect(
      sizesOf(
        '/// Was `const double w = 280;`.\n'
        "const String label = '280 wide';\n"
        'Widget b() => Text(label);\n',
      ),
      isEmpty,
    );
  });

  test('a planted named size fails the gate', () {
    // The same census and verdict the gate runs, over a temporary
    // application: a new file with a named width and a backlog file that
    // gained one.
    final String base = plantedApplication(<String, String>{
      'lib/src/widgets/new_panel.dart':
          'class P {\n'
          '  static const double panelWidth = 360;\n'
          '  Widget b() => SizedBox(width: panelWidth);\n'
          '}\n',
      'lib/src/large_record.dart':
          'const double pageHeight = 320;\n'
          'const double pageGap = 24;\n'
          'Widget b() => SizedBox(height: pageHeight + pageGap);\n',
    });
    expect(namedPixelViolations(namedPixelCensus(base: base)), <String>[
      'lib/src/large_record.dart holds 2, allowed '
          '${namedPixelBacklog['lib/src/large_record.dart'] ?? 0}:\n'
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
