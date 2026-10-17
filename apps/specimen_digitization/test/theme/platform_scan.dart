// The platform gate's reader, kept apart from its test so the sign-off gate
// can read the same definitions.
//
// A platform check is a capability (CLAUDE.md: layout decisions use window
// size, never platform or device type; 09 section 2 principle 5: behaviour may
// follow the platform, identity may not). Each one is named by the
// declaration it sits in and counted by kind, and each declaration that holds
// one is also counted by where it is read, because a platform fact can leave
// its declaration as a boolean or a return value without another platform
// token.

import 'package:analyzer/dart/ast/ast.dart';

import 'gate_support.dart';

/// The kinds of check, by the name a finding reports.
const String webFlag = 'kIsWeb';
const String targetPlatform = 'defaultTargetPlatform';
const String targetPlatformType = 'TargetPlatform';
const String ioPlatform = 'Platform';
const String themePlatform = 'Theme.platform';
const String platformOverride = 'debugDefaultTargetPlatformOverride';
const String wasmFlag = 'kIsWasm';
const String conditionalImport = 'conditional import';
const String scrollPlatform = 'getPlatform';

/// `identical(0, 0.0)` or `0.0 is int`: true only where numbers are
/// JavaScript's, so a web test with no platform token in it.
const String numberWebTest = 'identical(0, 0.0)';

/// A declaration allowed to ask which platform it runs on.
class PlatformCapability {
  /// Allows [site] in [path] exactly the [checks] it makes, read exactly
  /// where [readers] says, for the reason [why].
  const PlatformCapability(
    this.path,
    this.site,
    this.checks,
    this.why, {
    this.readers = const <String, int>{},
  });

  /// The file, relative to the application root.
  final String path;

  /// The declaration, as [siteOf] names it: `Class.member`, `function`, or
  /// `<directives>` for a `show` clause that names a check.
  final String site;

  /// How many checks of each kind it makes.
  final Map<String, int> checks;

  /// One line: the capability that differs by platform.
  final String why;

  /// Where the declaration is read, `path site`, and how many times.
  final Map<String, int> readers;

  /// The name a reader refers to it by.
  String get member => site.split('.').last;

  /// The class it belongs to, or null for a top-level declaration.
  String? get owner => site.contains('.') ? site.split('.').first : null;
}

/// One platform check: where it is and what kind.
class PlatformCheck {
  /// Records a check of [kind] at [line] in the declaration [site].
  const PlatformCheck(this.line, this.site, this.kind);

  /// The line it is on.
  final int line;

  /// The declaration it is in.
  final String site;

  /// Its kind.
  final String kind;

  @override
  String toString() => 'line $line, $site, $kind';
}

/// Every platform check in [source].
List<PlatformCheck> platformChecksIn(GateSource source) {
  final _PlatformVisitor visitor = _PlatformVisitor(source);
  source.unit.accept(visitor);
  return visitor.found;
}

class _PlatformVisitor extends CodeVisitor {
  _PlatformVisitor(this.source) {
    source.unit.accept(_ThemeNames(themes));
  }

  final GateSource source;
  final List<PlatformCheck> found = <PlatformCheck>[];

  /// The names that hold a theme in this file: a variable initialised from
  /// `Theme.of(...)`, and a variable, field or parameter typed `ThemeData`.
  final Set<String> themes = <String>{};

  void _add(AstNode node, String kind) =>
      found.add(PlatformCheck(source.lineOf(node.offset), siteOf(node), kind));

  @override
  void visitSimpleIdentifier(SimpleIdentifier node) {
    switch (node.name) {
      case webFlag || wasmFlag || targetPlatform || platformOverride:
        _add(node, node.name);
      case targetPlatformType:
        _add(node, targetPlatformType);
      case ioPlatform:
        _add(node, ioPlatform);
    }
    super.visitSimpleIdentifier(node);
  }

  @override
  void visitNamedType(NamedType node) {
    if (node.name.lexeme == targetPlatformType ||
        node.importPrefix?.name.lexeme == targetPlatformType) {
      _add(node, targetPlatformType);
    }
    super.visitNamedType(node);
  }

  @override
  void visitPropertyAccess(PropertyAccess node) {
    final Expression? target = node.target;
    if (node.propertyName.name == 'platform' &&
        (isThemeOf(target) || _themeLike(target))) {
      _add(node, themePlatform);
    }
    super.visitPropertyAccess(node);
  }

  @override
  void visitPrefixedIdentifier(PrefixedIdentifier node) {
    if (node.identifier.name == 'platform' && _themeLike(node.prefix)) {
      _add(node, themePlatform);
    }
    super.visitPrefixedIdentifier(node);
  }

  /// A theme held in a variable, `theme.platform` or `t.platform` after
  /// `final t = Theme.of(context)`, asks the same question as
  /// `Theme.of(context).platform`.
  bool _themeLike(Expression? target) =>
      target is SimpleIdentifier &&
      (themes.contains(target.name) ||
          RegExp('theme', caseSensitive: false).hasMatch(target.name));

  @override
  void visitMethodInvocation(MethodInvocation node) {
    final String name = node.methodName.name;
    final List<Expression> arguments = node.argumentList.arguments;
    if (name == scrollPlatform) {
      // `ScrollConfiguration.of(context).getPlatform(context)`.
      _add(node, scrollPlatform);
    } else if (name == 'identical' &&
        node.target == null &&
        arguments.length == 2 &&
        _literalType(arguments.first) != null &&
        _literalType(arguments.last) != null &&
        _literalType(arguments.first) != _literalType(arguments.last)) {
      _add(node, numberWebTest);
    }
    super.visitMethodInvocation(node);
  }

  @override
  void visitIsExpression(IsExpression node) {
    final TypeAnnotation type = node.type;
    if (_literalType(node.expression) != null &&
        type is NamedType &&
        (type.name.lexeme == 'int' || type.name.lexeme == 'double')) {
      _add(node, numberWebTest);
    }
    super.visitIsExpression(node);
  }

  /// `int` or `double` for a number written as a literal, or null.
  static String? _literalType(Expression e) => switch (e) {
    IntegerLiteral() => 'int',
    DoubleLiteral() => 'double',
    PrefixExpression(:final Expression operand) => _literalType(operand),
    ParenthesizedExpression(:final Expression expression) => _literalType(
      expression,
    ),
    _ => null,
  };

  @override
  void visitConfiguration(Configuration node) {
    // `import 'a.dart' if (dart.library.io) 'b.dart'` picks code by platform.
    _add(node, conditionalImport);
    super.visitConfiguration(node);
  }
}

/// Whether [e] is `Theme.of(...)`, through an import prefix or not.
bool isThemeOf(Expression? e) =>
    e is MethodInvocation &&
    e.methodName.name == 'of' &&
    switch (e.target) {
      SimpleIdentifier(:final String name) => name == 'Theme',
      PrefixedIdentifier(:final SimpleIdentifier identifier) =>
        identifier.name == 'Theme',
      _ => false,
    };

class _ThemeNames extends CodeVisitor {
  _ThemeNames(this.names);

  final Set<String> names;

  static bool _themeData(TypeAnnotation? type) =>
      type is NamedType && type.name.lexeme == 'ThemeData';

  @override
  void visitVariableDeclaration(VariableDeclaration node) {
    final AstNode? list = node.parent;
    if (isThemeOf(node.initializer) ||
        (list is VariableDeclarationList && _themeData(list.type))) {
      names.add(node.name.lexeme);
    }
    super.visitVariableDeclaration(node);
  }

  @override
  void visitSimpleFormalParameter(SimpleFormalParameter node) {
    if (_themeData(node.type) && node.name != null) {
      names.add(node.name!.lexeme);
    }
    super.visitSimpleFormalParameter(node);
  }
}

/// Whether the declaration [site] in [source] is an instance member, read
/// through any object, rather than static or top-level, read through its
/// owner or by name.
bool isInstanceMember(GateSource source, String site) {
  final List<String> parts = site.split('.');
  if (parts.length != 2) return false;
  for (final CompilationUnitMember d in source.unit.declarations) {
    if (d is! ClassDeclaration || d.namePart.typeName.lexeme != parts[0]) {
      continue;
    }
    final ClassBody body = d.body;
    if (body is! BlockClassBody) continue;
    for (final ClassMember m in body.members) {
      if (m is MethodDeclaration && m.name.lexeme == parts[1]) {
        return !m.isStatic;
      }
      if (m is FieldDeclaration &&
          m.fields.variables.any((v) => v.name.lexeme == parts[1])) {
        return !m.isStatic;
      }
    }
  }
  return false;
}

/// The library [source] belongs to: the file itself, or, for a part, the file
/// that declares it, named by `part of 'uri'` or `part of name`.
String libraryOf(GateSource source, Map<String, GateSource> byPath) {
  for (final Directive d in source.unit.directives) {
    if (d is! PartOfDirective) continue;
    final String? uri = d.uri?.stringValue;
    if (uri != null) return resolveUri(source.path, uri) ?? source.path;
    final String? name = d.libraryName?.toSource();
    for (final GateSource s in byPath.values) {
      if (s.unit.directives.any(
        (Directive l) => l is LibraryDirective && l.name?.toSource() == name,
      )) {
        return s.path;
      }
    }
  }
  return source.path;
}

/// The files [source] can see: itself, its library, and every file its
/// library reaches through imports and exports, conditional ones included,
/// within [sources], with the parts of each. A part sees what its library
/// sees, and a library sees its parts.
Set<String> visibleFrom(GateSource source, Map<String, GateSource> byPath) {
  final String library = libraryOf(source, byPath);
  final Set<String> seen = <String>{source.path, library};
  final List<String> queue = <String>[library];
  while (queue.isNotEmpty) {
    final GateSource? s = byPath[queue.removeLast()];
    if (s == null) continue;
    for (final Directive d in s.unit.directives) {
      final List<String?> uris = switch (d) {
        NamespaceDirective() => <String?>[
          d.uri.stringValue,
          for (final Configuration c in d.configurations) c.uri.stringValue,
        ],
        PartDirective() => <String?>[d.uri.stringValue],
        _ => const <String?>[],
      };
      for (final String? uri in uris) {
        final String? path = uri == null ? null : resolveUri(s.path, uri);
        if (path != null && seen.add(path)) queue.add(path);
      }
    }
  }
  return seen;
}

/// The path, relative to the application root, that [uri] in the file
/// [from] names, or null for a `dart:` library. Another package is where the
/// application keeps its own, `packages/<name>/lib/`; one from pub is not
/// among the sources, so nothing is read there.
String? resolveUri(String from, String uri) {
  const String app = 'package:specimen_digitization/';
  if (uri.startsWith(app)) return 'lib/${uri.substring(app.length)}';
  final RegExpMatch? package = RegExp(r'^package:(\w+)/(.*)$').firstMatch(uri);
  if (package != null) return 'packages/${package[1]}/lib/${package[2]}';
  if (uri.contains(':')) return null;
  final List<String> parts = from.split('/')..removeLast();
  for (final String segment in uri.split('/')) {
    if (segment == '..') {
      if (parts.isNotEmpty) parts.removeLast();
    } else if (segment != '.') {
      parts.add(segment);
    }
  }
  return parts.join('/');
}

/// Where each of [capabilities] is read in [sources], `path site` to count.
///
/// A read counts only in a file that can see the declaration: its own file,
/// a part of the same library, or one that reaches it through imports and
/// exports. There, a private member is read only in its own library; a
/// top-level declaration is read by name, or through an import prefix; a
/// static member as `Owner.member` or `prefix.Owner.member`, or bare inside
/// its own class; an instance member through any object other than `super`,
/// or bare inside its own class. A named argument's label and the declaration
/// itself are not reads.
Map<String, Map<String, int>> readersOf(
  List<PlatformCapability> capabilities,
  List<GateSource> sources,
) {
  final Map<String, GateSource> byPath = <String, GateSource>{
    for (final GateSource s in sources) s.path: s,
  };
  final Map<String, String> libraries = <String, String>{
    for (final GateSource s in sources) s.path: libraryOf(s, byPath),
  };
  final Map<String, bool> instance = <String, bool>{
    for (final PlatformCapability c in capabilities)
      '${c.path} ${c.site}':
          byPath[c.path] != null && isInstanceMember(byPath[c.path]!, c.site),
  };
  final Map<String, Map<String, int>> found = <String, Map<String, int>>{
    for (final PlatformCapability c in capabilities)
      '${c.path} ${c.site}': <String, int>{},
  };
  for (final GateSource source in sources) {
    final Set<String> visible = visibleFrom(source, byPath);
    source.unit.accept(
      _ReaderVisitor(
        source,
        <PlatformCapability>[
          for (final PlatformCapability c in capabilities)
            if (visible.contains(c.path)) c,
        ],
        instance,
        found,
        libraries,
      ),
    );
  }
  return found;
}

class _ReaderVisitor extends CodeVisitor {
  _ReaderVisitor(
    this.source,
    this.capabilities,
    this.instance,
    this.found,
    this.libraries,
  );

  final GateSource source;
  final List<PlatformCapability> capabilities;
  final Map<String, bool> instance;
  final Map<String, Map<String, int>> found;
  final Map<String, String> libraries;

  @override
  void visitSimpleIdentifier(SimpleIdentifier node) {
    for (final PlatformCapability c in capabilities) {
      if (c.site == '<directives>' || node.name != c.member) continue;
      if (_reads(node, c)) {
        final Map<String, int> readers = found['${c.path} ${c.site}']!;
        final String key = '${source.path} ${siteOf(node)}';
        readers[key] = (readers[key] ?? 0) + 1;
      }
    }
    super.visitSimpleIdentifier(node);
  }

  bool _reads(SimpleIdentifier node, PlatformCapability c) {
    final bool sameFile = source.path == c.path;
    final bool sameLibrary =
        (libraries[source.path] ?? source.path) ==
        (libraries[c.path] ?? c.path);
    if (c.member.startsWith('_') && !sameLibrary) return false;
    if (sameFile && siteOf(node) == c.site) return false;
    final AstNode? parent = node.parent;
    if (parent is Label) return false;
    final Expression? target = switch (parent) {
      PrefixedIdentifier(:final SimpleIdentifier prefix)
          when parent.identifier == node =>
        prefix,
      PropertyAccess(:final Expression? target)
          when parent.propertyName == node =>
        target,
      MethodInvocation(:final Expression? target)
          when parent.methodName == node =>
        target,
      _ => null,
    };
    if (target is SuperExpression) return false;
    // Bare, a top-level declaration is read by name anywhere; a class member
    // only inside its own class, since a local of the same name elsewhere is
    // not it.
    if (target == null) {
      return c.owner == null ||
          (sameFile && siteOf(node).startsWith('${c.owner}.'));
    }
    // A top-level declaration reached through an import prefix.
    if (c.owner == null) return target is SimpleIdentifier;
    if (instance['${c.path} ${c.site}']!) return true;
    // `Owner.member`, or `prefix.Owner.member` through an import prefix.
    return (target is SimpleIdentifier && target.name == c.owner) ||
        (target is PrefixedIdentifier && target.identifier.name == c.owner);
  }
}
