// The Cupertino gate (10 section 8, `no_cupertino`).
//
// 09 section 2 principle 5: behaviour adapts, identity does not. Type, colour,
// shape, icons, motion signature and component anatomy are ours on every
// platform, so no file the product ships, the application's `lib/` or that of
// a package it keeps under `packages/` (the design system's among them), draws
// a Cupertino component. The Material
// gates never read this library, and a `CupertinoTabBar` shipped on iOS through
// that gap, with tests asserting it, until `UiTabBar` replaced it on
// 2026-10-17 (10 section 4.4).
//
// The gate reads each file as a syntax tree, so comments and line breaks
// between tokens change nothing. Three ways in are counted: an import or
// export whose URI, or any of its conditional URIs, is
// `package:flutter/cupertino.dart`; any identifier that contains `Cupertino`,
// which also catches the Cupertino classes `material.dart` defines itself,
// such as `CupertinoPageTransitionsBuilder`, the functions such as
// `showCupertinoDialog`, and an identifier inside a string interpolation; and
// the Flutter APIs that draw a Cupertino component on Apple platforms under a
// Material name, named exactly below, so a product class's own `adaptive`
// constructor is not counted.

import 'package:analyzer/dart/ast/ast.dart';
import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';

/// A file that may name a Cupertino class: the one class, and the one site in
/// the file that may use it.
class CupertinoExemption {
  /// Allows [path] to import [name] alone and use it in [site], for [why].
  const CupertinoExemption(this.path, this.name, this.site, this.why);

  /// The file, relative to the application root.
  final String path;

  /// The one Cupertino name it may use.
  final String name;

  /// The declaration that may use it, `Class.member`.
  final String site;

  /// Why.
  final String why;
}

/// The files that may name a Cupertino class. One.
///
/// The router takes `CupertinoRouteTransitionMixin` for the phone iOS push
/// from the queue to the workbench, the platform page transition 04 row 18
/// gives it; 09 section 2 principle 5 lists page transitions with the
/// behaviour that follows the platform. Every cupertino directive in the file
/// must `show` that name and nothing else, and only `buildTransitions` may use
/// it.
const List<CupertinoExemption> cupertinoExemptions = <CupertinoExemption>[
  CupertinoExemption(
    'lib/src/app/app_router.dart',
    'CupertinoRouteTransitionMixin',
    '_WorkspacePageRoute.buildTransitions',
    'the phone iOS page transition (04 row 18; 09 section 2 principle 5)',
  ),
];

/// The library a directive finding names.
const String cupertinoLibrary = 'package:flutter/cupertino.dart';

/// The Flutter classes whose `adaptive` constructor or member draws a
/// Cupertino component on Apple platforms, from the Flutter 3.38.5 sources.
const Set<String> flutterAdaptiveClasses = <String>{
  'AboutDialog',
  'AlertDialog',
  'Checkbox',
  'CheckboxListTile',
  'CircularProgressIndicator',
  'Icons',
  'Radio',
  'RadioListTile',
  'RefreshIndicator',
  'Slider',
  'Switch',
  'SwitchListTile',
};

/// The Flutter functions that show a Cupertino component on Apple platforms.
const Set<String> flutterAdaptiveFunctions = <String>{
  'showAdaptiveAboutDialog',
  'showAdaptiveDialog',
};

/// One Cupertino use: where it is and what it names.
class CupertinoUse {
  /// Records [term] at [line] in the declaration [site].
  const CupertinoUse(this.line, this.site, this.term, {this.shows});

  /// The line it is on.
  final int line;

  /// The declaration it is in, or `<directives>`.
  final String site;

  /// The library, the identifier, or `Class.adaptive`.
  final String term;

  /// For a directive, the names its `show` clauses list, or null when it has
  /// none (a bare import, or one that hides).
  final List<String>? shows;

  @override
  String toString() => 'line $line, $site, $term';
}

/// Every Cupertino use in [source].
List<CupertinoUse> cupertinoUsesIn(GateSource source) {
  final _CupertinoVisitor visitor = _CupertinoVisitor(source);
  source.unit.accept(visitor);
  return visitor.found;
}

class _CupertinoVisitor extends CodeVisitor {
  _CupertinoVisitor(this.source);

  final GateSource source;
  final List<CupertinoUse> found = <CupertinoUse>[];

  void _add(AstNode node, String term, {List<String>? shows}) => found.add(
    CupertinoUse(source.lineOf(node.offset), siteOf(node), term, shows: shows),
  );

  void _directive(NamespaceDirective node) {
    final List<String?> uris = <String?>[
      node.uri.stringValue,
      for (final Configuration c in node.configurations) c.uri.stringValue,
    ];
    if (!uris.contains(cupertinoLibrary)) return;
    final bool narrowed =
        node.combinators.isNotEmpty &&
        node.combinators.every((Combinator c) => c is ShowCombinator);
    _add(
      node,
      cupertinoLibrary,
      shows: narrowed
          ? <String>[
              for (final Combinator c in node.combinators)
                for (final SimpleIdentifier n
                    in (c as ShowCombinator).shownNames)
                  n.name,
            ]
          : null,
    );
  }

  @override
  void visitImportDirective(ImportDirective node) {
    _directive(node);
    super.visitImportDirective(node);
  }

  @override
  void visitExportDirective(ExportDirective node) {
    _directive(node);
    super.visitExportDirective(node);
  }

  @override
  void visitSimpleIdentifier(SimpleIdentifier node) {
    if (node.name.contains('Cupertino')) _add(node, node.name);
    super.visitSimpleIdentifier(node);
  }

  @override
  void visitNamedType(NamedType node) {
    if (node.name.lexeme.contains('Cupertino')) _add(node, node.name.lexeme);
    super.visitNamedType(node);
  }

  @override
  void visitInstanceCreationExpression(InstanceCreationExpression node) {
    // Unresolved, `const Switch.adaptive()` may read as the type `adaptive`
    // under the prefix `Switch`, so both shapes are asked about.
    final NamedType type = node.constructorName.type;
    final String? prefix = type.importPrefix?.name.lexeme;
    final String? named = node.constructorName.name?.name;
    if (flutterAdaptiveClasses.contains(type.name.lexeme) &&
        named == 'adaptive') {
      _add(node, '${type.name.lexeme}.adaptive');
    } else if (prefix != null &&
        flutterAdaptiveClasses.contains(prefix) &&
        type.name.lexeme == 'adaptive') {
      _add(node, '$prefix.adaptive');
    }
    super.visitInstanceCreationExpression(node);
  }

  @override
  void visitMethodInvocation(MethodInvocation node) {
    final Expression? target = node.target;
    final String method = node.methodName.name;
    // `Switch.adaptive()`, or `m.Switch.adaptive()` through an import prefix.
    final String? owner = switch (target) {
      SimpleIdentifier(:final String name) => name,
      PrefixedIdentifier(:final SimpleIdentifier identifier) => identifier.name,
      _ => null,
    };
    if (method == 'adaptive' && flutterAdaptiveClasses.contains(owner)) {
      _add(node, '$owner.adaptive');
    } else if ((target == null || target is SimpleIdentifier) &&
        flutterAdaptiveFunctions.contains(method)) {
      _add(node, method);
    }
    super.visitMethodInvocation(node);
  }

  @override
  void visitPropertyAccess(PropertyAccess node) {
    // `m.Icons.adaptive` through an import prefix.
    final Expression? target = node.target;
    if (node.propertyName.name == 'adaptive' &&
        target is PrefixedIdentifier &&
        flutterAdaptiveClasses.contains(target.identifier.name)) {
      _add(node, '${target.identifier.name}.adaptive');
    }
    super.visitPropertyAccess(node);
  }

  @override
  void visitPrefixedIdentifier(PrefixedIdentifier node) {
    if (node.identifier.name == 'adaptive' &&
        flutterAdaptiveClasses.contains(node.prefix.name)) {
      _add(node, '${node.prefix.name}.adaptive');
    }
    super.visitPrefixedIdentifier(node);
  }
}

/// Every file the product ships from the application at [base], its `lib/`
/// and the design system's, with a Cupertino use. A Cupertino widget wrapped
/// as a `Ui*` component would otherwise reach the app with no token in it.
Map<String, List<CupertinoUse>> cupertinoCensus({String base = '.'}) {
  final Map<String, List<CupertinoUse>> found = <String, List<CupertinoUse>>{};
  for (final GateSource source in productSources(base: base)) {
    final List<CupertinoUse> uses = cupertinoUsesIn(source);
    if (uses.isNotEmpty) found[source.path] = uses;
  }
  return found;
}

/// What the gate objects to in [census]: any use in a file with no exemption;
/// in an exempt file, a directive that does not `show` exactly its one name,
/// and a use of any other name, or of its name outside its site.
List<String> cupertinoViolations(Map<String, List<CupertinoUse>> census) {
  final List<String> found = <String>[];
  census.forEach((String path, List<CupertinoUse> uses) {
    final CupertinoExemption? exemption = cupertinoExemptions
        .where((CupertinoExemption e) => e.path == path)
        .firstOrNull;
    for (final CupertinoUse use in uses) {
      if (exemption == null) {
        found.add('$path: $use');
      } else if (use.term == cupertinoLibrary) {
        if (use.shows == null ||
            use.shows!.length != 1 ||
            use.shows!.single != exemption.name) {
          found.add(
            '$path: $use must show ${exemption.name} and nothing else, '
            'showing ${use.shows ?? 'everything'}',
          );
        }
      } else if (use.term != exemption.name) {
        found.add('$path: $use, but only ${exemption.name} is exempt');
      } else if (use.site != '<directives>' && use.site != exemption.site) {
        found.add('$path: $use, but only ${exemption.site} may use it');
      }
    }
  });
  return found;
}

void main() {
  List<String> termsOf(String text) => <String>[
    for (final CupertinoUse u in cupertinoUsesIn(GateSource('x.dart', text)))
      u.term,
  ];

  test('the scanner finds each way in, whatever the trivia', () {
    expect(termsOf("import 'package:flutter/cupertino.dart';"), <String>[
      cupertinoLibrary,
    ]);
    expect(termsOf('import "package:flutter/cupertino.dart" as c;'), <String>[
      cupertinoLibrary,
    ]);
    expect(
      termsOf("export /* compatibility */ 'package:flutter/cupertino.dart';"),
      <String>[cupertinoLibrary],
    );
    expect(
      termsOf(
        "import 'package:flutter/widgets.dart'\n"
        "    if (dart.library.io) 'package:flutter/cupertino.dart';",
      ),
      <String>[cupertinoLibrary],
    );
    expect(termsOf('Widget b() => c.CupertinoTabBar(items: tabs);'), <String>[
      'CupertinoTabBar',
    ]);
    expect(termsOf('final o = CupertinoPageTransitionsBuilder();'), <String>[
      'CupertinoPageTransitionsBuilder',
    ]);
    expect(termsOf('void f() { showCupertinoDialog(context: c); }'), <String>[
      'showCupertinoDialog',
    ]);
    expect(termsOf("final s = '\${CupertinoColors.label}';"), <String>[
      'CupertinoColors',
    ]);
    expect(termsOf('Widget t() => Switch.adaptive(value: on);'), <String>[
      'Switch.adaptive',
    ]);
    expect(
      termsOf('Widget t() => const Switch.adaptive(value: true);'),
      <String>['Switch.adaptive'],
    );
    expect(termsOf('final i = Icons.adaptive.share;'), <String>[
      'Icons.adaptive',
    ]);
    expect(termsOf('void f() { showAdaptiveDialog(context: c); }'), <String>[
      'showAdaptiveDialog',
    ]);
    expect(termsOf('Widget t() => m.Switch.adaptive(value: on);'), <String>[
      'Switch.adaptive',
    ]);
    expect(termsOf('final i = m.Icons.adaptive.share;'), <String>[
      'Icons.adaptive',
    ]);
    expect(termsOf('void f() { m.showAdaptiveDialog(context: c); }'), <String>[
      'showAdaptiveDialog',
    ]);

    // Prose, strings, and the product's own window-adaptive APIs are not
    // uses.
    expect(termsOf("// import 'package:flutter/cupertino.dart';"), isEmpty);
    expect(
      termsOf("/* import 'package:flutter/cupertino.dart'; */\nvoid f() {}"),
      isEmpty,
    );
    expect(termsOf('/// Retires `CupertinoTabBar`.\nvoid f() {}'), isEmpty);
    expect(termsOf("final s = 'CupertinoTabBar';"), isEmpty);
    expect(
      termsOf('void f() { showAdaptiveModal<void>(context: c); }'),
      isEmpty,
    );
    expect(termsOf('void f() { UiDialog.showAdaptive<void>(c); }'), isEmpty);
    expect(termsOf('Widget w() => WindowLayout.adaptive(child: c);'), isEmpty);
  });

  test('a planted Cupertino use fails the gate', () {
    // The same census and verdict the gate runs, over a temporary
    // application: a clean file, one violation per way in, an exempt router
    // that reaches past its one name three ways, and a Cupertino widget
    // wrapped inside the design system and inside a second package of the
    // application's own; vendored upstream code under third_party/ is not
    // the product's to count.
    final String base = plantedApplication(<String, String>{
      'packages/zz_native/lib/zz_native.dart':
          "import 'package:flutter/cupertino.dart';\n"
          'Widget zzTabs() => const CupertinoTabBar(items: tabs);\n',
      'third_party/app_links/lib/app_links.dart':
          "import 'package:flutter/cupertino.dart';\n",
      'lib/src/clean.dart': "import 'package:flutter/widgets.dart';\n",
      'lib/src/tab_bar.dart':
          "import 'package:flutter/cupertino.dart';\n"
          'Widget bar() => CupertinoTabBar(items: tabs);\n',
      'lib/src/theme.dart':
          'const Object t = CupertinoPageTransitionsBuilder();\n',
      'lib/src/toggle.dart': 'Widget t() => Switch.adaptive(value: on);\n',
      'packages/specimen_ui/lib/src/controls/ui_tabs.dart':
          'Widget tabs() => CupertinoTabBar(items: tabs);\n',
      'lib/src/app/app_router.dart':
          "import 'package:flutter/cupertino.dart' "
          'show CupertinoRouteTransitionMixin;\n'
          "import 'package:flutter/cupertino.dart';\n"
          "// import 'package:flutter/cupertino.dart' "
          'show CupertinoRouteTransitionMixin;\n'
          'class _WorkspacePageRoute {\n'
          '  void buildTransitions() => CupertinoRouteTransitionMixin.x();\n'
          '  void other() => CupertinoRouteTransitionMixin.x();\n'
          '  void dialog() => showCupertinoDialog(context: c);\n'
          '}\n',
    });
    expect(cupertinoViolations(cupertinoCensus(base: base)), <String>[
      'lib/src/app/app_router.dart: line 2, <directives>, '
          '$cupertinoLibrary must show CupertinoRouteTransitionMixin and '
          'nothing else, showing everything',
      'lib/src/app/app_router.dart: line 6, _WorkspacePageRoute.other, '
          'CupertinoRouteTransitionMixin, but only '
          '_WorkspacePageRoute.buildTransitions may use it',
      'lib/src/app/app_router.dart: line 7, _WorkspacePageRoute.dialog, '
          'showCupertinoDialog, but only CupertinoRouteTransitionMixin is '
          'exempt',
      'lib/src/tab_bar.dart: line 1, <directives>, $cupertinoLibrary',
      'lib/src/tab_bar.dart: line 2, bar, CupertinoTabBar',
      'lib/src/theme.dart: line 1, t, CupertinoPageTransitionsBuilder',
      'lib/src/toggle.dart: line 1, t, Switch.adaptive',
      'packages/specimen_ui/lib/src/controls/ui_tabs.dart: line 1, tabs, '
          'CupertinoTabBar',
      'packages/zz_native/lib/zz_native.dart: line 1, <directives>, '
          '$cupertinoLibrary',
      'packages/zz_native/lib/zz_native.dart: line 2, zzTabs, '
          'CupertinoTabBar',
    ]);
  });

  test('every product file parses, so the tree is the whole file', () {
    for (final GateSource source in productSources()) {
      expect(source.errors, isEmpty, reason: source.path);
    }
  });

  test('no product file names a Cupertino component', () {
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

  test('every exemption is still used where it says', () {
    final Map<String, List<CupertinoUse>> census = cupertinoCensus();
    for (final CupertinoExemption e in cupertinoExemptions) {
      expect(
        census[e.path]?.any(
              (CupertinoUse u) => u.term == e.name && u.site == e.site,
            ) ??
            false,
        isTrue,
        reason:
            '${e.path} no longer uses ${e.name} in ${e.site}; remove or '
            'correct its exemption',
      );
    }
  });
}
