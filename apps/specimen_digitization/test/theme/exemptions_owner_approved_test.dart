// The sign-off gate (10 section 8, `exemptions_owner_approved`).
//
// Every source gate here has a way to let something through: an allow-list, an
// exemption, a backlog count, an allowed value, an exempt path or pattern, a
// threshold, and the ban lists that say what is forbidden. Each one lets a
// hardcoded value, a stock component or a platform fork into the product,
// which is what the owner objected to on 2026-10-17 ("i hope we arent
// duplicating and hand-codring hardcoding"), so loosening one is the owner's
// decision and not an agent's.
//
// The record is the pull request's base. Each allowance is read from the
// base's copy of its gate file and from this change's copy, both as syntax
// trees with every entry evaluated (`1 + 279` is 280), and anything this change
// loosens needs the owner's sign-off on the entry:
//
//     // owner-approved: 2026-10-17 "the owner's exact words"
//
// on the comment lines directly above the entry, or at the end of the entry's
// own line, after its comma; a comment on the line below belongs to the next
// entry. A scalar or a ban list carries it on its declaration. Loosening is: a
// new entry; a backlog count above the base's; a capability with a new kind of
// check, a higher count or a new reader; an exemption, scalar or threshold
// that changed; an entry removed from a ban list. Narrowing needs nothing. The
// date must be a real day that has happened; the words are a quotation, in
// straight double quotes, never a paraphrase. A coordinator's or a reviewer's
// OK is not the owner's.
//
// The base is `GATE_BASE` (CI sets it to the merge commit's first parent) or,
// on a developer's machine, the merge base with `origin/main`. A gate file the
// base does not have is new in this change: its entries are compared with the
// inventory the 2026-10-17 brief named, and anything else in it needs a
// sign-off like any other. Once the base has the file, the inventory is never
// read again.
//
// Two self-checks keep the reading honest: the evaluated entries must equal
// what the compiler builds for every allowance the test can import, and every
// top-level variable in a gate file must be classified here.

import 'dart:io';

import 'package:analyzer/dart/ast/ast.dart';
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
import 'pixel_scan.dart' as pixel_scan;
import 'platform_scan.dart' as platform_scan;

/// How an allowance's entries are read and what loosens it.
enum Grant {
  /// A set or list of values, or a map from a value to its reason: an entry
  /// is the value, and a new one loosens.
  keys,

  /// A backlog of path to count: a new path, or a count above the base's.
  counts,

  /// A map from a path to what it may use: a new path, or a changed value.
  keyAndValue,

  /// A list of objects; [Allowance.keyArgs] positional arguments name an
  /// entry and [Allowance.reasonArg] is prose. A new entry loosens, and so does
  /// any count, set or value wider than the base's.
  objects,

  /// One value: a path, a pattern or a threshold. A change loosens.
  scalar,

  /// What a gate forbids: an entry removed loosens.
  banList,
}

/// An allowance this gate checks.
class Allowance {
  /// Names [declaration] in [file], read as [grant], with [compiled] the
  /// value the compiler builds when the test can import it.
  const Allowance(
    this.file,
    this.declaration,
    this.grant, {
    this.compiled,
    this.keyArgs = 1,
    this.reasonArg,
  });

  /// The gate file, relative to the application root.
  final String file;

  /// The top-level variable.
  final String declaration;

  /// How its entries are read.
  final Grant grant;

  /// The entries as the compiler sees them, key to canonical value.
  final Map<String, String> Function()? compiled;

  /// For [Grant.objects], how many leading positional arguments name an
  /// entry.
  final int keyArgs;

  /// For [Grant.objects], the positional argument that is prose.
  final int? reasonArg;

  /// The key reports use.
  String get id => '$file $declaration';

  /// How the registry names this entry: what decides how it is read.
  String get registryKey => <String>[
    file,
    declaration,
    'Grant.${grant.name}',
    if (keyArgs != 1) 'keyArgs: $keyArgs',
    if (reasonArg != null) 'reasonArg: $reasonArg',
  ].join(' ');
}

const String _theme = 'test/theme';
const String _self = '$_theme/exemptions_owner_approved_test.dart';
const String _packageGeometry =
    'packages/specimen_ui/test/gates/no_literal_geometry_test.dart';

Map<String, String> _keys(Iterable<Object> values) => <String, String>{
  for (final Object v in values) v is String ? v : _show(v): '',
};

Map<String, String> _counts(Map<String, int> m) => <String, String>{
  for (final MapEntry<String, int> e in m.entries) e.key: '${e.value}',
};

/// Every allowance and every ban list in the source gates.
final List<Allowance> allowances = <Allowance>[
  Allowance(
    '$_theme/icons_unique_test.dart',
    'glyphBacklog',
    Grant.counts,
    compiled: () => _counts(icons.glyphBacklog),
  ),
  Allowance(
    '$_theme/no_alpha_literals_test.dart',
    'alphaLiteralBacklog',
    Grant.counts,
    compiled: () => _counts(alpha.alphaLiteralBacklog),
  ),
  Allowance(
    '$_theme/no_color_literals_test.dart',
    'migrationBacklog',
    Grant.counts,
    compiled: () => _counts(colors.migrationBacklog),
  ),
  Allowance(
    '$_theme/no_color_literals_test.dart',
    'paletteFile',
    Grant.scalar,
    compiled: () => <String, String>{'': _show(colors.paletteFile)},
  ),
  const Allowance('$_theme/contrast_test.dart', 'nonTextMinimum', Grant.scalar),
  const Allowance('$_theme/contrast_test.dart', 'textMinimum', Grant.scalar),
  Allowance(
    '$_theme/no_cupertino_test.dart',
    'cupertinoExemptions',
    Grant.objects,
    reasonArg: 3,
    compiled: () => <String, String>{
      for (final cupertino.CupertinoExemption e
          in cupertino.cupertinoExemptions)
        e.path: _show(<Object>[e.name, e.site, <String, Object>{}]),
    },
  ),
  Allowance(
    '$_theme/no_cupertino_test.dart',
    'flutterAdaptiveClasses',
    Grant.banList,
    compiled: () => _keys(cupertino.flutterAdaptiveClasses),
  ),
  Allowance(
    '$_theme/no_cupertino_test.dart',
    'flutterAdaptiveFunctions',
    Grant.banList,
    compiled: () => _keys(cupertino.flutterAdaptiveFunctions),
  ),
  Allowance(
    '$_theme/no_literal_geometry_test.dart',
    'allowedValues',
    Grant.keys,
    compiled: () => _keys(geometry.allowedValues),
  ),
  Allowance(
    '$_theme/no_literal_geometry_test.dart',
    'generatedFile',
    Grant.scalar,
    compiled: () => <String, String>{
      '': _show(_Call('RegExp', <Object?>[geometry.generatedFile.pattern])),
    },
  ),
  Allowance(
    '$_theme/no_literal_geometry_test.dart',
    'geometryBacklog',
    Grant.counts,
    compiled: () => _counts(geometry.geometryBacklog),
  ),
  Allowance(
    '$_theme/no_literal_geometry_test.dart',
    'modelsPrefix',
    Grant.scalar,
    compiled: () => <String, String>{'': _show(geometry.modelsPrefix)},
  ),
  Allowance(
    '$_theme/no_material_components_test.dart',
    'componentBacklog',
    Grant.counts,
    compiled: () => _counts(components.componentBacklog),
  ),
  Allowance(
    '$_theme/no_material_components_test.dart',
    'retiredWidgets',
    Grant.banList,
    compiled: () => _keys(components.retiredWidgets),
  ),
  Allowance(
    '$_theme/no_material_imports_test.dart',
    'importBacklog',
    Grant.keys,
    compiled: () => _keys(imports.importBacklog),
  ),
  Allowance(
    '$_theme/no_material_imports_test.dart',
    'infrastructureImporters',
    Grant.keys,
    compiled: () => _keys(imports.infrastructureImporters.keys),
  ),
  Allowance(
    '$_theme/no_material_imports_test.dart',
    'packageMaterialFiles',
    Grant.keys,
    compiled: () => _keys(imports.packageMaterialFiles),
  ),
  Allowance(
    '$_theme/no_named_pixels_test.dart',
    'namedPixelBacklog',
    Grant.counts,
    compiled: () => _counts(pixels.namedPixelBacklog),
  ),
  Allowance(
    '$_theme/no_platform_branching_test.dart',
    'generatedOptions',
    Grant.scalar,
    compiled: () => <String, String>{'': _show(platform.generatedOptions)},
  ),
  Allowance(
    '$_theme/no_platform_branching_test.dart',
    'platformCapabilities',
    Grant.objects,
    keyArgs: 2,
    reasonArg: 3,
    compiled: () => <String, String>{
      for (final platform_scan.PlatformCapability c
          in platform.platformCapabilities)
        '${c.path} ${c.site}': _show(<Object>[
          c.checks,
          <String, Object>{if (c.readers.isNotEmpty) 'readers': c.readers},
        ]),
    },
  ),
  Allowance(
    '$_theme/pixel_scan.dart',
    'geometryCalls',
    Grant.banList,
    compiled: () => _keys(pixel_scan.geometryCalls),
  ),
  Allowance(
    '$_theme/pixel_scan.dart',
    'namedSizeFloor',
    Grant.scalar,
    compiled: () => <String, String>{'': _show(pixel_scan.namedSizeFloor)},
  ),
  const Allowance('$_theme/pixel_scan.dart', '_sized', Grant.banList),
  // The registry itself, compared with the base's copy of this file: an
  // allowance may not leave the list or change how it is read, and the brief
  // inventory and the new gate files may not grow, without a sign-off.
  Allowance(
    _self,
    'allowances',
    Grant.banList,
    keyArgs: 3,
    compiled: () => <String, String>{
      for (final Allowance a in allowances) a.registryKey: '',
    },
  ),
  Allowance(
    _self,
    'briefInventory',
    Grant.keyAndValue,
    compiled: () => <String, String>{
      for (final String id in briefInventory.keys) id: '',
    },
  ),
  Allowance(
    _self,
    'newGateFiles',
    Grant.keys,
    compiled: () => _keys(newGateFiles),
  ),
  const Allowance(_packageGeometry, 'allowedValues', Grant.keys),
  const Allowance(_packageGeometry, 'foundationFile', Grant.scalar),
  const Allowance(_packageGeometry, 'galleryPrefix', Grant.scalar),
  const Allowance(_packageGeometry, 'generatedFile', Grant.scalar),
  const Allowance(_packageGeometry, 'waveFHandoff', Grant.counts),
];

/// The top-level variables in the gate files that are neither, and why.
const Map<String, String> notAllowances = <String, String>{
  '$_theme/dark_mode_test.dart themes': 'the themes under test',
  '$_theme/no_color_literals_test.dart _colorLiteral':
      'the pattern the gate reads; review owns a change to it',
  '$_theme/no_cupertino_test.dart cupertinoLibrary':
      'the name a finding reports',
  '$_theme/no_dashes_test.dart _stringLiteral':
      'the pattern the gate reads; review owns a change to it',
  '$_theme/no_dashes_test.dart emDash': 'a banned character',
  '$_theme/no_dashes_test.dart enDash': 'a banned character',
  '$_theme/icons_unique_test.dart _materialGlyph':
      'the pattern the gate reads; review owns a change to it',
  '$_theme/no_literal_geometry_test.dart _number':
      'the pattern the gate reads; review owns a change to it',
  '$_theme/no_literal_geometry_test.dart _numberPattern':
      'the pattern the gate reads; review owns a change to it',
  '$_theme/no_literal_geometry_test.dart _paintMethod':
      'the pattern the gate reads; review owns a change to it',
  '$_theme/no_literal_geometry_test.dart _painterClass':
      'the pattern the gate reads; review owns a change to it',
  '$_theme/no_literal_geometry_test.dart argumentRules':
      'the rules the gate applies; review owns a change to them',
  '$_theme/no_literal_geometry_test.dart callRules':
      'the rules the gate applies; review owns a change to them',
  '$_theme/no_material_components_test.dart _constructors':
      'the pattern built from retiredWidgets',
  '$_theme/no_material_components_test.dart _extraTerms':
      'the pattern the gate reads; review owns a change to it',
  '$_theme/no_material_imports_test.dart _materialImport':
      'the pattern the gate reads; review owns a change to it',
  '$_theme/pixel_scan.dart layoutName':
      'the definition of a layout use; review owns a change to it',
  '$_theme/pixel_scan.dart _sizeToken':
      'the definition of a size token; review owns a change to it',
  '$_theme/exemptions_owner_approved_test.dart _self': 'a path this test reads',
  '$_theme/pixel_scan.dart measuredSize':
      'the definition of a measured size; review owns a change to it',
  '$_theme/platform_scan.dart ioPlatform': 'the name a finding reports',
  '$_theme/platform_scan.dart platformOverride': 'the name a finding reports',
  '$_theme/platform_scan.dart targetPlatform': 'the name a finding reports',
  '$_theme/platform_scan.dart targetPlatformType': 'the name a finding reports',
  '$_theme/platform_scan.dart themePlatform': 'the name a finding reports',
  '$_theme/platform_scan.dart webFlag': 'the name a finding reports',
  '$_theme/platform_scan.dart wasmFlag': 'the name a finding reports',
  '$_theme/platform_scan.dart conditionalImport': 'the name a finding reports',
  '$_theme/exemptions_owner_approved_test.dart _packageGeometry':
      'a path this test reads',
  '$_theme/exemptions_owner_approved_test.dart _theme':
      'a path this test reads',
  '$_theme/exemptions_owner_approved_test.dart notAllowances': 'this registry',
  '$_theme/exemptions_owner_approved_test.dart _approval':
      'the sign-off pattern',
  '$_packageGeometry _number':
      'the pattern the gate reads; review owns a change to it',
  '$_packageGeometry _numberPattern':
      'the pattern the gate reads; review owns a change to it',
  '$_packageGeometry _paintMethod':
      'the pattern the gate reads; review owns a change to it',
  '$_packageGeometry _painterClass':
      'the pattern the gate reads; review owns a change to it',
  '$_packageGeometry argumentRules':
      'the rules the gate applies; review owns a change to them',
  '$_packageGeometry callRules':
      'the rules the gate applies; review owns a change to them',
};

/// The gate files the 2026-10-17 change introduced. [briefInventory] may name
/// allowances in these and no others.
const Set<String> newGateFiles = <String>{
  '$_theme/exemptions_owner_approved_test.dart',
  '$_theme/no_alpha_literals_test.dart',
  '$_theme/no_cupertino_test.dart',
  '$_theme/no_named_pixels_test.dart',
  '$_theme/no_platform_branching_test.dart',
  '$_theme/pixel_scan.dart',
};

/// The entries the brief of 2026-10-17 named, for gate files the base does
/// not have yet. `*` is every entry: the brief put the current offenders in
/// each backlog, and each backlog is held to the tree exactly.
///
/// The brief is the coordinating session's, not the owner's: "the iOS route in
/// app/app_router.dart as the only, documented exemption", nine capability
/// files, "values > 1", and "put current offenders in the gate's backlog
/// list". The platform checks in `app_router.dart`, `queue_screen.dart` and
/// `app_theme.dart`, and the skipped generated options, are not here: each
/// needs the owner's sign-off.
const Map<String, Set<String>> briefInventory = <String, Set<String>>{
  '$_theme/no_alpha_literals_test.dart alphaLiteralBacklog': <String>{'*'},
  '$_theme/no_cupertino_test.dart cupertinoExemptions': <String>{
    'lib/src/app/app_router.dart',
  },
  '$_theme/no_named_pixels_test.dart namedPixelBacklog': <String>{'*'},
  '$_theme/no_platform_branching_test.dart platformCapabilities': <String>{
    'lib/firebase_options.ci.dart <directives>',
    'lib/firebase_options.ci.dart DefaultFirebaseOptions.currentPlatform',
    'lib/main.dart main',
    'lib/src/auth.dart emailLinkActionCodeSettings',
    'lib/src/capture/capture_camera.dart <directives>',
    'lib/src/capture/capture_camera.dart PlatformCaptureCamera._startStream',
    'lib/src/capture/capture_camera.dart PlatformCaptureCamera.focusAt',
    // The two conditional exports of the same email-link capability, and the
    // design system's reduced-motion bridge: recorded by the coordinator's
    // direction of 2026-10-17 for the round that counted conditional imports.
    'lib/src/email_link_browser.dart <directives>',
    'lib/src/email_link_source_factory.dart <directives>',
    'packages/specimen_ui/lib/src/foundation/reduced_motion_platform.dart '
        '<directives>',
    'lib/src/email_link_source_factory_io.dart createNativeEmailLinkSource',
    'lib/src/intake.dart _IntakeScreenState._isWeb',
    'lib/src/intake.dart _IntakeScreenState._nativeCameraAvailable',
    'lib/src/intake.dart _IntakeScreenState._recoverCamera',
    'lib/src/magic_link_screen.dart MagicLinkSignInScreen.platform',
    'lib/src/magic_link_screen.dart applePersonalDemoPasteEnabled',
    'lib/src/screens/workbench/readings_panel.dart '
        '_WorkbenchReadingsState.didUpdateWidget',
    'lib/src/theme/motion.dart SpecimenHaptics.available',
  },
  '$_theme/pixel_scan.dart namedSizeFloor': <String>{''},
  // The registry's own lists, for the change that writes this file.
  '$_self briefInventory': <String>{'*'},
  '$_self newGateFiles': <String>{'*'},
};

// ---------------------------------------------------------------------------
// Evaluating an allowance.
// ---------------------------------------------------------------------------

/// A constructor or function call in an allowance, `PlatformCapability(...)`.
class _Call {
  _Call(this.name, this.positional, [this.named = const <String, Object?>{}]);

  final String name;
  final List<Object?> positional;
  final Map<String, Object?> named;
}

String _show(Object? value) => switch (value) {
  null => '?',
  String() => "'$value'",
  num() => value == value.roundToDouble() ? '${value.round()}' : '$value',
  Map<Object?, Object?>() =>
    '{${(value.entries.map((e) => '${_show(e.key)}: ${_show(e.value)}').toList()..sort()).join(', ')}}',
  Set<Object?>() => '{${(value.map(_show).toList()..sort()).join(', ')}}',
  List<Object?>() => '[${value.map(_show).join(', ')}]',
  _Call() =>
    '${value.name}(${<String>[...value.positional.map(_show), ...(value.named.entries.map((e) => '${e.key}: ${_show(e.value)}').toList()..sort())].join(', ')})',
  _ => '$value',
};

/// The value of [e], or null when it is not something an allowance may be
/// written in: literals, collections, calls of them, and the names of
/// top-level constants in [constants].
Object? _evaluate(Expression e, Map<String, Expression> constants) {
  Object? of(Expression x) => _evaluate(x, constants);
  switch (e) {
    case SimpleStringLiteral(:final String value):
      return value;
    case AdjacentStrings(:final String? stringValue):
      return stringValue;
    case StringInterpolation(:final NodeList<InterpolationElement> elements):
      // `'$_theme/x.dart'`: text and the names of string constants.
      final StringBuffer text = StringBuffer();
      for (final InterpolationElement el in elements) {
        final Object? part = switch (el) {
          InterpolationString(:final String value) => value,
          InterpolationExpression(:final Expression expression) => of(
            expression,
          ),
        };
        if (part is! String) return null;
        text.write(part);
      }
      return text.toString();
    case PrefixedIdentifier(:final SimpleIdentifier prefix):
      // A number, or an enum value such as `Grant.counts`.
      return numberOf(e, constants: constants) ??
          (RegExp('^[A-Z]').hasMatch(prefix.name) ? e.toSource() : null);
    case IntegerLiteral() || DoubleLiteral() || BinaryExpression():
      return numberOf(e, constants: constants);
    case PrefixExpression():
      return numberOf(e, constants: constants);
    case SimpleIdentifier(:final String name):
      final Expression? target = constants[name];
      return target == null ? null : of(target);
    case SetOrMapLiteral(
      :final NodeList<CollectionElement> elements,
      :final TypeArgumentList? typeArguments,
    ):
      final bool map = elements.isEmpty
          ? typeArguments?.arguments.length == 2
          : elements.first is MapLiteralEntry;
      if (map) {
        final Map<String, Object?> map = <String, Object?>{};
        for (final CollectionElement el in elements) {
          if (el is! MapLiteralEntry) return null;
          final Object? key = of(el.key);
          if (key == null) return null;
          map[key is String ? key : _show(key)] = of(el.value);
        }
        return map;
      }
      return <Object?>{
        for (final CollectionElement el in elements)
          el is Expression ? of(el) : null,
      };
    case ListLiteral(:final NodeList<CollectionElement> elements):
      return <Object?>[
        for (final CollectionElement el in elements)
          el is Expression ? of(el) : null,
      ];
    case InstanceCreationExpression(
      :final ConstructorName constructorName,
      :final ArgumentList argumentList,
    ):
      return _call(constructorName.type.name.lexeme, argumentList, of);
    case MethodInvocation(
      :final SimpleIdentifier methodName,
      :final ArgumentList argumentList,
    ):
      return _call(methodName.name, argumentList, of);
    default:
      return null;
  }
}

_Call _call(
  String name,
  ArgumentList arguments,
  Object? Function(Expression) of,
) => _Call(
  name,
  <Object?>[
    for (final Expression a in arguments.arguments)
      if (a is! NamedExpression) of(a),
  ],
  <String, Object?>{
    for (final Expression a in arguments.arguments)
      if (a is NamedExpression) a.name.label.name: of(a.expression),
  },
);

/// Whether [v] is written in literals. A call is allowed only as an
/// [Grant.objects] entry or as a scalar's `RegExp`, never inside a value.
bool _readable(Object? v, {bool call = false}) => switch (v) {
  null => false,
  Map<Object?, Object?>() => v.values.every(_readable),
  Iterable<Object?>() => v.every(_readable),
  _Call() =>
    call && v.positional.every(_readable) && v.named.values.every(_readable),
  _ => true,
};

/// The top-level constants [source] can name: its own, then those of the
/// gate files it imports, so two files' `allowedValues` never meet.
Map<String, Expression> constantsFor(
  GateSource source,
  List<GateSource> sources,
) {
  final Map<String, GateSource> byPath = <String, GateSource>{
    for (final GateSource s in sources) s.path: s,
  };
  final String dir = source.path.contains('/')
      ? source.path.substring(0, source.path.lastIndexOf('/'))
      : '';
  return <String, Expression>{
    for (final Directive d in source.unit.directives.reversed)
      if (d is ImportDirective &&
          d.uri.stringValue != null &&
          !d.uri.stringValue!.contains(':') &&
          byPath['$dir/${d.uri.stringValue}'] != null)
        ...constantsOf(<GateSource>[byPath['$dir/${d.uri.stringValue}']!]),
    ...constantsOf(<GateSource>[source]),
  };
}

/// The top-level constants of [sources], by name, for resolving an entry
/// that names one (`webFlag` in a capability).
Map<String, Expression> constantsOf(Iterable<GateSource> sources) {
  final Map<String, Expression> found = <String, Expression>{};
  for (final GateSource s in sources) {
    for (final CompilationUnitMember d in s.unit.declarations) {
      if (d is TopLevelVariableDeclaration) {
        for (final VariableDeclaration v in d.variables.variables) {
          if (v.initializer != null) {
            found.putIfAbsent(v.name.lexeme, () => v.initializer!);
          }
        }
      }
    }
  }
  return found;
}

/// One entry of an allowance: its key, its canonical value, the value
/// itself, and the comments a sign-off may be written in.
class Entry {
  Entry(this.key, this.value, this.shown, this.comments);

  final String key;
  final Object? value;
  final String shown;
  final List<String> comments;
}

/// The entries of [allowance] in [source], or null when [source] does not
/// declare it. An entry the gate cannot evaluate is reported as `!` plus its
/// source.
List<Entry>? entriesOf(
  GateSource source,
  Allowance allowance,
  Map<String, Expression> constants,
) {
  TopLevelVariableDeclaration? declaration;
  VariableDeclaration? variable;
  for (final CompilationUnitMember d in source.unit.declarations) {
    if (d is! TopLevelVariableDeclaration) continue;
    for (final VariableDeclaration v in d.variables.variables) {
      if (v.name.lexeme == allowance.declaration) {
        declaration = d;
        variable = v;
      }
    }
  }
  final Expression? initializer = variable?.initializer;
  if (declaration == null || initializer == null) return null;
  final List<String> onDeclaration = declarationCommentsOf(
    declaration,
    source.unit,
  );

  // [read] is what must be written in literals: the value, and for a keyed
  // entry its key as well.
  Entry entry(
    AstNode node,
    String key,
    Object? value, {
    required Object? read,
    bool call = false,
  }) => Entry(
    _readable(read, call: call) ? key : '!${node.toSource()}',
    value,
    _show(value),
    commentsOf(node, source.unit),
  );

  if (allowance.grant == Grant.scalar) {
    final Object? value = _evaluate(initializer, constants);
    final bool pattern = value is _Call && value.name == 'RegExp';
    return <Entry>[
      Entry(
        _readable(value, call: pattern) ? '' : '!${initializer.toSource()}',
        value,
        _show(value),
        onDeclaration,
      ),
    ];
  }
  final NodeList<CollectionElement> elements = switch (initializer) {
    SetOrMapLiteral(:final NodeList<CollectionElement> elements) => elements,
    ListLiteral(:final NodeList<CollectionElement> elements) => elements,
    _ => throw StateError('${allowance.id} is not a collection literal'),
  };
  final List<Entry> found = <Entry>[];
  for (final CollectionElement el in elements) {
    if (el is MapLiteralEntry) {
      final Object? key = _evaluate(el.key, constants);
      final Object? value = _evaluate(el.value, constants);
      final String k = key is String ? key : _show(key);
      found.add(
        entry(
          el,
          k,
          allowance.grant == Grant.keys ? '' : value,
          read: <Object?>[key, value],
        ),
      );
    } else if (el is Expression) {
      final Object? value = _evaluate(el, constants);
      if (allowance.grant == Grant.objects && value is _Call) {
        final String key = value.positional
            .take(allowance.keyArgs)
            .map((Object? p) => p is String ? p : _show(p))
            .join(' ');
        final List<Object?> rest = <Object?>[
          for (int i = allowance.keyArgs; i < value.positional.length; i++)
            if (i != allowance.reasonArg) value.positional[i],
          // Named arguments always, an empty one dropped, so `readers: {}`
          // and no readers are the same entry.
          <String, Object?>{
            for (final MapEntry<String, Object?> n in value.named.entries)
              if (!_empty(n.value)) n.key: n.value,
          },
        ];
        found.add(entry(el, key, rest, read: value, call: true));
      } else if (allowance.grant == Grant.banList && value is _Call) {
        // A registry entry, `Allowance(file, declaration, grant, ...)`: named
        // by what decides how it is read, never by its compiled callback.
        final List<Object?> parts = <Object?>[
          ...value.positional.take(allowance.keyArgs),
          for (final String k in value.named.keys.toList()..sort())
            if (k != 'compiled') '$k: ${_show(value.named[k])}',
        ];
        found.add(
          entry(
            el,
            parts.map((Object? p) => p is String ? p : _show(p)).join(' '),
            '',
            read: parts,
          ),
        );
      } else if (allowance.grant == Grant.objects) {
        found.add(Entry('!${el.toSource()}', null, '?', const <String>[]));
      } else {
        found.add(
          entry(el, value is String ? value : _show(value), '', read: value),
        );
      }
    } else {
      found.add(Entry('!${el.toSource()}', null, '?', const <String>[]));
    }
  }
  if (allowance.grant == Grant.banList) {
    return <Entry>[
      for (final Entry e in found)
        Entry(e.key, e.value, e.shown, onDeclaration),
    ];
  }
  return found;
}

bool _empty(Object? v) =>
    (v is Map<Object?, Object?> && v.isEmpty) ||
    (v is Iterable<Object?> && v.isEmpty);

/// Whether [head] lets through no more than [base]: counts no higher, sets
/// no wider, everything else equal.
bool narrowerOrEqual(Object? head, Object? base) {
  if (head is num && base is num) return head <= base;
  if (head is Map<Object?, Object?> && base is Map<Object?, Object?>) {
    return head.entries.every(
      (MapEntry<Object?, Object?> e) => base.containsKey(e.key)
          ? narrowerOrEqual(e.value, base[e.key])
          : _empty(e.value),
    );
  }
  if (head is Set<Object?> && base is Set<Object?>) {
    final Set<String> b = base.map(_show).toSet();
    return head.every((Object? v) => b.contains(_show(v)));
  }
  if (head is List<Object?> && base is List<Object?>) {
    if (head.length != base.length) return false;
    for (int i = 0; i < head.length; i++) {
      if (!narrowerOrEqual(head[i], base[i])) return false;
    }
    return true;
  }
  return _show(head) == _show(base);
}

// ---------------------------------------------------------------------------
// The rule.
// ---------------------------------------------------------------------------

final RegExp _approval = RegExp(
  r'owner-approved:\s*(\d{4})-(\d{2})-(\d{2})\s+"([^"]*[A-Za-z][^"]*)"',
);

/// The sign-offs [comments] carry that are dated on a real day no later than
/// [today], each as `date "words"` with the comment markers and line breaks
/// of a wrapped quotation taken out.
Set<String> approvalsIn(List<String> comments, DateTime today) {
  final Set<String> found = <String>{};
  for (final RegExpMatch m in _approval.allMatches(comments.join('\n'))) {
    final int year = int.parse(m.group(1)!);
    final int month = int.parse(m.group(2)!);
    final int day = int.parse(m.group(3)!);
    final DateTime date = DateTime(year, month, day);
    final bool real =
        date.year == year && date.month == month && date.day == day;
    if (real && !date.isAfter(today)) {
      final String words = m
          .group(4)!
          .replaceAll(RegExp(r'\s*\n\s*/*\s*'), ' ')
          .trim();
      found.add('${m.group(1)}-${m.group(2)}-${m.group(3)} "$words"');
    }
  }
  return found;
}

/// Whether [comments] carry a sign-off dated on a real day no later than
/// [today].
bool ownerApproved(List<String> comments, DateTime today) =>
    approvalsIn(comments, today).isNotEmpty;

/// Whether [head] carries a sign-off its [base] did not: one sign-off
/// licenses one change, so a quotation already on the base's copy licenses
/// nothing more.
bool freshlyApproved(List<String> head, List<String> base, DateTime today) =>
    approvalsIn(head, today).difference(approvalsIn(base, today)).isNotEmpty;

/// Everything [head] loosens relative to [base] (null when the base does not
/// have the allowance) that carries no sign-off. [bootstrap] lists the keys a
/// gate new in this change may hold unsigned, `*` for all.
List<String> loosenings({
  required Allowance allowance,
  required List<Entry> head,
  required List<Entry>? base,
  required DateTime today,
  Set<String> bootstrap = const <String>{},
}) {
  final List<String> found = <String>[
    for (final Entry e in head)
      if (e.key.startsWith('!'))
        '${e.key.substring(1)} cannot be read; write the entry as literals',
  ];
  final Map<String, Entry> before = <String, Entry>{
    for (final Entry e
        in base ??
            head.where(
              (Entry e) => bootstrap.contains('*') || bootstrap.contains(e.key),
            ))
      e.key: e,
  };
  if (allowance.grant == Grant.banList) {
    final Set<String> now = head.map((Entry e) => e.key).toSet();
    final List<String> removed = <String>[
      for (final String k in before.keys)
        if (!now.contains(k)) k,
    ];
    if (removed.isNotEmpty &&
        !(head.isNotEmpty &&
            freshlyApproved(
              head.first.comments,
              base?.firstOrNull?.comments ?? const <String>[],
              today,
            ))) {
      found.add('lost ${removed.join(', ')} from what it forbids');
    }
    return found;
  }
  for (final Entry e in head) {
    if (e.key.startsWith('!')) continue;
    final Entry? b = before[e.key];
    if (freshlyApproved(
      e.comments,
      base == null ? const <String>[] : b?.comments ?? const <String>[],
      today,
    )) {
      continue;
    }
    final String name = e.key.isEmpty ? allowance.declaration : e.key;
    final bool keyed = allowance.grant == Grant.keys;
    if (b == null) {
      found.add(keyed ? '$name is new' : '$name ${e.shown} is new');
    } else if (allowance.grant == Grant.scalar) {
      if (e.shown != b.shown) {
        found.add('$name changed from ${b.shown} to ${e.shown}');
      }
    } else if (allowance.grant == Grant.counts) {
      if (!narrowerOrEqual(
        num.tryParse('${e.value}') ?? e.value,
        num.tryParse('${b.value}') ?? b.value,
      )) {
        found.add('$name rose from ${b.shown} to ${e.shown}');
      }
    } else if (!narrowerOrEqual(e.value, b.value)) {
      found.add('$name widened from ${b.shown} to ${e.shown}');
    }
  }
  return found;
}

// ---------------------------------------------------------------------------
// The base.
// ---------------------------------------------------------------------------

String _git(List<String> args) {
  final ProcessResult r = Process.runSync('git', args);
  if (r.exitCode != 0) {
    throw StateError('git ${args.join(' ')} failed: ${r.stderr}');
  }
  return (r.stdout as String).trim();
}

/// The base commit this change is compared with.
String baseCommit() {
  final String? set = Platform.environment['GATE_BASE'];
  if (set == null) {
    // A stale origin/main would compare with an old main and read every new
    // gate as bootstrapping; fetch it first when the network allows.
    Process.runSync('git', <String>['fetch', '--quiet', 'origin', 'main']);
  }
  final String ref = set ?? _git(<String>['merge-base', 'HEAD', 'origin/main']);
  return _git(<String>['rev-parse', '--verify', '$ref^{commit}']);
}

/// The base's copy of [path], relative to the application root, or null
/// when the base does not have it.
String? baseText(String commit, String path) {
  final String prefix = _git(<String>['rev-parse', '--show-prefix']);
  final ProcessResult r = Process.runSync('git', <String>[
    'show',
    '$commit:$prefix$path',
  ]);
  return r.exitCode == 0 ? r.stdout as String : null;
}

/// Every gate file, relative to the application root.
List<String> gateFiles() => <String>[
  for (final FileSystemEntity e in Directory(_theme).listSync())
    if (e is File && e.path.endsWith('.dart')) e.path,
  _packageGeometry,
]..sort();

/// Today in the zone furthest ahead, UTC+14, so an owner who dates a sign-off
/// east of the machine running the test is not refused for a few hours.
DateTime _today() {
  final DateTime ahead = DateTime.now().toUtc().add(const Duration(hours: 14));
  return DateTime(ahead.year, ahead.month, ahead.day);
}

void main() {
  final DateTime day = DateTime(2026, 10, 17);

  List<String> diff(
    String head,
    String? base,
    Allowance a, {
    Set<String> bootstrap = const <String>{},
  }) {
    final GateSource h = GateSource('h.dart', head);
    final GateSource? b = base == null ? null : GateSource('b.dart', base);
    return loosenings(
      allowance: a,
      head: entriesOf(h, a, constantsOf(<GateSource>[h]))!,
      base: b == null ? null : entriesOf(b, a, constantsOf(<GateSource>[b])),
      today: day,
      bootstrap: bootstrap,
    );
  }

  const Allowance files = Allowance('g.dart', 'files', Grant.keys);
  const Allowance backlog = Allowance('g.dart', 'backlog', Grant.counts);

  test('a new entry needs a sign-off, and only a real one clears it', () {
    const String base = "const Set<String> files = <String>{'lib/old.dart'};";
    String head(String comment) =>
        'const Set<String> files = <String>{\n'
        "  'lib/old.dart',\n"
        '  $comment\n'
        "  'lib/new.dart',\n"
        '};\n';
    const List<String> fails = <String>['lib/new.dart is new'];

    expect(diff(head(''), base, files), fails);
    expect(
      diff(head('// owner-approved: 2026-10-17 "yes, allow it"'), base, files),
      isEmpty,
    );
    expect(diff(head('// owner-approved: "yes"'), base, files), fails);
    expect(diff(head('// owner-approved: 2026-10-17'), base, files), fails);
    expect(diff(head('// owner-approved: 2026-10-17 yes'), base, files), fails);
    expect(diff(head('// owner-approved: 2026-10-17 ""'), base, files), fails);
    expect(
      diff(head('// owner-approved: 2026-02-30 "yes"'), base, files),
      fails,
    );
    expect(
      diff(head('// owner-approved: 2026-10-18 "yes"'), base, files),
      fails,
      reason: 'a day that has not happened',
    );
    expect(
      diff(head('// approved by the coordinator 2026-10-17'), base, files),
      fails,
    );
  });

  test('editing the record is not a way round: the base is the record', () {
    // A change that adds a backlog row has nothing else to edit: the base's
    // copy of the gate is what it is compared with.
    const String base =
        "const Map<String, int> backlog = <String, int>{'lib/a.dart': 1};";
    expect(
      diff(
        'const Map<String, int> backlog = <String, int>{\n'
        "  'lib/a.dart': 1,\n"
        "  'lib/new_panel.dart': 1,\n"
        '};\n',
        base,
        backlog,
      ),
      <String>['lib/new_panel.dart 1 is new'],
    );
  });

  test('a backlog may fall freely and may not rise above the base', () {
    const String base =
        'const Map<String, int> backlog = <String, int>{\n'
        "  'lib/fell.dart': 3, 'lib/rose.dart': 1, 'lib/signed.dart': 1,\n"
        '};\n';
    expect(
      diff(
        'const Map<String, int> backlog = <String, int>{\n'
        "  'lib/fell.dart': 1,\n"
        "  'lib/rose.dart': 2,\n"
        '  // owner-approved: 2026-10-17 "fine, for now"\n'
        "  'lib/signed.dart': 9,\n"
        '};\n',
        base,
        backlog,
      ),
      <String>['lib/rose.dart rose from 1 to 2'],
    );
  });

  test('an entry is evaluated, so arithmetic is not an old value', () {
    const Allowance values = Allowance('g.dart', 'allowedValues', Grant.keys);
    expect(
      diff(
        'const Set<num> allowedValues = <num>{0, 1, 2, 1 + 279};',
        'const Set<num> allowedValues = <num>{0, 1, 2};',
        values,
      ),
      <String>['280 is new'],
    );
    expect(
      diff(
        'const Set<num> allowedValues = <num>{0, 1, f()};',
        'const Set<num> allowedValues = <num>{0, 1};',
        values,
      ),
      <String>['f() cannot be read; write the entry as literals'],
    );
  });

  test('a capability may narrow freely and may not widen unsigned', () {
    const Allowance caps = Allowance(
      'g.dart',
      'caps',
      Grant.objects,
      keyArgs: 2,
      reasonArg: 3,
    );
    const String base =
        'const List<C> caps = <C>[\n'
        "  C('lib/a.dart', 'A.x', <String, int>{webFlag: 2}, 'why',\n"
        "      readers: <String, int>{'lib/a.dart A.y': 1}),\n"
        '];\n'
        "const String webFlag = 'kIsWeb';\n";
    String head(String checks, String readers) =>
        'const List<C> caps = <C>[\n'
        "  C('lib/a.dart', 'A.x', <String, int>{$checks}, 'reworded freely',\n"
        '      readers: <String, int>{$readers}),\n'
        '];\n'
        "const String webFlag = 'kIsWeb';\n"
        "const String targetPlatform = 'defaultTargetPlatform';\n";
    expect(diff(head('webFlag: 1', ''), base, caps), isEmpty);
    expect(
      diff(head('webFlag: 3', "'lib/a.dart A.y': 1"), base, caps),
      <String>[
        "lib/a.dart A.x widened from [{'kIsWeb': 2}, {'readers': "
            "{'lib/a.dart A.y': 1}}] to [{'kIsWeb': 3}, {'readers': "
            "{'lib/a.dart A.y': 1}}]",
      ],
    );
    expect(
      diff(head('webFlag: 2, targetPlatform: 1', ''), base, caps).single,
      contains('widened'),
    );
    expect(
      diff(head('webFlag: 2', "'lib/b.dart B.z': 1"), base, caps).single,
      contains('widened'),
    );
  });

  test('a changed scalar, and a ban list that lost an entry, need one', () {
    const Allowance prefix = Allowance('g.dart', 'modelsPrefix', Grant.scalar);
    expect(
      diff(
        "const String modelsPrefix = 'lib/src';",
        "const String modelsPrefix = 'lib/src/models';",
        prefix,
      ),
      <String>["modelsPrefix changed from 'lib/src/models' to 'lib/src'"],
    );
    expect(
      diff(
        '// owner-approved: 2026-10-17 "move the wire types"\n'
            "const String modelsPrefix = 'lib/src';",
        "const String modelsPrefix = 'lib/src/models';",
        prefix,
      ),
      isEmpty,
    );
    const Allowance banned = Allowance('g.dart', 'retired', Grant.banList);
    expect(
      diff(
        "const List<String> retired = <String>['Card'];",
        "const List<String> retired = <String>['Card', 'Scaffold'];",
        banned,
      ),
      <String>['lost Scaffold from what it forbids'],
    );
    expect(
      diff(
        "const List<String> retired = <String>['Card', 'Scaffold', 'Chip'];",
        "const List<String> retired = <String>['Card', 'Scaffold'];",
        banned,
      ),
      isEmpty,
    );
  });

  test('a sign-off belongs to the entry it is written on', () {
    expect(
      diff(
        'const List<String> files = <String>[\n'
            "  'lib/a.dart', // owner-approved: 2026-10-17 \"a only\"\n"
            "  'lib/b.dart',\n"
            '  // owner-approved: 2026-10-17 "c only"\n'
            "  'lib/c.dart',\n"
            "  'lib/d.dart',\n"
            '];\n',
        'const List<String> files = <String>[];',
        files,
      ),
      <String>['lib/b.dart is new', 'lib/d.dart is new'],
    );
    expect(
      diff(
        "const Set<String> files = <String>{'lib/a.dart', 'lib/b.dart'}; "
            '// owner-approved: 2026-10-17 "b"\n',
        'const Set<String> files = <String>{};',
        files,
      ),
      <String>['lib/a.dart is new'],
    );
  });

  test('a gate new in this change holds only what the brief named', () {
    const String head =
        'const Map<String, int> backlog = <String, int>{\n'
        "  'lib/a.dart': 1,\n"
        '};\n';
    expect(diff(head, null, backlog, bootstrap: <String>{'*'}), isEmpty);
    expect(diff(head, null, backlog), <String>['lib/a.dart 1 is new']);
    expect(
      diff(
        "const Set<String> files = <String>{'lib/a.dart', 'lib/b.dart'};",
        null,
        files,
        bootstrap: <String>{'lib/a.dart'},
      ),
      <String>['lib/b.dart is new'],
    );
  });

  test('a sign-off licenses one change, not every later one', () {
    // The same quotation already on the base's copy licenses nothing more;
    // a further rise needs the owner's words again.
    const String base =
        'const Map<String, int> backlog = <String, int>{\n'
        "  'lib/a.dart': 2, // owner-approved: 2026-10-17 \"fine, for now\"\n"
        '};\n';
    String head(String comment) =>
        'const Map<String, int> backlog = <String, int>{\n'
        "  'lib/a.dart': 5, $comment\n"
        '};\n';
    expect(
      diff(
        head('// owner-approved: 2026-10-17 "fine, for now"'),
        base,
        backlog,
      ),
      <String>['lib/a.dart rose from 2 to 5'],
    );
    expect(
      diff(head('// owner-approved: 2026-10-17 "five is fine"'), base, backlog),
      isEmpty,
    );
    expect(
      diff(
        'const Map<String, int> backlog = <String, int>{\n'
        "  'lib/a.dart': 1, // owner-approved: 2026-10-17 \"fine, for now\"\n"
        '};\n',
        base,
        backlog,
      ),
      isEmpty,
      reason: 'falling needs nothing',
    );
  });

  test('the registry cannot drop or regrant an allowance unsigned', () {
    const Allowance registry = Allowance(
      'g.dart',
      'allowances',
      Grant.banList,
      keyArgs: 3,
    );
    const String base =
        'final List<Allowance> allowances = <Allowance>[\n'
        "  Allowance('g.dart', 'backlog', Grant.counts),\n"
        "  Allowance('g.dart', 'caps', Grant.objects, keyArgs: 2, reasonArg: 3),\n"
        '];\n';
    expect(
      diff(
        'final List<Allowance> allowances = <Allowance>[\n'
        "  Allowance('g.dart', 'caps', Grant.objects, keyArgs: 2, reasonArg: 3),\n"
        '];\n',
        base,
        registry,
      ),
      <String>['lost g.dart backlog Grant.counts from what it forbids'],
      reason: 'moved out of the list, for instance into notAllowances',
    );
    expect(
      diff(
        'final List<Allowance> allowances = <Allowance>[\n'
        "  Allowance('g.dart', 'backlog', Grant.keys),\n"
        "  Allowance('g.dart', 'caps', Grant.objects, keyArgs: 2),\n"
        '];\n',
        base,
        registry,
      ),
      <String>[
        'lost g.dart backlog Grant.counts, g.dart caps Grant.objects '
            'keyArgs: 2 reasonArg: 3 from what it forbids',
      ],
      reason: 'read another way, or its prose argument moved',
    );
    expect(
      diff(
        'final List<Allowance> allowances = <Allowance>[\n'
        "  Allowance('g.dart', 'backlog', Grant.counts, compiled: () => x),\n"
        "  Allowance('g.dart', 'caps', Grant.objects, keyArgs: 2, reasonArg: 3),\n"
        "  Allowance('g.dart', 'added', Grant.keys),\n"
        '];\n',
        base,
        registry,
      ),
      isEmpty,
      reason: 'adding an allowance, or a compiled check, tightens',
    );
    const Allowance inventory = Allowance(
      'g.dart',
      'briefInventory',
      Grant.keyAndValue,
    );
    expect(
      diff(
        "const Map<String, Set<String>> briefInventory = {'g x': {'a', 'b'}};",
        "const Map<String, Set<String>> briefInventory = {'g x': {'a'}};",
        inventory,
      ),
      <String>["g x widened from {'a'} to {'a', 'b'}"],
    );
  });

  test('a capability that drops its readers has narrowed', () {
    const Allowance caps = Allowance(
      'g.dart',
      'caps',
      Grant.objects,
      keyArgs: 2,
      reasonArg: 3,
    );
    const String base =
        'const List<C> caps = <C>[\n'
        "  C('lib/a.dart', 'A.x', <String, int>{'kIsWeb': 1}, 'why',\n"
        "      readers: <String, int>{'lib/a.dart A.y': 1}),\n"
        '];\n';
    expect(
      diff(
        'const List<C> caps = <C>[\n'
        "  C('lib/a.dart', 'A.x', <String, int>{'kIsWeb': 1}, 'why'),\n"
        '];\n',
        base,
        caps,
      ),
      isEmpty,
    );
    expect(
      diff(
        'const List<C> caps = <C>[\n'
            "  C('lib/a.dart', 'A.x', <String, int>{'kIsWeb': 1}, 'why',\n"
            '      readers: <String, int>{}),\n'
            '];\n',
        'const List<C> caps = <C>[\n'
            "  C('lib/a.dart', 'A.x', <String, int>{'kIsWeb': 1}, 'why'),\n"
            '];\n',
        caps,
      ),
      isEmpty,
      reason: 'an empty readers map and none are the same entry',
    );
  });

  test('every gate file parses, so the tree is the whole file', () {
    for (final String path in gateFiles()) {
      expect(
        GateSource(path, File(path).readAsStringSync()).errors,
        isEmpty,
        reason: path,
      );
    }
  });

  final List<GateSource> heads = <GateSource>[
    for (final String path in gateFiles())
      GateSource(path, File(path).readAsStringSync()),
  ];
  GateSource headOf(String path) =>
      heads.firstWhere((GateSource s) => s.path == path);
  Map<String, Expression> headConstantsOf(String path) =>
      constantsFor(headOf(path), heads);

  test('the gate reads every allowance the way the compiler builds it', () {
    for (final Allowance a in allowances) {
      final List<Entry>? entries = entriesOf(
        headOf(a.file),
        a,
        headConstantsOf(a.file),
      );
      expect(entries, isNotNull, reason: '${a.id} is not declared');
      expect(
        entries!.where((Entry e) => e.key.startsWith('!')),
        isEmpty,
        reason: a.id,
      );
      if (a.compiled == null) continue;
      final Map<String, String> read = <String, String>{
        for (final Entry e in entries)
          e.key: a.grant == Grant.counts || a.grant == Grant.objects
              ? _show(e.value)
              : a.grant == Grant.scalar
              ? e.shown
              : '',
      };
      final Map<String, String> built = a.compiled!();
      if (a.grant == Grant.counts) {
        expect(read, <String, String>{
          for (final MapEntry<String, String> e in built.entries)
            e.key: e.value,
        }, reason: a.id);
      } else {
        expect(read, built, reason: a.id);
      }
    }
  });

  test('every top-level variable in a gate file is classified', () {
    final Set<String> known = <String>{
      for (final Allowance a in allowances) a.id,
      ...notAllowances.keys,
    };
    final List<String> unknown = <String>[
      for (final GateSource s in heads)
        for (final CompilationUnitMember d in s.unit.declarations)
          if (d is TopLevelVariableDeclaration)
            for (final VariableDeclaration v in d.variables.variables)
              if (!known.contains('${s.path} ${v.name.lexeme}'))
                '${s.path} ${v.name.lexeme}',
    ];
    expect(
      unknown,
      isEmpty,
      reason:
          'an allowance or a ban list goes in `allowances`, so loosening it '
          'needs a sign-off; anything else goes in `notAllowances` with why',
    );
    final Set<String> declared = <String>{
      for (final GateSource s in heads)
        for (final CompilationUnitMember d in s.unit.declarations)
          if (d is TopLevelVariableDeclaration)
            for (final VariableDeclaration v in d.variables.variables)
              '${s.path} ${v.name.lexeme}',
    };
    expect(known.difference(declared), isEmpty, reason: 'stale rows');
  });

  test('the brief inventory names only allowances in new gate files', () {
    for (final String id in briefInventory.keys) {
      expect(
        newGateFiles.any((String f) => id.startsWith('$f ')),
        isTrue,
        reason: id,
      );
    }
  });

  test('nothing loosened since the base without the owner signing it', () {
    final String commit = baseCommit();
    final List<GateSource> bases = <GateSource>[
      for (final String path in gateFiles())
        if (baseText(commit, path) case final String text)
          GateSource(path, text),
    ];

    final List<String> found = <String>[];
    for (final Allowance a in allowances) {
      final GateSource? base = bases
          .where((GateSource s) => s.path == a.file)
          .firstOrNull;
      for (final String problem in loosenings(
        allowance: a,
        head: entriesOf(headOf(a.file), a, headConstantsOf(a.file))!,
        base: base == null
            ? null
            : entriesOf(base, a, constantsFor(base, bases)),
        today: _today(),
        bootstrap: base == null
            ? briefInventory[a.id] ?? const <String>{}
            : const <String>{},
      )) {
        found.add('${a.id}: $problem');
      }
    }
    expect(
      found,
      isEmpty,
      reason:
          'fix the code instead, or ask the owner. A loosening needs '
          '`// owner-approved: YYYY-MM-DD "the owner\'s exact words"` on the '
          'entry (CLAUDE.md, "Gate exemptions"). Compared with $commit:\n'
          '${found.join('\n')}',
    );
  });
}
