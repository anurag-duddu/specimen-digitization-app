// The opacity literal gate (10 section 8, `no_alpha_literals`).
//
// `no_color_literals_test.dart` counts `Color(0x`. A role with an opacity typed
// over it, `ui.color.ink.withValues(alpha: .06)`, passed it, and is the same
// thing: a colour nobody named, which a mode, a contrast check or a later
// palette change cannot reach. The colour belongs in the theme as a role or an
// overlay token.
//
// So an opacity written as a number fails: in `withValues(alpha: ...)`, in the
// deprecated `withOpacity(...)`, in `withAlpha(...)`, in the design system's
// own `stateLayer(...)`, which takes an opacity, in an `opacity:` argument
// (`Opacity`, `AnimatedOpacity`) and as the amount of `Color.lerp`, which mixes
// two roles into a third nobody named. Giving the number a name in the same
// file does not help: `alpha: _wash` with `const double _wash = .06` reads as
// `.06`. A name from another file is out of reach of a per-file scan; review
// catches it. Zero and full opacity stay, because they are not a colour
// decision: `withValues(alpha: 0)` is the role at nothing, which is what a
// cross-fade starts from. The mechanism is the
// geometry gate's: a per-file count that may go down, never up, and a file at
// zero leaves the map. It reads the application's `lib/`; the package's
// foundation is where a role and its opacity are defined (`selection` at
// `selectionOpacity`, `stateLayer` at `hoverOpacity`).

import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';

/// Per-file counts on 2026-10-17, when the gate was written. Shrink only.
///
/// Two: the wash under the selected destination in the shell's rail, and the
/// shade the capture screen paints outside the crop.
const Map<String, int> alphaLiteralBacklog = <String, int>{
  'lib/src/app/shell.dart': 1,
  'lib/src/capture/capture_screen.dart': 1,
};

final RegExp _withValues = RegExp(r'\.withValues\s*\(');
final RegExp _alphaArgument = RegExp(r'\balpha\s*:');
final RegExp _withOpacity = RegExp(r'\.withOpacity\s*\(');
final RegExp _withAlpha = RegExp(r'\.withAlpha\s*\(');
final RegExp _stateLayer = RegExp(r'\.stateLayer\s*\(');
final RegExp _opacityArgument = RegExp(r'\bopacity\s*:');
final RegExp _lerp = RegExp(r'\bColor\.lerp\s*\(');
final RegExp _bareName = RegExp(
  r'^\s*(?:[A-Za-z_$][\w$]*\.)?([A-Za-z_$][\w$]*)\s*$',
);

/// Every opacity in [source] written as a number other than none or full, as
/// `line N, <call> <value>`.
List<String> alphaLiteralsIn(String source) {
  final String code = maskProse(source);
  final List<String> found = <String>[];

  void check(int start, int end, String call, Set<num> allowed) {
    final String expression = code.substring(start, end);
    for (final RegExpMatch literal in numericLiteral.allMatches(expression)) {
      final String text = literal.group(0)!;
      if (allowed.contains(num.parse(text))) continue;
      found.add('line ${lineOf(source, start)}, $call $text');
      return;
    }
    // A name for the number, declared in this file.
    final String? name = _bareName.firstMatch(expression)?.group(1);
    if (name == null) return;
    final RegExpMatch? declared = RegExp(
      '\\b(?:const|final)\\s+(?:(?:double|num|int)\\s+)?'
      '${RegExp.escape(name)}\\s*=\\s*(${numericLiteral.pattern})\\s*[;,]',
    ).firstMatch(code);
    if (declared == null) return;
    final String text = declared.group(1)!;
    if (!allowed.contains(num.parse(text))) {
      found.add('line ${lineOf(source, start)}, $call $name = $text');
    }
  }

  for (final RegExpMatch call in _withValues.allMatches(code)) {
    final int close = endOfBracket(code, call.end - 1);
    final String arguments = code.substring(call.end, close);
    for (final RegExpMatch alpha in _alphaArgument.allMatches(arguments)) {
      final int start = call.end + alpha.end;
      check(start, endOfExpression(code, start), 'alpha:', <num>{0, 1});
    }
  }
  for (final RegExpMatch call in _withOpacity.allMatches(code)) {
    check(call.end, endOfExpression(code, call.end), 'withOpacity', <num>{
      0,
      1,
    });
  }
  for (final RegExpMatch call in _stateLayer.allMatches(code)) {
    check(call.end, endOfExpression(code, call.end), 'stateLayer', <num>{0, 1});
  }
  for (final RegExpMatch argument in _opacityArgument.allMatches(code)) {
    check(argument.end, endOfExpression(code, argument.end), 'opacity:', <num>{
      0,
      1,
    });
  }
  for (final RegExpMatch call in _lerp.allMatches(code)) {
    // The third argument is the amount.
    int from = call.end;
    for (int argument = 0; argument < 2 && from < code.length; argument++) {
      from = endOfExpression(code, from) + 1;
    }
    check(from, endOfExpression(code, from), 'Color.lerp', <num>{0, 1});
  }
  for (final RegExpMatch call in _withAlpha.allMatches(code)) {
    check(call.end, endOfExpression(code, call.end), 'withAlpha', <num>{
      0,
      255,
    });
  }
  return found;
}

/// Every file under `lib/` of the application at [base] that writes an
/// opacity as a number, with its findings.
Map<String, List<String>> alphaLiteralCensus({String base = '.'}) {
  final Map<String, List<String>> found = <String, List<String>>{};
  for (final GateSource source in libSources(base: base)) {
    if (generatedFile.hasMatch(source.path)) continue;
    final List<String> findings = alphaLiteralsIn(source.text);
    if (findings.isNotEmpty) found[source.path] = findings;
  }
  return found;
}

/// What the gate objects to in [census]: a file not in the backlog, or one
/// that holds more than its count.
List<String> alphaLiteralViolations(Map<String, List<String>> census) {
  final List<String> found = <String>[];
  census.forEach((String path, List<String> findings) {
    final int allowed = alphaLiteralBacklog[path] ?? 0;
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
  test('the scanner reads an opacity the way a reviewer would', () {
    expect(alphaLiteralsIn('ui.color.ink.withValues(alpha: .06)'), <String>[
      'line 1, alpha: .06',
    ]);
    expect(alphaLiteralsIn('c.withValues(alpha: 0.58)'), <String>[
      'line 1, alpha: 0.58',
    ]);
    expect(alphaLiteralsIn('c.withValues(red: r, alpha: t * 0.5)'), <String>[
      'line 1, alpha: 0.5',
    ]);
    expect(alphaLiteralsIn('c.withOpacity(0.4)'), <String>[
      'line 1, withOpacity 0.4',
    ]);
    expect(alphaLiteralsIn('c.withAlpha(20)'), <String>[
      'line 1, withAlpha 20',
    ]);
    expect(alphaLiteralsIn('ui.color.stateLayer(.06)'), <String>[
      'line 1, stateLayer .06',
    ]);
    expect(
      alphaLiteralsIn('Opacity(opacity: .06, child: ColoredBox(color: ink))'),
      <String>['line 1, opacity: .06'],
    );
    expect(alphaLiteralsIn('Color.lerp(ui.color.ground, ink, 0.06)!'), <String>[
      'line 1, Color.lerp 0.06',
    ]);
    expect(alphaLiteralsIn('c.withAlpha(0x14)'), <String>[
      'line 1, withAlpha 0x14',
    ]);

    // A name for the number in the same file is the number.
    expect(
      alphaLiteralsIn(
        'static const double _wash = .06;\n'
        'Color w() => ink.withValues(alpha: _wash);',
      ),
      <String>['line 2, alpha: _wash = .06'],
    );
    expect(
      alphaLiteralsIn(
        'class _S { static const double wash = .06; }\n'
        'Color w() => ink.withValues(alpha: _S.wash);',
      ),
      <String>['line 2, alpha: wash = .06'],
    );
    expect(alphaLiteralsIn('a;\nc.withValues(\n  alpha: .1,\n)'), <String>[
      'line 3, alpha: .1',
    ]);

    // None and full, a token, another channel and prose are not opacities.
    expect(alphaLiteralsIn('c.withValues(alpha: 0)'), isEmpty);
    expect(alphaLiteralsIn('c.withValues(alpha: 1.0)'), isEmpty);
    expect(alphaLiteralsIn('c.withAlpha(255)'), isEmpty);
    expect(
      alphaLiteralsIn('ui.color.stateLayer(ui.color.hoverOpacity)'),
      isEmpty,
    );
    expect(
      alphaLiteralsIn('Color.lerp(a, b, animation.value)'),
      isEmpty,
      reason: 'an amount that comes from an animation is not a colour',
    );
    expect(alphaLiteralsIn('Opacity(opacity: visible ? 1 : 0)'), isEmpty);
    expect(
      alphaLiteralsIn('c.withValues(alpha: GroundPalette.scrimOpacity)'),
      isEmpty,
      reason: 'a token declared in the package is not in this file',
    );
    expect(alphaLiteralsIn('c.withValues(red: 0.5)'), isEmpty);
    expect(alphaLiteralsIn('// was ink.withValues(alpha: .06)'), isEmpty);
  });

  test('a planted opacity fails the gate', () {
    // The same census and verdict the gate runs, over a temporary
    // application: a new file with a typed opacity, and a backlog file that
    // gained a second one.
    final String base = plantedApplication(<String, String>{
      'lib/src/widgets/hover.dart':
          'Color wash(UiThemeData ui) => ui.color.ink.withValues(alpha: .08);\n',
      'lib/src/app/shell.dart':
          'final Color a = ink.withValues(alpha: .06);\n'
          'final Color b = ink.withOpacity(.12);\n',
    });
    expect(alphaLiteralViolations(alphaLiteralCensus(base: base)), <String>[
      'lib/src/app/shell.dart holds 2, allowed 1:\n'
          '    line 1, alpha: .06\n'
          '    line 2, withOpacity .12',
      'lib/src/widgets/hover.dart holds 1, allowed 0:\n'
          '    line 1, alpha: .08',
    ]);
  });

  test('no file gained an opacity literal', () {
    final List<String> violations = alphaLiteralViolations(
      alphaLiteralCensus(),
    );
    expect(
      violations,
      isEmpty,
      reason:
          'an opacity typed over a role is a colour no role names. Read it '
          'from a specimen_ui role, such as ui.color.selection, or pass a '
          'named opacity, such as ui.color.stateLayer(ui.color.hoverOpacity):\n'
          '${violations.join('\n')}',
    );
  });

  test('the backlog matches the tree exactly', () {
    final Map<String, List<String>> census = alphaLiteralCensus();
    alphaLiteralBacklog.forEach((String path, int allowed) {
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
