// The Material component gate (10 section 8, `no_material_components`).
//
// Every widget in the retired list of 10 section 1.3 is counted per file. The
// map may only shrink: a screen agent that replaces `FilledButton` with
// `UiButton` lowers its file's number, and a change that adds one fails.
//
// The list is 1.3's, widened to the variants 1.3 retires by implication and
// that the build plan's census counts: the `*ListTile` forms, the chip
// family, `TextField` and `TextFormField` (retired at call sites by 10
// section 4.2), `Dialog` and `NavigationDrawer`.
//
// Measured against build plan appendix B at the cut point: appendix B totals
// 203 and this gate totals 208. The difference is exactly five, one per
// `ScaffoldMessenger.of(context).showSnackBar(SnackBar(...))` site. Appendix B
// counted each of those as one Material use; this gate counts the messenger
// and the bar separately, because the brief for wave 0 names `ScaffoldMessenger`
// as its own term in the regex. The five sites were in `queue_screen.dart`,
// `source_screen.dart`, `evidence_drawer.dart` and `workbench.dart` (twice);
// the queue's is now a `UiToast`. Every one of the 208 is gone.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The widgets 10 section 1.3 retires, plus the variants it retires with them.
const List<String> retiredWidgets = <String>[
  'Scaffold',
  'AppBar',
  'Card',
  'ListTile',
  'Chip',
  'InputChip',
  'FilterChip',
  'ActionChip',
  'ChoiceChip',
  'FilledButton',
  'OutlinedButton',
  'TextButton',
  'IconButton',
  'NavigationBar',
  'NavigationRail',
  'NavigationDrawer',
  'Drawer',
  'ExpansionTile',
  'SegmentedButton',
  'Switch',
  'SwitchListTile',
  'Checkbox',
  'CheckboxListTile',
  'Radio',
  'RadioListTile',
  'DropdownMenu',
  'DropdownButton',
  'MenuAnchor',
  'PopupMenuButton',
  'SnackBar',
  'AlertDialog',
  'Dialog',
  'Tooltip',
  'Divider',
  'InkWell',
  'Material',
  'LinearProgressIndicator',
  'CircularProgressIndicator',
  'Badge',
  'TabBar',
  'TextField',
  'TextFormField',
];

/// The three terms that are not a constructor call.
final RegExp _extraTerms = RegExp(
  r'\b(showDialog|showModalBottomSheet)\(|\bScaffoldMessenger\b',
);

final RegExp _constructors = RegExp(
  '\\b(${(retiredWidgets.toList()..sort((String a, String b) => b.length.compareTo(a.length))).join('|')})\\(',
);

/// Per-file counts at the start of the refactor. Shrink only.
///
/// Empty since the cleanup slot, which took the last entry: the transparent
/// `Scaffold` in `app_router.dart` that stood over the collection subtree
/// while its screens still needed a `Material` ancestor and a messenger. The
/// gate now allows nothing, so any of the 42 widgets above, anywhere under
/// `lib/`, fails it.
///
/// `lib/src/theme/` was out of scope while it was the adapter layer that
/// configured those widgets. It is scanned now: the six adapter files are
/// gone and the bridge that is left builds no component at all.
const Map<String, int> componentBacklog = <String, int>{};

/// Counts the retired widgets in [source], ignoring line comments so a
/// comment naming a widget does not read as a use of it.
int countIn(String source) {
  final String code = source.replaceAll(RegExp(r'//.*'), '');
  return _constructors.allMatches(code).length +
      _extraTerms.allMatches(code).length;
}

/// The files this gate scans.
Map<String, int> measure() {
  final Directory root = Directory('lib');
  expect(root.existsSync(), isTrue, reason: 'run this from the app root');
  final Map<String, int> found = <String, int>{};
  for (final FileSystemEntity entity in root.listSync(recursive: true)) {
    if (entity is! File || !entity.path.endsWith('.dart')) continue;
    final int count = countIn(entity.readAsStringSync());
    if (count > 0) found[entity.path] = count;
  }
  return found;
}

void main() {
  test('no file gained a Material component', () {
    final Map<String, int> found = measure();

    final Iterable<String> unexpected = found.keys.where(
      (String path) => !componentBacklog.containsKey(path),
    );
    expect(
      unexpected,
      isEmpty,
      reason:
          'these files use a retired Material component and are not in the '
          'backlog: ${unexpected.join(', ')}',
    );

    for (final MapEntry<String, int> entry in found.entries) {
      expect(
        entry.value,
        lessThanOrEqualTo(componentBacklog[entry.key]!),
        reason:
            '${entry.key} went from ${componentBacklog[entry.key]} to '
            '${entry.value}. The backlog may only shrink.',
      );
    }
  });

  test('the backlog only lists files that still hold one', () {
    final Map<String, int> found = measure();
    for (final String path in componentBacklog.keys) {
      expect(
        File(path).existsSync(),
        isTrue,
        reason: '$path is in the backlog but does not exist',
      );
      expect(
        found.containsKey(path),
        isTrue,
        reason: '$path is clean now, so remove it from the backlog',
      );
    }
  });
}
