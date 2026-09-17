// The static geometry gate for the design system (10 section 8,
// `no_literal_geometry`), widened from the four patterns that row first named
// to every static size.
//
// The application's copy of this gate, at
// `apps/specimen_digitization/test/theme/no_literal_geometry_test.dart`, carries
// a per-file backlog because the screens still hold numbers wave 3 has not
// reached. The package carries none. A design system that writes a size as a
// number has nowhere left to put the token, and 11 section 0's diagnosis is
// that nobody owned the seam: a number in a control is a seam by itself.
//
// The scanner below is deliberately the same code as the application's. The two
// gates scan different trees, allow different paths and hold different
// policies, so they are two files; a change to how a file is read belongs in
// both.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

// ---------------------------------------------------------------------------
// Allowances. Each one is a named value, a named regex or a path. There is no
// per-line escape hatch: a number that genuinely has to be written down
// becomes a token in `lib/src/foundation/`, which is the first allowance.
// ---------------------------------------------------------------------------

/// The values a size may still be written as a digit.
///
/// Zero is the absence of a size. One is the hairline and two is the emphasis
/// stroke (09 section 5), which are tokens where they are drawn and bare
/// numbers where a `BorderSide` or a `Radius` takes them. Every other number is
/// a measurement, and a measurement belongs in the foundation.
const Set<num> allowedValues = <num>{0, 1, 2};

/// The foundation is where a token is defined, so it is where the number that
/// backs the token is written. `motion.dart` says the same of itself in its own
/// header: it is the one file in the product allowed to hold a duration.
final RegExp foundationFile = RegExp(r'^lib/src/foundation/[^/]+\.dart$');

/// The gallery documents a control at a set width, which is the one place a
/// width is the subject rather than a decision (10 section 6).
const String galleryPrefix = 'lib/src/gallery/';

/// Files nobody chose the numbers in.
final RegExp generatedFile = RegExp(r'(?:^|/)[^/]*\.g\.dart$');

/// Numbers inside the files wave F is rewriting as this gate lands.
///
/// 11 section 7 gives the overlay frames and `modal_routes.dart` to
/// `fe/fit-foundation`, which runs beside this slot, so editing them here would
/// collide with work already in flight. Five numbers, and every one of them
/// wants a name rather than a deletion:
///
/// - `toast.dart`, `UiToastStyle.showDuration`, six seconds, and `tooltip.dart`,
///   `UiTooltipStyle.hoverDelay` at 400 ms and `touchDuration` at 1500 ms. All
///   three are fixed by 10 section 4.3 and all three are already named where
///   they are written. `foundation/motion.dart` says it is the one file in the
///   product allowed to hold a duration literal, so the three belong beside the
///   motion tokens, as delays rather than as durations: `hoverDelay` in
///   particular must not be collapsed by the reduced-motion policy, which is
///   why it is not a motion token today.
/// - `modal_routes.dart`, the two entrance offsets a sheet and a dialog slide
///   through, 0.08 and 0.02 of the pane's height. They are fractions rather
///   than sizes, which is what 11 section 1 asks for, but they are unnamed:
///   `UiToastStyle.entranceRise` is the pattern to follow.
///
/// The integrator empties this map when wave F merges. Shrink only, like the
/// application's backlog.
const Map<String, int> waveFHandoff = <String, int>{
  'lib/src/controls/overlays/toast.dart': 1,
  'lib/src/controls/overlays/tooltip.dart': 2,
  'lib/src/primitives/modal_routes.dart': 2,
};

// ---------------------------------------------------------------------------
// The scanner. Every file is read once, masked once, and matched with compiled
// expressions, so the whole census runs in well under a second.
// ---------------------------------------------------------------------------

/// A numeric literal that is not part of an identifier, so `s4` and `space12`
/// read as the token names they are and `1.45` reads as one number.
const String _number =
    r'(?<![A-Za-z0-9_$.])(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)';

/// A call whose every argument is a number, so a digit anywhere inside it is a
/// static size. The expression matches the head; the scanner takes the call.
class CallRule {
  /// Names the rule for the census and matches its head.
  const CallRule(this.name, this.head);

  /// The name this rule reports under.
  final String name;

  /// Matches up to and including the call's opening parenthesis.
  final RegExp head;
}

/// An argument that carries a size directly, where the call around it also
/// takes children and colours and must not be read whole.
class ArgumentRule {
  /// Names the rule for the census and matches the argument with its value.
  const ArgumentRule(this.name, this.argument);

  /// The name this rule reports under.
  final String name;

  /// Matches the argument. Every group that parses as a number is a value.
  final RegExp argument;
}

/// Calls whose arguments are all numbers.
final List<CallRule> callRules = <CallRule>[
  CallRule('radius', RegExp(r'\b(?:BorderRadius|Radius)\.\w+\(')),
  CallRule('duration', RegExp(r'\bDuration\(')),
  CallRule('insets', RegExp(r'\bEdgeInsets(?:Directional)?(?:\.\w+)?\(')),
  CallRule('constraints', RegExp(r'\bBoxConstraints(?:\.\w+)?\(')),
  CallRule('point', RegExp(r'\b(?:Offset|Size)(?:\.\w+)?\(')),
];

/// An argument named one of [names] whose value is written as a number.
RegExp _valueOf(String names) => RegExp('\\b(?:$names)\\s*:\\s*($_number)');

/// Arguments that carry a size inside a call that carries other things too.
final List<ArgumentRule> argumentRules = <ArgumentRule>[
  ArgumentRule(
    'radius',
    RegExp(
      '\\b(?:Squircle|RSuperellipse|ClipRSuperellipse'
      '|RoundedSuperellipseBorder)(?:\\.\\w+)?\\(\\s*($_number)',
    ),
  ),
  ArgumentRule('radius', _valueOf('radius|borderRadius|cornerRadius')),
  ArgumentRule(
    'dimension',
    _valueOf('width|height|minWidth|maxWidth|minHeight|maxHeight|dimension'),
  ),
  ArgumentRule('type', _valueOf('fontSize|letterSpacing')),
];

final RegExp _numberPattern = RegExp(_number);
final RegExp _painterClass = RegExp(
  r'\bclass\s+\w+\s*(?:<[^>]*>)?\s*(?:extends|implements)\s+CustomPainter\b',
);
final RegExp _paintMethod = RegExp(r'\bvoid\s+paint\s*\(');

/// One number this gate objects to.
class Finding {
  /// Records the [rule] that claimed it, its 1-based [line] and its [text].
  const Finding(this.rule, this.line, this.text);

  /// The rule that claimed it.
  final String rule;

  /// The line it sits on, 1-based.
  final int line;

  /// The number as it is written.
  final String text;

  @override
  String toString() => 'line $line, $rule, $text';
}

bool _isIdentifierPart(int c) =>
    (c >= 0x30 && c <= 0x39) ||
    (c >= 0x41 && c <= 0x5A) ||
    (c >= 0x61 && c <= 0x7A) ||
    c == 0x5F ||
    c == 0x24;

int _endOfInterpolation(String source, int open) {
  int depth = 0;
  int i = open;
  while (i < source.length) {
    final int c = source.codeUnitAt(i);
    if (c == 0x7B) {
      depth++;
      i++;
    } else if (c == 0x7D) {
      depth--;
      i++;
      if (depth == 0) return i;
    } else if (c == 0x27 || c == 0x22) {
      i = _endOfString(source, i);
    } else {
      i++;
    }
  }
  return source.length;
}

int _endOfString(String source, int start) {
  final int n = source.length;
  final int quote = source.codeUnitAt(start);
  final bool raw =
      start > 0 &&
      source.codeUnitAt(start - 1) == 0x72 &&
      (start < 2 || !_isIdentifierPart(source.codeUnitAt(start - 2)));
  final bool triple =
      start + 2 < n &&
      source.codeUnitAt(start + 1) == quote &&
      source.codeUnitAt(start + 2) == quote;
  int i = start + (triple ? 3 : 1);
  while (i < n) {
    final int c = source.codeUnitAt(i);
    if (!raw && c == 0x5C) {
      i += 2;
      continue;
    }
    if (!raw && c == 0x24 && i + 1 < n && source.codeUnitAt(i + 1) == 0x7B) {
      i = _endOfInterpolation(source, i + 1);
      continue;
    }
    if (c == quote) {
      if (!triple) return i + 1;
      if (i + 2 < n &&
          source.codeUnitAt(i + 1) == quote &&
          source.codeUnitAt(i + 2) == quote) {
        return i + 3;
      }
    }
    if (!triple && c == 0x0A) return i;
    i++;
  }
  return n;
}

/// Replaces every comment and every string with spaces, keeping the length and
/// every newline, so prose never counts, a number inside a string is not a
/// size, and a finding's line number is the line in the file.
String maskProse(String source) {
  final List<int> out = List<int>.of(source.codeUnits);
  void blank(int from, int to) {
    for (int i = from; i < to && i < out.length; i++) {
      if (out[i] != 0x0A) out[i] = 0x20;
    }
  }

  final int n = source.length;
  int i = 0;
  while (i < n) {
    final int c = source.codeUnitAt(i);
    if (c == 0x2F && i + 1 < n) {
      final int next = source.codeUnitAt(i + 1);
      if (next == 0x2F) {
        int j = i;
        while (j < n && source.codeUnitAt(j) != 0x0A) {
          j++;
        }
        blank(i, j);
        i = j;
        continue;
      }
      if (next == 0x2A) {
        int depth = 1;
        int j = i + 2;
        while (j < n && depth > 0) {
          if (source.codeUnitAt(j) == 0x2F &&
              j + 1 < n &&
              source.codeUnitAt(j + 1) == 0x2A) {
            depth++;
            j += 2;
          } else if (source.codeUnitAt(j) == 0x2A &&
              j + 1 < n &&
              source.codeUnitAt(j + 1) == 0x2F) {
            depth--;
            j += 2;
          } else {
            j++;
          }
        }
        blank(i, j);
        i = j;
        continue;
      }
    }
    if (c == 0x27 || c == 0x22) {
      final int end = _endOfString(source, i);
      blank(i, end);
      i = end;
      continue;
    }
    i++;
  }
  return String.fromCharCodes(out);
}

int _endOfCall(String code, int openParen) {
  int depth = 0;
  for (int i = openParen; i < code.length; i++) {
    final int c = code.codeUnitAt(i);
    if (c == 0x28) {
      depth++;
    } else if (c == 0x29) {
      depth--;
      if (depth == 0) return i + 1;
    }
  }
  return code.length;
}

int _endOfBlock(String code, int openBrace) {
  int depth = 0;
  for (int i = openBrace; i < code.length; i++) {
    final int c = code.codeUnitAt(i);
    if (c == 0x7B) {
      depth++;
    } else if (c == 0x7D) {
      depth--;
      if (depth == 0) return i + 1;
    }
  }
  return code.length;
}

/// The character ranges of the `paint` methods of every `CustomPainter` in
/// [code].
///
/// Inside one, geometry is arithmetic on the `size` the canvas was given: a
/// number there is a fraction of a size rather than a size of its own. The
/// allowance is the method, not the class, so a painter's own fields and
/// constructor defaults are still counted.
List<List<int>> painterPaintBodies(String code) {
  final List<List<int>> spans = <List<int>>[];
  for (final RegExpMatch painter in _painterClass.allMatches(code)) {
    final int brace = code.indexOf('{', painter.end);
    if (brace < 0) continue;
    final int classEnd = _endOfBlock(code, brace);
    for (final RegExpMatch method in _paintMethod.allMatches(
      code.substring(brace, classEnd),
    )) {
      final int start = brace + method.start;
      final int signatureEnd = _endOfCall(code, brace + method.end - 1);
      final int body = code.indexOf('{', signatureEnd);
      final int arrow = code.indexOf('=>', signatureEnd);
      if (body >= 0 && (arrow < 0 || body < arrow)) {
        spans.add(<int>[start, _endOfBlock(code, body)]);
      } else if (arrow >= 0) {
        final int end = code.indexOf(';', arrow);
        spans.add(<int>[start, end < 0 ? code.length : end]);
      }
    }
  }
  return spans;
}

/// Whether the number at [start] to [end] is a list index, `bbox[3]`, rather
/// than a size. No size in this system is written inside brackets.
bool isSubscript(String code, int start, int end) {
  int before = start - 1;
  while (before >= 0 && code.codeUnitAt(before) == 0x20) {
    before--;
  }
  int after = end;
  while (after < code.length && code.codeUnitAt(after) == 0x20) {
    after++;
  }
  return before >= 0 &&
      code.codeUnitAt(before) == 0x5B &&
      after < code.length &&
      code.codeUnitAt(after) == 0x5D;
}

List<int> _lineStarts(String source) {
  final List<int> starts = <int>[0];
  for (int i = 0; i < source.length; i++) {
    if (source.codeUnitAt(i) == 0x0A) starts.add(i + 1);
  }
  return starts;
}

int _lineOf(List<int> starts, int offset) {
  int low = 0;
  int high = starts.length - 1;
  while (low < high) {
    final int mid = (low + high + 1) ~/ 2;
    if (starts[mid] <= offset) {
      low = mid;
    } else {
      high = mid - 1;
    }
  }
  return low + 1;
}

/// Every number in [source] that names a size no token names.
///
/// One number is one finding wherever it was found, so two rules that reach
/// the same digit do not count it twice and fixing one call clears every
/// finding that call carried.
List<Finding> findingsIn(String source) {
  final String code = maskProse(source);
  final List<List<int>> exempt = painterPaintBodies(code);
  final Map<int, Finding> claimed = <int, Finding>{};
  final List<int> starts = _lineStarts(source);

  void claim(int start, String text, String rule) {
    if (claimed.containsKey(start)) return;
    final num? value = num.tryParse(text);
    if (value != null && allowedValues.contains(value)) return;
    if (isSubscript(code, start, start + text.length)) return;
    for (final List<int> span in exempt) {
      if (start >= span[0] && start < span[1]) return;
    }
    claimed[start] = Finding(rule, _lineOf(starts, start), text);
  }

  for (final CallRule rule in callRules) {
    for (final RegExpMatch head in rule.head.allMatches(code)) {
      final int end = _endOfCall(code, head.end - 1);
      for (final RegExpMatch number in _numberPattern.allMatches(
        code.substring(head.end, end),
      )) {
        claim(head.end + number.start, number.group(0)!, rule.name);
      }
    }
  }
  for (final ArgumentRule rule in argumentRules) {
    for (final RegExpMatch match in rule.argument.allMatches(code)) {
      for (int group = 1; group <= match.groupCount; group++) {
        final String? value = match.group(group);
        if (value == null) continue;
        claim(code.indexOf(value, match.start), value, rule.name);
      }
    }
  }

  final List<int> offsets = claimed.keys.toList()..sort();
  return <Finding>[for (final int offset in offsets) claimed[offset]!];
}

/// Every Dart file this gate scans, by path relative to the package root.
List<String> scannedFiles() {
  final Directory root = Directory('lib');
  expect(
    root.existsSync(),
    isTrue,
    reason: 'run this test from the package root',
  );
  return <String>[
    for (final FileSystemEntity entity in root.listSync(recursive: true))
      if (entity is File &&
          entity.path.endsWith('.dart') &&
          !foundationFile.hasMatch(entity.path) &&
          !entity.path.startsWith(galleryPrefix) &&
          !generatedFile.hasMatch(entity.path))
        entity.path,
  ]..sort();
}

/// Every scanned file that still carries a static size, with its findings.
Map<String, List<Finding>> census() {
  final Map<String, List<Finding>> found = <String, List<Finding>>{};
  for (final String path in scannedFiles()) {
    final List<Finding> findings = findingsIn(File(path).readAsStringSync());
    if (findings.isNotEmpty) found[path] = findings;
  }
  return found;
}

void main() {
  test('the gate is looking at the package it thinks it is', () {
    final List<String> files = scannedFiles();
    expect(files, isNotEmpty);
    expect(
      files.where((String path) => path.startsWith('lib/src/controls/')),
      isNotEmpty,
      reason: 'the controls are the point of the gate',
    );
    expect(
      files.where(foundationFile.hasMatch),
      isEmpty,
      reason: 'the foundation is where the numbers are allowed to live',
    );
    expect(
      Directory('lib/src/foundation').listSync().whereType<File>(),
      isNotEmpty,
      reason: 'if the foundation moved, the allowance moved with it',
    );
  });

  test('the scanner reads a file the way a reviewer would', () {
    List<String> rulesOf(String source) =>
        findingsIn(source).map((Finding f) => f.rule).toList();

    // The patterns, one each.
    expect(rulesOf('BorderRadius.circular(12)'), <String>['radius']);
    expect(rulesOf('Squircle.border(12)'), <String>['radius']);
    expect(rulesOf('Squircle.clip(radius: 12, child: x)'), <String>['radius']);
    expect(rulesOf('Duration(milliseconds: 150)'), <String>['duration']);
    expect(rulesOf('EdgeInsetsDirectional.only(start: 12)'), <String>[
      'insets',
    ]);
    expect(rulesOf('SizedBox(width: 40)'), <String>['dimension']);
    expect(rulesOf('BoxConstraints(minWidth: 40)'), <String>['constraints']);
    expect(rulesOf('TextStyle(fontSize: 15, height: 1.45)'), <String>[
      'type',
      'dimension',
    ]);
    expect(rulesOf('Offset(4, 8)'), <String>['point', 'point']);

    // A token is not a number, whatever digits its name carries.
    expect(findingsIn('EdgeInsets.all(ui.space.s4)'), isEmpty);
    expect(findingsIn('SizedBox(height: space12)'), isEmpty);
    expect(findingsIn('BorderRadius.circular(ui.shape.field)'), isEmpty);

    // Zero, the hairline and the emphasis stroke stay bare.
    expect(findingsIn('EdgeInsets.all(0)'), isEmpty);
    expect(findingsIn('BorderSide(width: 1)'), isEmpty);
    expect(findingsIn('Offset(0, 2)'), isEmpty);
    expect(rulesOf('BorderSide(width: 1.5)'), <String>['dimension']);

    // Prose is not code.
    expect(findingsIn('// EdgeInsets.all(16) is what this replaced'), isEmpty);
    expect(
      findingsIn('/// Was `SizedBox(height: 24)` before the token.'),
      isEmpty,
    );
    expect(findingsIn('/* EdgeInsets.all(16) */'), isEmpty);
    expect(findingsIn("label('EdgeInsets.all(16)')"), isEmpty);

    // A string that holds a quote, an escape or an interpolation does not
    // shift everything after it out of phase.
    expect(rulesOf("x('it\\'s'); SizedBox(width: 40);"), <String>['dimension']);
    expect(rulesOf("x('\${m['k']}'); SizedBox(width: 40);"), <String>[
      'dimension',
    ]);
    expect(rulesOf("x(r'a\\'); SizedBox(width: 40);"), <String>['dimension']);
    expect(rulesOf("x('''a ' b'''); SizedBox(width: 40);"), <String>[
      'dimension',
    ]);

    // A list index is not a size.
    expect(findingsIn('Offset(box[2] / w, box[3] / h)'), isEmpty);

    // A painter's `paint` is arithmetic on the size it was handed; its fields
    // and its other methods are not.
    const String painter = '''
class P extends CustomPainter {
  final EdgeInsets inset = const EdgeInsets.all(12);
  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawCircle(Offset(24, 24), size.width / 3, brush);
  }
  EdgeInsets slop() => const EdgeInsets.all(33);
}
''';
    expect(findingsIn(painter).map((Finding f) => f.line), <int>[2, 7]);

    // The line number is the line in the file, not the line in some stripped
    // copy of it.
    expect(findingsIn('// a\n\n/* b\nc */\nEdgeInsets.all(16)').single.line, 5);
  });

  test('no control writes a size as a number', () {
    final Map<String, List<Finding>> found = census();

    final Iterable<String> unexpected = found.keys.where(
      (String path) => !waveFHandoff.containsKey(path),
    );
    expect(
      unexpected,
      isEmpty,
      reason:
          'a control that writes a size as a number is a decision no token '
          'records. Add the token to lib/src/foundation/ and read it from the '
          "control's style object (10 section 2 clause 11):\n"
          '${unexpected.map((String p) => '  $p: ${found[p]}').join('\n')}',
    );

    for (final MapEntry<String, List<Finding>> entry in found.entries) {
      expect(
        entry.value.length,
        lessThanOrEqualTo(waveFHandoff[entry.key]!),
        reason:
            '${entry.key} went from ${waveFHandoff[entry.key]} to '
            '${entry.value.length}. The handoff may only shrink.\n'
            '${entry.value.join('\n')}',
      );
    }
  });

  test('the handoff only lists files wave F still owes', () {
    final Map<String, List<Finding>> found = census();
    for (final String path in waveFHandoff.keys) {
      expect(
        File(path).existsSync(),
        isTrue,
        reason: '$path is in the handoff but does not exist',
      );
      expect(
        found.containsKey(path),
        isTrue,
        reason: '$path is clean now, so remove it from the handoff',
      );
    }
  });
}
