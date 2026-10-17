// What the source gates added on 2026-10-17 share: the files they read, read
// as Dart syntax trees, and the questions they ask of a tree.
//
// The first version of these gates read text through a mask, and the review
// of PR #358 showed what text cannot see: a comment between `Platform` and
// `.isIOS`, a hex literal, a second declarator, an identifier inside a string
// interpolation, a directive split by a comment. A syntax tree from
// `package:analyzer` reads each of those the way the compiler reads them, so
// the gates ask the tree.

import 'dart:io';

import 'package:analyzer/dart/analysis/results.dart';
import 'package:analyzer/dart/analysis/utilities.dart';
import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/token.dart';
import 'package:analyzer/dart/ast/visitor.dart';
import 'package:analyzer/diagnostic/diagnostic.dart';
import 'package:flutter_test/flutter_test.dart';

/// One Dart file a gate reads: the path a reviewer opens, its text and its
/// syntax tree.
class GateSource {
  /// Parses [text] as the file at [path].
  GateSource(this.path, this.text) {
    final ParseStringResult result = parseString(
      content: text,
      path: '/gate/$path',
      throwIfDiagnostics: false,
    );
    unit = result.unit;
    errors = result.errors;
  }

  /// The path relative to the application root, `lib/src/...`.
  final String path;

  /// The file as it is on disk.
  final String text;

  /// Its syntax tree.
  late final CompilationUnit unit;

  /// The syntax errors the parser reported; a gate cannot trust a tree that
  /// has any.
  late final List<Diagnostic> errors;

  /// The 1-based line of [offset].
  int lineOf(int offset) => unit.lineInfo.getLocation(offset).lineNumber;
}

/// Every Dart file under `lib/` of the application at [base], by path relative
/// to [base], sorted.
///
/// [base] is the application root, which is where `flutter test` runs. A test
/// that plants a violation passes a temporary directory laid out the same way,
/// so the gate it proves is the gate that runs, not a copy of it.
List<GateSource> libSources({String base = '.'}) {
  final Directory lib = Directory(base == '.' ? 'lib' : '$base/lib');
  expect(
    lib.existsSync(),
    isTrue,
    reason:
        'run this test from the application root; looked in '
        '${lib.absolute.path}',
  );
  final int strip = base == '.' ? 0 : base.length + 1;
  return <GateSource>[
    for (final FileSystemEntity entity in lib.listSync(recursive: true))
      if (entity is File && entity.path.endsWith('.dart'))
        GateSource(entity.path.substring(strip), entity.readAsStringSync()),
  ]..sort((GateSource a, GateSource b) => a.path.compareTo(b.path));
}

/// Every Dart file the product ships from the application at [base]: its own
/// `lib/` and the `lib/` of every package it keeps under `packages/`, the
/// design system's among them, by path relative to [base], sorted. A
/// Cupertino widget or a platform fork wrapped in a `Ui*` component, or in a
/// new package of the application's own, would otherwise reach the app with
/// no token in it. `third_party/` holds upstream code the application vendors
/// with its provenance, and is not read.
List<GateSource> productSources({String base = '.'}) {
  final Directory packages = Directory(
    base == '.' ? 'packages' : '$base/packages',
  );
  final int strip = base == '.' ? 0 : base.length + 1;
  return <GateSource>[
    ...libSources(base: base),
    if (packages.existsSync())
      for (final FileSystemEntity package in packages.listSync())
        if (package is Directory &&
            Directory('${package.path}/lib').existsSync())
          for (final FileSystemEntity entity in Directory(
            '${package.path}/lib',
          ).listSync(recursive: true))
            if (entity is File && entity.path.endsWith('.dart'))
              GateSource(
                entity.path.substring(strip),
                entity.readAsStringSync(),
              ),
  ]..sort((GateSource a, GateSource b) => a.path.compareTo(b.path));
}

/// Writes [files], path to text, under a new temporary application root and
/// returns the root. The directory is deleted when the test ends.
String plantedApplication(Map<String, String> files) {
  final Directory root = Directory.systemTemp.createTempSync('planted_gate_');
  addTearDown(() => root.deleteSync(recursive: true));
  files.forEach((String path, String text) {
    File('${root.path}/$path')
      ..createSync(recursive: true)
      ..writeAsStringSync(text);
  });
  return root.path;
}

/// The declaration [node] sits in, as a reviewer names it: `Class.member`,
/// `function`, `Class` for a class-level initializer, or `<directives>` for an
/// import or export.
String siteOf(AstNode node) {
  String? member;
  String? container;
  for (AstNode? n = node; n != null; n = n.parent) {
    if (n is Directive) return '<directives>';
    if (member == null) {
      if (n is MethodDeclaration) {
        member = n.name.lexeme;
      } else if (n is ConstructorDeclaration) {
        member = n.name?.lexeme ?? '<constructor>';
      } else if (n is FieldDeclaration) {
        member = n.fields.variables.map((v) => v.name.lexeme).join(',');
      } else if (n is FunctionDeclaration && n.parent is CompilationUnit) {
        return n.name.lexeme;
      } else if (n is TopLevelVariableDeclaration) {
        return n.variables.variables.map((v) => v.name.lexeme).join(',');
      }
    }
    if (n is ClassDeclaration) container = n.namePart.typeName.lexeme;
    if (n is MixinDeclaration) container = n.name.lexeme;
    if (n is EnumDeclaration) container = n.namePart.typeName.lexeme;
    if (n is ExtensionDeclaration) container = n.name?.lexeme ?? '<extension>';
    if (n is ExtensionTypeDeclaration) {
      container = n.primaryConstructor.typeName.lexeme;
    }
    if (container != null) {
      return member == null ? container : '$container.$member';
    }
  }
  return member ?? '<top>';
}

/// A visitor over code alone: a doc comment's `[name]` references are prose,
/// not uses, so comments are not visited.
class CodeVisitor extends RecursiveAstVisitor<void> {
  @override
  void visitComment(Comment node) {}
}

/// The numeric constants a file declares, by `name` and `Class.name`: every
/// `const` or `final` variable whose initializer is a number the gate can
/// evaluate. Later declarations of the same name do not replace earlier ones.
Map<String, Expression> numericConstants(CompilationUnit unit) {
  final Map<String, Expression> found = <String, Expression>{};
  unit.accept(_ConstantCollector(found));
  return found;
}

class _ConstantCollector extends CodeVisitor {
  _ConstantCollector(this.found);

  final Map<String, Expression> found;

  @override
  void visitVariableDeclaration(VariableDeclaration node) {
    final Expression? initializer = node.initializer;
    final AstNode? list = node.parent;
    if (initializer != null &&
        list is VariableDeclarationList &&
        (list.isConst || list.isFinal)) {
      final String name = node.name.lexeme;
      found.putIfAbsent(name, () => initializer);
      final ClassDeclaration? owner = list.parent is FieldDeclaration
          ? node.thisOrAncestorOfType<ClassDeclaration>()
          : null;
      if (owner != null) {
        found.putIfAbsent(
          '${owner.namePart.typeName.lexeme}.$name',
          () => initializer,
        );
      }
    }
    super.visitVariableDeclaration(node);
  }
}

/// The value of [expression] when it is a number written in literals,
/// operators and the [constants] of its file, or null.
///
/// When [literalsOnly] is true a name is not followed, so the answer is
/// whether the expression itself is all numbers.
num? numberOf(
  Expression expression, {
  Map<String, Expression> constants = const <String, Expression>{},
  bool literalsOnly = false,
  Set<String>? following,
}) {
  final Set<String> seen = following ?? <String>{};
  num? of(Expression e) => numberOf(
    e,
    constants: constants,
    literalsOnly: literalsOnly,
    following: seen,
  );
  switch (expression) {
    case IntegerLiteral(:final int? value):
      return value;
    case DoubleLiteral(:final double value):
      return value;
    case ParenthesizedExpression(:final Expression expression):
      return of(expression);
    case PrefixExpression(:final Token operator, :final Expression operand)
        when operator.type == TokenType.MINUS:
      final num? value = of(operand);
      return value == null ? null : -value;
    case BinaryExpression(
      :final Expression leftOperand,
      :final Token operator,
      :final Expression rightOperand,
    ):
      final num? left = of(leftOperand);
      final num? right = of(rightOperand);
      if (left == null || right == null) return null;
      switch (operator.type) {
        case TokenType.PLUS:
          return left + right;
        case TokenType.MINUS:
          return left - right;
        case TokenType.STAR:
          return left * right;
        case TokenType.SLASH:
          return right == 0 ? null : left / right;
        case TokenType.TILDE_SLASH:
          return right == 0 ? null : left ~/ right;
        default:
          return null;
      }
    case SimpleIdentifier(:final String name) when !literalsOnly:
      return _follow(name, constants, seen, of);
    case PrefixedIdentifier(:final String name) when !literalsOnly:
      return _follow(name, constants, seen, of);
    default:
      return null;
  }
}

num? _follow(
  String name,
  Map<String, Expression> constants,
  Set<String> seen,
  num? Function(Expression) of,
) {
  final Expression? target = constants[name];
  if (target == null || !seen.add(name)) return null;
  return of(target);
}

/// Every numeric literal inside [node], in source order.
List<Literal> numericLiteralsIn(AstNode node) {
  final List<Literal> found = <Literal>[];
  node.accept(_LiteralCollector(found));
  return found;
}

class _LiteralCollector extends CodeVisitor {
  _LiteralCollector(this.found);

  final List<Literal> found;

  @override
  void visitIntegerLiteral(IntegerLiteral node) => found.add(node);

  @override
  void visitDoubleLiteral(DoubleLiteral node) => found.add(node);
}

/// The value of a numeric literal node.
num literalValue(Literal literal) => switch (literal) {
  IntegerLiteral(:final int? value) => value ?? 0,
  DoubleLiteral(:final double value) => value,
  _ => throw ArgumentError('not a numeric literal: $literal'),
};

/// The comments attached to [node] as an entry of a list, set, map or
/// argument list: the ones on its own lines before it, any inside it, and the
/// one that follows it on its last line, after its comma.
///
/// A comment after an entry's comma on the same line is that entry's, never
/// the next one's, so `'a', // owner-approved: ...` approves `'a'`.
List<String> commentsOf(AstNode node, CompilationUnit unit) {
  int line(int offset) => unit.lineInfo.getLocation(offset).lineNumber;
  final List<String> found = <String>[];
  final Token first = node.beginToken;
  final int previousLine = first.previous == null || first.previous!.isEof
      ? 0
      : line(first.previous!.end);
  for (Token? c = first.precedingComments; c != null; c = c.next) {
    if (line(c.offset) > previousLine) found.add(c.lexeme);
  }
  for (Token t = first.next!; t != node.endToken.next; t = t.next!) {
    for (Token? c = t.precedingComments; c != null; c = c.next) {
      found.add(c.lexeme);
    }
  }
  // After it on its last line, past its comma and any closing brackets and
  // the statement's end: a comment there is the last entry's on that line.
  const Set<TokenType> closers = <TokenType>{
    TokenType.COMMA,
    TokenType.CLOSE_CURLY_BRACKET,
    TokenType.CLOSE_SQUARE_BRACKET,
    TokenType.CLOSE_PAREN,
    TokenType.SEMICOLON,
  };
  final int lastLine = line(node.end);
  Token after = node.endToken.next!;
  while (true) {
    for (Token? c = after.precedingComments; c != null; c = c.next) {
      if (line(c.offset) == lastLine) found.add(c.lexeme);
    }
    if (after.isEof ||
        !closers.contains(after.type) ||
        line(after.offset) != lastLine) {
      break;
    }
    after = after.next!;
  }
  return found;
}

/// The comments attached to a top-level declaration: its doc comment, the
/// comments before it, and one after it on its last line.
List<String> declarationCommentsOf(
  AnnotatedNode declaration,
  CompilationUnit unit,
) {
  int line(int offset) => unit.lineInfo.getLocation(offset).lineNumber;
  final List<String> found = <String>[
    if (declaration.documentationComment case final Comment doc)
      for (final Token t in doc.tokens) t.lexeme,
  ];
  for (
    Token? c = declaration.firstTokenAfterCommentAndMetadata.precedingComments;
    c != null;
    c = c.next
  ) {
    found.add(c.lexeme);
  }
  final Token after = declaration.endToken.next!;
  for (Token? c = after.precedingComments; c != null; c = c.next) {
    if (line(c.offset) == line(declaration.end)) found.add(c.lexeme);
  }
  return found;
}
