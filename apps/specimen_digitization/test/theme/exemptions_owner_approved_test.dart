// The sign-off gate (10 section 8, `exemptions_owner_approved`).
//
// Every source gate here has a way to let something through: an allow-list, an
// exemption, a backlog count, an allowed value or an exempt path. Each one lets
// a hardcoded value, a stock component or a platform fork into the product,
// which is what the owner objected to on 2026-10-17 ("i hope we arent
// duplicating and hand-codring hardcoding"), so adding one is the owner's
// decision and not an agent's. An allowance written after this gate needs the
// owner's sign-off, recorded on the entry itself:
//
//     // owner-approved: 2026-10-17 "the owner's exact words"
//
// on the comment lines directly above the entry, or after the entry on its own
// line. The date
// must be a real day that has happened; the words are a quotation, in straight
// double quotes, never a paraphrase. A coordinator's or a reviewer's OK is not
// the owner's.
//
// The entries on each list when the gate was written are recorded below and
// need no annotation. That record only shrinks: an entry that leaves its list
// leaves the record, so bringing it back is new and needs a sign-off. A backlog
// count may fall freely and may not rise above its recorded count unsigned.
//
// The gate reads the lists from source, because a comment is not a value.
// Three self-checks keep that reading honest: its comment reader must read
// every file the way `maskProse` does, it must see the entries the compiler
// sees, and every public constant in a gate file must be either an allowance
// this test checks or named below as something that is not one.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';
import 'icons_unique_test.dart' as icons;
import 'no_alpha_literals_test.dart' as alpha;
import 'no_color_literals_test.dart' as colors;
import 'no_cupertino_test.dart' as cupertino;
import 'no_literal_geometry_test.dart' as geometry;
import 'no_material_components_test.dart' as components;
import 'no_material_imports_test.dart' as imports;
import 'no_named_pixels_test.dart' as pixels;
import 'no_platform_branching_test.dart' as platform;

/// How an allowance's entries are compared with the record.
enum Grant {
  /// A list or set of paths or values, or a map from a path to its reason:
  /// an entry is its first string, or its number.
  keys,

  /// A map from a path to what it may use: an entry is the path and the
  /// value.
  keyAndValue,

  /// A list of objects: an entry is its path and the first set it carries.
  keyAndSet,

  /// A backlog of path to count: a new path, or a count above the record.
  counts,

  /// One value, a path or a pattern: the initializer as written.
  scalar,
}

/// An allowance this gate checks: a declaration in a gate file.
class Allowance {
  /// Names [declaration] in [file], compared by [grant], with [compiled] the
  /// entries the compiler sees for a collection the test can import.
  const Allowance(this.file, this.declaration, this.grant, [this.compiled]);

  /// The gate file, relative to the application root.
  final String file;

  /// The constant's name.
  final String declaration;

  /// How its entries are compared.
  final Grant grant;

  /// The entries as the compiler sees them, by key.
  final Iterable<String> Function()? compiled;

  /// The key the record and the reports use.
  String get id => '$file $declaration';
}

const String _theme = 'test/theme';
const String _packageGeometry =
    'packages/specimen_ui/test/gates/no_literal_geometry_test.dart';

/// Every allowance in the source gates.
final List<Allowance> allowances = <Allowance>[
  Allowance(
    '$_theme/icons_unique_test.dart',
    'glyphBacklog',
    Grant.counts,
    () => icons.glyphBacklog.keys,
  ),
  Allowance(
    '$_theme/no_alpha_literals_test.dart',
    'alphaLiteralBacklog',
    Grant.counts,
    () => alpha.alphaLiteralBacklog.keys,
  ),
  const Allowance(
    '$_theme/no_color_literals_test.dart',
    'paletteFile',
    Grant.scalar,
  ),
  Allowance(
    '$_theme/no_color_literals_test.dart',
    'migrationBacklog',
    Grant.counts,
    () => colors.migrationBacklog.keys,
  ),
  Allowance(
    '$_theme/no_cupertino_test.dart',
    'cupertinoExemptions',
    Grant.keyAndValue,
    () => cupertino.cupertinoExemptions.keys,
  ),
  Allowance(
    '$_theme/no_literal_geometry_test.dart',
    'allowedValues',
    Grant.keys,
    () => geometry.allowedValues.map((num v) => '$v'),
  ),
  const Allowance(
    '$_theme/no_literal_geometry_test.dart',
    'generatedFile',
    Grant.scalar,
  ),
  const Allowance(
    '$_theme/no_literal_geometry_test.dart',
    'modelsPrefix',
    Grant.scalar,
  ),
  Allowance(
    '$_theme/no_literal_geometry_test.dart',
    'geometryBacklog',
    Grant.counts,
    () => geometry.geometryBacklog.keys,
  ),
  Allowance(
    '$_theme/no_material_components_test.dart',
    'componentBacklog',
    Grant.counts,
    () => components.componentBacklog.keys,
  ),
  Allowance(
    '$_theme/no_material_imports_test.dart',
    'infrastructureImporters',
    Grant.keys,
    () => imports.infrastructureImporters.keys,
  ),
  Allowance(
    '$_theme/no_material_imports_test.dart',
    'packageMaterialFiles',
    Grant.keys,
    () => imports.packageMaterialFiles,
  ),
  Allowance(
    '$_theme/no_material_imports_test.dart',
    'importBacklog',
    Grant.keys,
    () => imports.importBacklog,
  ),
  Allowance(
    '$_theme/no_named_pixels_test.dart',
    'namedPixelBacklog',
    Grant.counts,
    () => pixels.namedPixelBacklog.keys,
  ),
  Allowance(
    '$_theme/no_platform_branching_test.dart',
    'platformCapabilities',
    Grant.keyAndSet,
    () => platform.platformCapabilities.map(
      (platform.PlatformCapability c) => c.path,
    ),
  ),
  const Allowance(
    '$_theme/no_platform_branching_test.dart',
    'generatedOptions',
    Grant.scalar,
  ),
  const Allowance('$_theme/contrast_test.dart', 'textMinimum', Grant.scalar),
  const Allowance('$_theme/contrast_test.dart', 'nonTextMinimum', Grant.scalar),
  const Allowance(_packageGeometry, 'allowedValues', Grant.keys),
  const Allowance(_packageGeometry, 'foundationFile', Grant.scalar),
  const Allowance(_packageGeometry, 'galleryPrefix', Grant.scalar),
  const Allowance(_packageGeometry, 'generatedFile', Grant.scalar),
  const Allowance(_packageGeometry, 'waveFHandoff', Grant.counts),
];

/// The public constants in the gate files that let nothing through, and why.
const Map<String, String> notAllowances = <String, String>{
  '$_theme/dark_mode_test.dart themes':
      'the themes under test, not a permission',
  '$_theme/gate_support.dart numericLiteral': 'the pattern a number is read by',
  '$_theme/no_cupertino_test.dart cupertinoLibrary':
      'the name a finding reports',
  '$_theme/no_dashes_test.dart emDash': 'a banned character',
  '$_theme/no_dashes_test.dart enDash': 'a banned character',
  '$_theme/no_literal_geometry_test.dart argumentRules':
      'the rules the gate applies; an entry tightens it',
  '$_theme/no_literal_geometry_test.dart callRules':
      'the rules the gate applies; an entry tightens it',
  '$_theme/no_material_components_test.dart retiredWidgets':
      'the ban list; an entry tightens it',
  '$_theme/no_platform_branching_test.dart ioPlatform':
      'the name a finding reports',
  '$_theme/no_platform_branching_test.dart platformOverride':
      'the name a finding reports',
  '$_theme/no_platform_branching_test.dart targetPlatform':
      'the name a finding reports',
  '$_theme/no_platform_branching_test.dart targetPlatformValue':
      'the name a finding reports',
  '$_theme/no_platform_branching_test.dart webFlag':
      'the name a finding reports',
  '$_packageGeometry argumentRules':
      'the rules the gate applies; an entry tightens it',
  '$_packageGeometry callRules':
      'the rules the gate applies; an entry tightens it',
};

/// The entries on each allowance when this gate was written, 2026-10-17.
/// Shrink only.
const Map<String, Set<String>> recordedGrants = <String, Set<String>>{
  '$_theme/no_alpha_literals_test.dart alphaLiteralBacklog': <String>{
    'lib/src/app/shell.dart = 1',
    'lib/src/capture/capture_screen.dart = 1',
  },
  '$_theme/no_color_literals_test.dart paletteFile': <String>{
    r"'packages/specimen_ui/lib/src/foundation/palette.dart'",
  },
  '$_theme/no_cupertino_test.dart cupertinoExemptions': <String>{
    'lib/src/app/app_router.dart -> CupertinoRouteTransitionMixin',
  },
  '$_theme/no_literal_geometry_test.dart allowedValues': <String>{
    '0',
    '1',
    '2',
  },
  '$_theme/no_literal_geometry_test.dart generatedFile': <String>{
    r"RegExp(r'(?:^|/)(?:[^/]*\.g\.dart|firebase_options[^/]*\.dart)$')",
  },
  '$_theme/no_literal_geometry_test.dart modelsPrefix': <String>{
    r"'lib/src/models'",
  },
  '$_theme/no_literal_geometry_test.dart geometryBacklog': <String>{
    'lib/src/api_repository.dart = 1',
    'lib/src/magic_link.dart = 1',
    'lib/src/workspace.dart = 2',
  },
  '$_theme/no_material_imports_test.dart infrastructureImporters': <String>{
    'lib/main.dart',
    'lib/src/theme/app_theme.dart',
    'lib/src/capture/capture_screen.dart',
  },
  '$_theme/no_material_imports_test.dart packageMaterialFiles': <String>{
    'packages/specimen_ui/lib/src/primitives/field_core.dart',
    'packages/specimen_ui/lib/src/foundation/theme.dart',
    'packages/specimen_ui/lib/src/controls/overlays/tooltip.dart',
  },
  '$_theme/no_named_pixels_test.dart namedPixelBacklog': <String>{
    'lib/src/app/auth_layout.dart = 1',
    'lib/src/app/shell.dart = 1',
    'lib/src/capture/capture_screen.dart = 1',
    'lib/src/large_record.dart = 1',
    'lib/src/region_editor.dart = 2',
    'lib/src/screens/queue/queue_screen.dart = 3',
    'lib/src/screens/sources/source_screen.dart = 1',
    'lib/src/screens/workbench/readings_panel.dart = 1',
    'lib/src/screens/workbench/source_pane.dart = 2',
    'lib/src/screens/workbench/workbench_layout.dart = 6',
    'lib/src/widgets/adaptive_form.dart = 3',
    'lib/src/widgets/motion_reveal.dart = 1',
    'lib/src/widgets/queue_row.dart = 1',
    'lib/src/widgets/upload_item.dart = 1',
  },
  '$_theme/no_platform_branching_test.dart platformCapabilities': <String>{
    'lib/firebase_options.ci.dart {targetPlatform, targetPlatformValue, webFlag}',
    'lib/main.dart {webFlag}',
    'lib/src/app/app_router.dart {targetPlatform, targetPlatformValue}',
    'lib/src/auth.dart {targetPlatform, targetPlatformValue, webFlag}',
    'lib/src/capture/capture_camera.dart {webFlag}',
    'lib/src/email_link_source_factory_io.dart {ioPlatform}',
    'lib/src/intake.dart {targetPlatform, targetPlatformValue, webFlag}',
    'lib/src/magic_link_screen.dart {targetPlatform, targetPlatformValue, webFlag}',
    'lib/src/screens/queue/queue_screen.dart {targetPlatform, targetPlatformValue, webFlag}',
    'lib/src/screens/workbench/readings_panel.dart {webFlag}',
    'lib/src/theme/app_theme.dart {targetPlatformValue}',
    'lib/src/theme/motion.dart {targetPlatform, targetPlatformValue, webFlag}',
  },
  '$_theme/no_platform_branching_test.dart generatedOptions': <String>{
    r"'lib/firebase_options.dart'",
  },
  '$_theme/contrast_test.dart textMinimum': <String>{'4.5'},
  '$_theme/contrast_test.dart nonTextMinimum': <String>{'3.0'},
  '$_packageGeometry allowedValues': <String>{'0', '1', '2'},
  '$_packageGeometry foundationFile': <String>{
    r"RegExp(r'^lib/src/foundation/[^/]+\.dart$')",
  },
  '$_packageGeometry galleryPrefix': <String>{r"'lib/src/gallery/'"},
  '$_packageGeometry generatedFile': <String>{
    r"RegExp(r'(?:^|/)[^/]*\.g\.dart$')",
  },
};

// ---------------------------------------------------------------------------
// Reading an allowance from source.
// ---------------------------------------------------------------------------

/// One entry of an allowance as written: what it grants, the count when it is
/// a backlog's, and the comments attached to it.
class Entry {
  /// Records an entry's [grant], its backlog [count] and its [comments].
  const Entry(this.grant, this.count, this.comments);

  /// What it grants, as the record writes it.
  final String grant;

  /// The count, for a backlog entry.
  final int? count;

  /// The text of every comment attached to it.
  final String comments;
}

bool _blank(String c) => c == ' ' || c == '\n' || c == '\t' || c == '\r';

String _stringValue(String source, ProseSpan span) {
  final String text = source.substring(span.start, span.end);
  final int quotes = text.length >= 6 && text.startsWith(text[0] * 3) ? 3 : 1;
  return text.substring(quotes, text.length - quotes);
}

/// The comments attached to the code from [start] to [end]: the whole-line
/// comments directly above its first line, and any comment that starts on its
/// lines, which takes in one after its comma.
String _attached(String source, List<ProseSpan> spans, int start, int end) {
  final List<ProseSpan> comments = <ProseSpan>[
    for (final ProseSpan s in spans)
      if (s.comment) s,
  ];
  final List<String> found = <String>[];
  int lineStart = source.lastIndexOf('\n', start - 1) + 1;
  while (lineStart > 0) {
    final int above = lineStart >= 2
        ? source.lastIndexOf('\n', lineStart - 2) + 1
        : 0;
    int first = above;
    while (first < lineStart - 1 && _blank(source[first])) {
      first++;
    }
    final ProseSpan? comment = comments
        .where((ProseSpan s) => s.start == first)
        .firstOrNull;
    if (comment == null) break;
    found.add(source.substring(comment.start, comment.end));
    lineStart = above;
  }
  int lineEnd = source.indexOf('\n', end);
  if (lineEnd < 0) lineEnd = source.length;
  for (final ProseSpan s in comments) {
    if (s.start >= start && s.start < lineEnd) {
      found.add(source.substring(s.start, s.end));
    }
  }
  return found.join('\n');
}

/// The first character from [from] to [to] that is neither a comment nor
/// white space: the start of an entry, which may be a string.
int _codeStart(String source, List<ProseSpan> spans, int from, int to) {
  int i = from;
  while (i < to) {
    final ProseSpan? comment = spans
        .where((ProseSpan s) => s.comment && s.start == i)
        .firstOrNull;
    if (comment != null) {
      i = comment.end;
    } else if (_blank(source[i])) {
      i++;
    } else {
      return i;
    }
  }
  return to;
}

int _statementEnd(String code, int start) {
  int depth = 0;
  for (int i = start; i < code.length; i++) {
    final String c = code[i];
    if (c == '(' || c == '[' || c == '{') depth++;
    if (c == ')' || c == ']' || c == '}') depth--;
    if (c == ';' && depth == 0) return i;
  }
  return code.length;
}

/// The entries of the top-level constant [name] in [source], read as [grant]
/// reads them, or null when [source] does not declare it.
List<Entry>? entriesOf(String source, String name, Grant grant) {
  final String code = maskProse(source);
  final List<ProseSpan> spans = proseSpans(source);
  final RegExpMatch? head = RegExp(
    '^(?:const|final)\\s[^=;]*\\b${RegExp.escape(name)}\\s*=(?!=)',
    multiLine: true,
  ).firstMatch(code);
  if (head == null) return null;
  final int end = _statementEnd(code, head.end);

  if (grant == Grant.scalar) {
    final StringBuffer value = StringBuffer();
    for (int i = head.end; i < end; i++) {
      final ProseSpan? inside = spans
          .where((ProseSpan s) => s.start <= i && i < s.end)
          .firstOrNull;
      if (inside != null && inside.comment) continue;
      if (inside == null && _blank(source[i])) continue;
      value.write(source[i]);
    }
    final String written = value.toString().replaceAll(
      RegExp(r',(?=[)\]}])'),
      '',
    );
    return <Entry>[
      Entry(written, null, _attached(source, spans, head.start, end)),
    ];
  }

  final int open = code.indexOf(RegExp(r'[\[{]'), head.end);
  final int close = endOfBracket(code, open) - 1;
  final List<Entry> entries = <Entry>[];
  int from = open + 1;
  while (from < close) {
    final int to = endOfExpression(code, from);
    final int start = _codeStart(source, spans, from, to);
    if (start < to) {
      entries.add(_entry(source, code, spans, start, to, grant));
    }
    from = to + 1;
  }
  return entries;
}

Entry _entry(
  String source,
  String code,
  List<ProseSpan> spans,
  int start,
  int end,
  Grant grant,
) {
  final List<ProseSpan> strings = <ProseSpan>[
    for (final ProseSpan s in spans)
      if (!s.comment && s.start >= start && s.start < end) s,
  ];
  final int colon = code.substring(start, end).indexOf(':');
  final String key;
  if (strings.isNotEmpty) {
    key = _stringValue(source, strings.first);
  } else {
    final RegExpMatch? number = numericLiteral.firstMatch(
      code.substring(start, end),
    );
    key = number?.group(0) ?? code.substring(start, end).trim();
  }
  final String comments = _attached(source, spans, start, end);
  switch (grant) {
    case Grant.counts:
      return Entry(
        key,
        int.parse(code.substring(start + colon + 1, end).trim()),
        comments,
      );
    case Grant.keyAndValue:
      return Entry(
        '$key -> ${_stringValue(source, strings[1])}',
        null,
        comments,
      );
    case Grant.keyAndSet:
      final int set = code.indexOf('{', start);
      final List<String> items =
          code
              .substring(set + 1, endOfBracket(code, set) - 1)
              .split(',')
              .map((String item) => item.trim())
              .where((String item) => item.isNotEmpty)
              .toList()
            ..sort();
      return Entry('$key {${items.join(', ')}}', null, comments);
    case Grant.keys:
    case Grant.scalar:
      return Entry(key, null, comments);
  }
}

// ---------------------------------------------------------------------------
// The rule.
// ---------------------------------------------------------------------------

final RegExp _approval = RegExp(
  r'owner-approved:\s*(\d{4})-(\d{2})-(\d{2})\s+"([^"]*[A-Za-z][^"]*)"',
);

/// Whether [comments] carry a sign-off dated on a real day no later than
/// [today].
bool ownerApproved(String comments, DateTime today) {
  for (final RegExpMatch m in _approval.allMatches(comments)) {
    final int year = int.parse(m.group(1)!);
    final int month = int.parse(m.group(2)!);
    final int day = int.parse(m.group(3)!);
    final DateTime date = DateTime(year, month, day);
    final bool real =
        date.year == year && date.month == month && date.day == day;
    if (real && !date.isAfter(today)) return true;
  }
  return false;
}

/// Every entry of [entries] that grants more than [recorded] did and carries
/// no sign-off.
List<String> unapproved(
  List<Entry> entries,
  Set<String> recorded,
  Grant grant,
  DateTime today,
) {
  final Map<String, int> recordedCounts = <String, int>{
    if (grant == Grant.counts)
      for (final String r in recorded)
        r.substring(0, r.lastIndexOf(' = ')): int.parse(
          r.substring(r.lastIndexOf(' = ') + 3),
        ),
  };
  final List<String> found = <String>[];
  for (final Entry entry in entries) {
    if (ownerApproved(entry.comments, today)) continue;
    if (grant == Grant.counts) {
      final int? before = recordedCounts[entry.grant];
      if (before == null) {
        found.add('${entry.grant} = ${entry.count} is a new backlog entry');
      } else if (entry.count! > before) {
        found.add(
          '${entry.grant} rose from $before to ${entry.count} in the backlog',
        );
      }
    } else if (!recorded.contains(entry.grant)) {
      found.add('${entry.grant} is a new allowance');
    }
  }
  return found;
}

/// The public top-level constants of [source].
List<String> publicConstants(String source) => <String>[
  for (final RegExpMatch m in RegExp(
    r'^(?:const|final)\s[^=;(]*?\b([a-zA-Z]\w*)\s*=(?!=)',
    multiLine: true,
  ).allMatches(maskProse(source)))
    m.group(1)!,
];

/// Every gate file, relative to the application root.
List<String> gateFiles() => <String>[
  for (final FileSystemEntity e in Directory(_theme).listSync())
    if (e is File &&
        e.path.endsWith('.dart') &&
        !e.path.endsWith('exemptions_owner_approved_test.dart'))
      e.path,
  _packageGeometry,
]..sort();

DateTime _today() {
  final DateTime now = DateTime.now();
  return DateTime(now.year, now.month, now.day);
}

void main() {
  final DateTime day = DateTime(2026, 10, 17);

  test('a planted allowance without a sign-off fails the gate', () {
    const String gate = '''
const Map<String, String> exemptions = <String, String>{
  'lib/old.dart': 'on the list before the rule',
  'lib/new.dart': 'added after it, unsigned',
};
''';
    expect(
      unapproved(
        entriesOf(gate, 'exemptions', Grant.keys)!,
        <String>{'lib/old.dart'},
        Grant.keys,
        day,
      ),
      <String>['lib/new.dart is a new allowance'],
    );
  });

  test('a sign-off clears it only when it is dated and quoted', () {
    List<String> withComment(String comment) => unapproved(
      entriesOf(
        '''
const Set<String> files = <String>{
  'lib/old.dart',
  $comment
  'lib/new.dart',
};
''',
        'files',
        Grant.keys,
      )!,
      <String>{'lib/old.dart'},
      Grant.keys,
      day,
    );
    const List<String> fails = <String>['lib/new.dart is a new allowance'];

    expect(
      withComment('// owner-approved: 2026-10-17 "yes, allow it"'),
      isEmpty,
    );
    expect(
      withComment(
        '// The tab bar needs it.\n'
        '  // owner-approved: 2026-10-16 "ok for the bar"',
      ),
      isEmpty,
    );
    expect(withComment('// owner-approved: "yes"'), fails, reason: 'no date');
    expect(withComment('// owner-approved: 2026-10-17'), fails);
    expect(withComment('// owner-approved: 2026-10-17 yes'), fails);
    expect(withComment('// owner-approved: 2026-10-17 ""'), fails);
    expect(withComment('// owner-approved: 2026-02-30 "yes"'), fails);
    expect(
      withComment('// owner-approved: 2026-10-18 "yes"'),
      fails,
      reason: 'a day that has not happened',
    );
    expect(withComment('// approved by the coordinator 2026-10-17'), fails);
  });

  test('a sign-off belongs to the entry it is written on', () {
    // After an entry's comma it is that entry's; it does not reach down to
    // the next one, and a code line between a comment and an entry cuts it.
    const String gate = '''
const List<String> files = <String>[
  'lib/a.dart', // owner-approved: 2026-10-17 "a only"
  'lib/b.dart',
  // owner-approved: 2026-10-17 "c only"
  'lib/c.dart',
  'lib/d.dart',
];
''';
    expect(
      unapproved(
        entriesOf(gate, 'files', Grant.keys)!,
        <String>{},
        Grant.keys,
        day,
      ),
      <String>[
        'lib/b.dart is a new allowance',
        'lib/d.dart is a new allowance',
      ],
    );
  });

  test('a backlog may fall freely and may not rise unsigned', () {
    const String gate = '''
const Map<String, int> backlog = <String, int>{
  'lib/fell.dart': 1,
  'lib/rose.dart': 4,
  'lib/new.dart': 1,
  'lib/signed.dart': 9, // owner-approved: 2026-10-17 "fine, for now"
};
''';
    expect(
      unapproved(
        entriesOf(gate, 'backlog', Grant.counts)!,
        <String>{
          'lib/fell.dart = 3',
          'lib/rose.dart = 2',
          'lib/signed.dart = 1',
        },
        Grant.counts,
        day,
      ),
      <String>[
        'lib/rose.dart rose from 2 to 4 in the backlog',
        'lib/new.dart = 1 is a new backlog entry',
      ],
    );
  });

  test('widening an entry or a path is a new allowance', () {
    const String capabilities = '''
const List<C> caps = <C>[
  C('lib/main.dart', <String>{webFlag, targetPlatform}, 'reason, '
      'reworded freely'),
];
''';
    expect(
      unapproved(
        entriesOf(capabilities, 'caps', Grant.keyAndSet)!,
        <String>{'lib/main.dart {webFlag}'},
        Grant.keyAndSet,
        day,
      ),
      <String>['lib/main.dart {targetPlatform, webFlag} is a new allowance'],
    );
    const String exemption = '''
const Map<String, String> ex = <String, String>{
  'lib/router.dart': 'CupertinoButton',
};
''';
    expect(
      unapproved(
        entriesOf(exemption, 'ex', Grant.keyAndValue)!,
        <String>{'lib/router.dart -> CupertinoRouteTransitionMixin'},
        Grant.keyAndValue,
        day,
      ),
      <String>['lib/router.dart -> CupertinoButton is a new allowance'],
    );
    const String prefix = '''
/// Wire types.
const String modelsPrefix =
    'lib/src';
''';
    expect(
      unapproved(
        entriesOf(prefix, 'modelsPrefix', Grant.scalar)!,
        <String>{"'lib/src/models'"},
        Grant.scalar,
        day,
      ),
      <String>["'lib/src' is a new allowance"],
    );
  });

  test('the comment reader reads every file the way maskProse does', () {
    // `proseSpans` is the second reader of the same grammar; blanking its
    // spans has to give the mask, character for character, on every file the
    // source gates and this one read.
    final List<String> paths = <String>[
      ...gateFiles(),
      for (final GateSource s in libSources()) s.path,
    ];
    for (final String path in paths) {
      final String source = File(path).readAsStringSync();
      final List<int> out = List<int>.of(source.codeUnits);
      for (final ProseSpan span in proseSpans(source)) {
        for (int i = span.start; i < span.end; i++) {
          if (out[i] != 0x0A) out[i] = 0x20;
        }
      }
      expect(String.fromCharCodes(out), maskProse(source), reason: path);
    }
  });

  test('the gate reads the entries the compiler sees', () {
    for (final Allowance allowance in allowances) {
      final List<Entry>? entries = entriesOf(
        File(allowance.file).readAsStringSync(),
        allowance.declaration,
        allowance.grant,
      );
      expect(entries, isNotNull, reason: '${allowance.id} is not declared');
      if (allowance.compiled == null) continue;
      expect(
        <String>{
          for (final Entry e in entries!)
            allowance.grant == Grant.keyAndValue
                ? e.grant.split(' -> ').first
                : allowance.grant == Grant.keyAndSet
                ? e.grant.split(' {').first
                : e.grant,
        },
        allowance.compiled!().toSet(),
        reason: allowance.id,
      );
    }
  });

  test('every public constant in a gate file is classified', () {
    final Set<String> known = <String>{
      for (final Allowance a in allowances) a.id,
      ...notAllowances.keys,
    };
    final List<String> unknown = <String>[
      for (final String file in gateFiles())
        for (final String name in publicConstants(
          File(file).readAsStringSync(),
        ))
          if (!known.contains('$file $name')) '$file $name',
    ];
    expect(
      unknown,
      isEmpty,
      reason:
          'an allowance goes in `allowances` so its entries need a sign-off; '
          'anything else goes in `notAllowances` with why it lets nothing '
          'through',
    );
  });

  test('no allowance grew without the owner signing it', () {
    final List<String> found = <String>[
      for (final Allowance allowance in allowances)
        for (final String problem in unapproved(
          entriesOf(
            File(allowance.file).readAsStringSync(),
            allowance.declaration,
            allowance.grant,
          )!,
          recordedGrants[allowance.id] ?? const <String>{},
          allowance.grant,
          _today(),
        ))
          '${allowance.id}: $problem',
    ];
    expect(
      found,
      isEmpty,
      reason:
          'fix the code instead, or ask the owner. An allowance needs '
          '`// owner-approved: YYYY-MM-DD "the owner\'s exact words"` on '
          'the entry (CLAUDE.md, "Gate exemptions"):\n${found.join('\n')}',
    );
  });

  test('the record only lists entries that are still granted', () {
    for (final Allowance allowance in allowances) {
      final Set<String> recorded =
          recordedGrants[allowance.id] ?? const <String>{};
      final List<Entry> entries = entriesOf(
        File(allowance.file).readAsStringSync(),
        allowance.declaration,
        allowance.grant,
      )!;
      final Set<String> live = <String>{for (final Entry e in entries) e.grant};
      for (final String r in recorded) {
        final String key = allowance.grant == Grant.counts
            ? r.substring(0, r.lastIndexOf(' = '))
            : r;
        expect(
          live.contains(key),
          isTrue,
          reason:
              '${allowance.id} no longer grants $r; remove it from '
              'recordedGrants, so bringing it back needs a sign-off',
        );
      }
    }
    expect(
      recordedGrants.keys.toSet().difference(<String>{
        for (final Allowance a in allowances) a.id,
      }),
      isEmpty,
      reason: 'the record names an allowance that is not checked',
    );
  });
}
