// The Cupertino gate (10 section 8, `no_cupertino`).
//
// 09 section 2 principle 5: behaviour adapts, identity does not. Type, colour,
// shape, icons, motion signature and component anatomy are ours on every
// platform, so no file under `lib/` draws a Cupertino component. The Material
// gates never read this library, and a `CupertinoTabBar` shipped on iOS through
// that gap, with tests asserting it, until `UiTabBar` replaced it on
// 2026-10-17 (10 section 4.4).
//
// Three ways in are counted, in code only (comments and strings are masked):
// an import or export of `package:flutter/cupertino.dart`; any identifier that
// starts with `Cupertino`, which also catches the Cupertino classes
// `material.dart` defines itself, such as `CupertinoPageTransitionsBuilder`;
// and Flutter's `.adaptive` constructors and `showAdaptiveDialog`, which draw a
// Cupertino component on Apple platforms under a Material name. The product's
// own `showAdaptiveModal` and `UiDialog.showAdaptive` adapt to the window, not
// the platform, and are not counted.

import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';

/// The files that may name a Cupertino class, and the one name each may use.
///
/// One file. 04 row 18 gives the phone push from the queue to the workbench
/// the platform page transition, and 09 section 2 principle 5 lists page
/// transitions with the behaviour that follows the platform. The router takes
/// `CupertinoRouteTransitionMixin` for that transition on iOS and nothing else
/// from the library; the test below holds it to the one name and a `show`
/// clause.
const Map<String, String> cupertinoExemptions = <String, String>{
  'lib/src/app/app_router.dart': 'CupertinoRouteTransitionMixin',
};

/// The library name a finding reports when a file imports or exports it.
const String cupertinoLibrary = 'package:flutter/cupertino.dart';

// Read from the unmasked source, since the URI is a string; anchored to the
// start of a line, so a commented out import is not a use.
final RegExp _libraryDirective = RegExp(
  r'''^\s*(?:import|export)\s+['"]package:flutter/cupertino\.dart['"]''',
  multiLine: true,
);
final RegExp _cupertinoName = RegExp(r'\bCupertino\w*');
final RegExp _adaptiveName = RegExp(r'\.adaptive\b|\bshowAdaptiveDialog\b');

/// Every Cupertino term in [source], in the order the three rules are listed.
List<String> cupertinoTermsIn(String source) {
  final String code = maskProse(source);
  return <String>[
    for (final RegExpMatch _ in _libraryDirective.allMatches(source))
      cupertinoLibrary,
    for (final RegExpMatch m in _cupertinoName.allMatches(code)) m.group(0)!,
    for (final RegExpMatch m in _adaptiveName.allMatches(code)) m.group(0)!,
  ];
}

/// Every file under `lib/` of the application at [base] that names a Cupertino
/// term, with the terms it names.
Map<String, List<String>> cupertinoCensus({String base = '.'}) {
  final Map<String, List<String>> found = <String, List<String>>{};
  for (final GateSource source in libSources(base: base)) {
    final List<String> terms = cupertinoTermsIn(source.text);
    if (terms.isNotEmpty) found[source.path] = terms;
  }
  return found;
}

/// What the gate objects to in [census]: a file with no exemption, or an
/// exempt file that names anything but its one class and the library it comes
/// from.
List<String> cupertinoViolations(Map<String, List<String>> census) {
  final List<String> found = <String>[];
  census.forEach((String path, List<String> terms) {
    final String? allowed = cupertinoExemptions[path];
    if (allowed == null) {
      found.add('$path: ${terms.join(', ')}');
      return;
    }
    for (final String term in terms) {
      if (term != allowed && term != cupertinoLibrary) {
        found.add('$path: $term, but only $allowed is exempt');
      }
    }
  });
  return found;
}

void main() {
  test('the scanner finds each way in and skips prose', () {
    expect(
      cupertinoTermsIn("import 'package:flutter/cupertino.dart';"),
      <String>[cupertinoLibrary],
    );
    expect(
      cupertinoTermsIn('import "package:flutter/cupertino.dart";'),
      <String>[cupertinoLibrary],
    );
    expect(
      cupertinoTermsIn("export 'package:flutter/cupertino.dart';"),
      <String>[cupertinoLibrary],
    );
    expect(cupertinoTermsIn('CupertinoTabBar(items: tabs)'), <String>[
      'CupertinoTabBar',
    ]);
    expect(
      cupertinoTermsIn('TargetPlatform.iOS: CupertinoPageTransitionsBuilder()'),
      <String>['CupertinoPageTransitionsBuilder'],
    );
    expect(cupertinoTermsIn('Switch.adaptive(value: on)'), <String>[
      '.adaptive',
    ]);
    expect(cupertinoTermsIn('showAdaptiveDialog(context: c)'), <String>[
      'showAdaptiveDialog',
    ]);

    // Prose, strings and the product's window-adaptive modals are not uses.
    expect(
      cupertinoTermsIn("// import 'package:flutter/cupertino.dart';"),
      <String>[],
    );
    expect(cupertinoTermsIn('/// Retires `CupertinoTabBar`.'), <String>[]);
    expect(cupertinoTermsIn("label('Cupertino')"), <String>[]);
    expect(cupertinoTermsIn('showAdaptiveModal<void>(context: c)'), <String>[]);
    expect(cupertinoTermsIn('UiDialog.showAdaptive<void>(c)'), <String>[]);
  });

  test('a planted Cupertino use fails the gate', () {
    // The same census and the same verdict the gate runs, over a temporary
    // application with one clean file, one violation per rule, and an exempt
    // router that reaches for a second Cupertino class.
    final String base = plantedApplication(<String, String>{
      'lib/src/clean.dart': "import 'package:flutter/widgets.dart';\n",
      'lib/src/tab_bar.dart':
          "import 'package:flutter/cupertino.dart';\n"
          'Widget bar() => CupertinoTabBar(items: tabs);\n',
      'lib/src/theme.dart':
          'const Object t = CupertinoPageTransitionsBuilder();\n',
      'lib/src/toggle.dart': 'Widget t() => Switch.adaptive(value: on);\n',
      'lib/src/app/app_router.dart':
          "import 'package:flutter/cupertino.dart' "
          'show CupertinoRouteTransitionMixin, CupertinoButton;\n',
    });
    final List<String> violations = cupertinoViolations(
      cupertinoCensus(base: base),
    );
    expect(violations, <String>[
      'lib/src/app/app_router.dart: CupertinoButton, but only '
          'CupertinoRouteTransitionMixin is exempt',
      'lib/src/tab_bar.dart: $cupertinoLibrary, CupertinoTabBar',
      'lib/src/theme.dart: CupertinoPageTransitionsBuilder',
      'lib/src/toggle.dart: .adaptive',
    ]);
  });

  test('no file under lib/ names a Cupertino component', () {
    final List<String> violations = cupertinoViolations(cupertinoCensus());
    expect(
      violations,
      isEmpty,
      reason:
          'the product draws its own components on every platform (09 '
          'section 2 principle 5). Use the specimen_ui control instead:\n'
          '${violations.join('\n')}',
    );
  });

  test('the iOS route takes one Cupertino name, through a show clause', () {
    // The exemption is a transition, not a licence for the library: a bare
    // import would let a Cupertino component in behind the same reason.
    const String router = 'lib/src/app/app_router.dart';
    final Map<String, List<String>> census = cupertinoCensus();
    expect(
      census[router],
      isNotNull,
      reason:
          '$router no longer uses ${cupertinoExemptions[router]}; remove its '
          'exemption',
    );
    final String source = libSources()
        .firstWhere((GateSource s) => s.path == router)
        .text;
    expect(
      RegExp(
        r"import 'package:flutter/cupertino\.dart'\s+"
        r'show CupertinoRouteTransitionMixin;',
      ).hasMatch(source),
      isTrue,
      reason:
          '$router should import cupertino.dart with a one-name show clause',
    );
  });

  test('every exemption is still used', () {
    final Map<String, List<String>> census = cupertinoCensus();
    for (final String path in cupertinoExemptions.keys) {
      expect(
        census.containsKey(path),
        isTrue,
        reason: '$path no longer names a Cupertino class; remove its exemption',
      );
    }
  });
}
