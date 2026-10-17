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
  _PlatformVisitor(this.source);

  final GateSource source;
  final List<PlatformCheck> found = <PlatformCheck>[];

  void _add(AstNode node, String kind) =>
      found.add(PlatformCheck(source.lineOf(node.offset), siteOf(node), kind));

  @override
  void visitSimpleIdentifier(SimpleIdentifier node) {
    switch (node.name) {
      case webFlag || targetPlatform || platformOverride:
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
        target is MethodInvocation &&
        target.methodName.name == 'of' &&
        target.target is SimpleIdentifier &&
        (target.target! as SimpleIdentifier).name == 'Theme') {
      _add(node, themePlatform);
    }
    super.visitPropertyAccess(node);
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

/// Where each of [capabilities] is read in [sources], `path site` to count.
///
/// A private member is read only in its own file. A top-level declaration is
/// read by name anywhere. A static member is read as `Owner.member`, or bare
/// inside its own file. An instance member is read through any object other
/// than `super`, or bare inside its own file. A named argument's label and the
/// declaration itself are not reads.
Map<String, Map<String, int>> readersOf(
  List<PlatformCapability> capabilities,
  List<GateSource> sources,
) {
  final Map<String, GateSource> byPath = <String, GateSource>{
    for (final GateSource s in sources) s.path: s,
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
    source.unit.accept(_ReaderVisitor(source, capabilities, instance, found));
  }
  return found;
}

class _ReaderVisitor extends CodeVisitor {
  _ReaderVisitor(this.source, this.capabilities, this.instance, this.found);

  final GateSource source;
  final List<PlatformCapability> capabilities;
  final Map<String, bool> instance;
  final Map<String, Map<String, int>> found;

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
    if (c.member.startsWith('_') && !sameFile) return false;
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
    return target is SimpleIdentifier && target.name == c.owner;
  }
}
