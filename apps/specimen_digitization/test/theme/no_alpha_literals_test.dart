// The opacity literal gate (10 section 8, `no_alpha_literals`).
//
// `no_color_literals_test.dart` counts `Color(0x`. A role with an opacity typed
// over it, `ui.color.ink.withValues(alpha: .06)`, passed it, and is the same
// thing: a colour nobody named, which a mode, a contrast check or a later
// palette change cannot reach. The colour belongs in the theme as a role or an
// opacity token.
//
// The gate reads each file as a syntax tree, so comments between tokens and
// hex spellings change nothing. An opacity is the `alpha:` of `withValues` or
// `Color.from`, the argument of `withOpacity`, `withAlpha` or the design
// system's `stateLayer`, the alpha of `Color.fromARGB`, `Color.fromRGBO`,
// `HSLColor.fromAHSL` and `HSVColor.fromAHSV`, and the amount of
// `Color.lerp`, which mixes two roles into a third nobody named. Each number
// written in one counts, whatever its value, because the brief counts
// literals: `alpha: 0` is the role at nothing, and the design system's
// transparent role says that with a name. A name for the number is the
// number: a constant, a final, or a getter, function or method with no
// parameters that returns one expression, in the same file, a public one
// anywhere in the application (`Washes.selected`), or the default of the
// parameter it is read in (`{double wash = .06}`). A number passed in from a
// caller, and one from outside the application, are review's. Not read: any
// `opacity:` argument (`Opacity`, `AnimatedOpacity`, `FadeTransition`,
// `Image` and the rest), where the tree today holds visibility toggles
// (`visible ? 1 : 0`) and animations; a fraction there over a coloured child
// is the same decision, and review catches it.
//
// The mechanism is the geometry gate's: a per-file count that may go down,
// never up, held to the tree exactly, and a file at zero leaves the map. It
// reads every file under `lib/`; the package's foundation, where a role and
// its opacity are defined, is the package's own.

import 'package:analyzer/dart/ast/ast.dart';
import 'package:flutter_test/flutter_test.dart';

import 'gate_support.dart';

/// Per-file counts on 2026-10-17, when the gate was written. Shrink only.
///
/// Three: the shade the capture screen paints outside the crop, and two roles
/// faded to nothing (`alpha: 0`) in the router's page and the queue's filter
/// control. The fourth, the wash under the selected destination in the
/// shell's rail, left when the shell moved onto `specimen_ui` (PR #359).
const Map<String, int> alphaLiteralBacklog = <String, int>{
  'lib/src/app/app_router.dart': 1,
  'lib/src/capture/capture_screen.dart': 1,
  'lib/src/screens/queue/queue_screen.dart': 1,
};

/// One opacity written as a number.
class OpacityLiteral {
  /// Records [text], the number or the name of one, at [line] in [site],
  /// written in [call].
  const OpacityLiteral(this.line, this.site, this.call, this.text);

  /// The line.
  final int line;

  /// The declaration it is in.
  final String site;

  /// Where the opacity goes: `alpha:`, `withOpacity`, `Color.lerp` and so on.
  final String call;

  /// The number as written, or `name = number`.
  final String text;

  @override
  String toString() => 'line $line, $site, $call $text';
}

/// Every opacity written as a number in [source]. A name is resolved in
/// [source] first, then among the public names of [pool], the rest of the
/// application.
List<OpacityLiteral> opacityLiteralsIn(
  GateSource source, {
  Map<String, Expression> pool = const <String, Expression>{},
}) {
  final _OpacityVisitor visitor = _OpacityVisitor(source, <String, Expression>{
    ...pool,
    ...numberNames(source.unit),
  });
  source.unit.accept(visitor);
  return visitor.found;
}

/// The names [unit] gives a number: its constants and finals, and its
/// getters, functions and methods with no parameters that return one
/// expression, by `name` and `Class.name`, as the named pixel gate reads them.
Map<String, Expression> numberNames(CompilationUnit unit) {
  final Map<String, Expression> found = numericConstants(unit);
  bool bare(FormalParameterList? parameters) =>
      parameters == null || parameters.parameters.isEmpty;
  for (final CompilationUnitMember d in unit.declarations) {
    if (d is FunctionDeclaration && bare(d.functionExpression.parameters)) {
      final FunctionBody body = d.functionExpression.body;
      if (body is ExpressionFunctionBody) {
        found.putIfAbsent(d.name.lexeme, () => body.expression);
      }
    }
    if (d is ClassDeclaration && d.body is BlockClassBody) {
      for (final ClassMember m in (d.body as BlockClassBody).members) {
        if (m is MethodDeclaration &&
            bare(m.parameters) &&
            m.body is ExpressionFunctionBody) {
          final Expression e = (m.body as ExpressionFunctionBody).expression;
          found.putIfAbsent(m.name.lexeme, () => e);
          found.putIfAbsent(
            '${d.namePart.typeName.lexeme}.${m.name.lexeme}',
            () => e,
          );
        }
      }
    }
  }
  return found;
}

/// The public names every file in [sources] gives a number, pooled.
Map<String, Expression> publicNumberNames(
  List<GateSource> sources,
) => <String, Expression>{
  for (final GateSource s in sources)
    for (final MapEntry<String, Expression> e in numberNames(s.unit).entries)
      if (!e.key.split('.').any((String part) => part.startsWith('_')))
        e.key: e.value,
};

class _OpacityVisitor extends CodeVisitor {
  _OpacityVisitor(this.source, this.constants);

  final GateSource source;
  final Map<String, Expression> constants;
  final List<OpacityLiteral> found = <OpacityLiteral>[];

  void _check(Expression value, String call) {
    final List<Literal> literals = numericLiteralsIn(value);
    for (final Literal literal in literals) {
      found.add(
        OpacityLiteral(
          source.lineOf(literal.offset),
          siteOf(literal),
          call,
          literal.toSource(),
        ),
      );
    }
    if (literals.isNotEmpty) return;
    // A function or method with no parameters is a name for what it returns,
    // `fade()` or `Washes.row()`.
    final Expression? called = switch (value) {
      MethodInvocation(
        :final Expression? target,
        :final SimpleIdentifier methodName,
        :final ArgumentList argumentList,
      )
          when argumentList.arguments.isEmpty &&
              (target == null || target is SimpleIdentifier) =>
        constants[target == null
            ? methodName.name
            : '${(target as SimpleIdentifier).name}.${methodName.name}'],
      _ => null,
    };
    if (called != null) {
      final num? named = numberOf(called, constants: constants);
      if (named != null) {
        found.add(
          OpacityLiteral(
            source.lineOf(value.offset),
            siteOf(value),
            call,
            '${value.toSource()} = $named',
          ),
        );
      }
      return;
    }
    if (value is SimpleIdentifier || value is PrefixedIdentifier) {
      final num? named =
          numberOf(value, constants: constants) ?? _parameterDefault(value);
      if (named != null) {
        found.add(
          OpacityLiteral(
            source.lineOf(value.offset),
            siteOf(value),
            call,
            '${value.toSource()} = $named',
          ),
        );
      }
    }
  }

  Expression? _named(ArgumentList arguments, String name) => arguments.arguments
      .whereType<NamedExpression>()
      .where((NamedExpression e) => e.name.label.name == name)
      .firstOrNull
      ?.expression;

  Expression? _positional(ArgumentList arguments, int index) {
    final List<Expression> positional = <Expression>[
      for (final Expression a in arguments.arguments)
        if (a is! NamedExpression) a,
    ];
    return index < positional.length ? positional[index] : null;
  }

  /// The default of the parameter [value] names, `{double wash = .06}`, in
  /// the function it is read in.
  num? _parameterDefault(Expression value) {
    if (value is! SimpleIdentifier) return null;
    for (AstNode? n = value.parent; n != null; n = n.parent) {
      final FormalParameterList? parameters = switch (n) {
        FunctionExpression(:final FormalParameterList? parameters) =>
          parameters,
        MethodDeclaration(:final FormalParameterList? parameters) => parameters,
        ConstructorDeclaration(:final FormalParameterList parameters) =>
          parameters,
        _ => null,
      };
      for (final FormalParameter p in parameters?.parameters ?? const []) {
        if (p is DefaultFormalParameter &&
            p.name?.lexeme == value.name &&
            p.defaultValue != null) {
          return numberOf(p.defaultValue!, constants: constants);
        }
      }
    }
    return null;
  }

  void _colorConstructor(String name, ArgumentList arguments) {
    final Expression? alpha = switch (name) {
      'fromARGB' => _positional(arguments, 0),
      'fromRGBO' => _positional(arguments, 3),
      'from' => _named(arguments, 'alpha'),
      'lerp' => _positional(arguments, 2),
      _ => null,
    };
    if (alpha != null) _check(alpha, 'Color.$name');
  }

  @override
  void visitMethodInvocation(MethodInvocation node) {
    final String method = node.methodName.name;
    final ArgumentList arguments = node.argumentList;
    final Expression? target = node.target;
    if (target is SimpleIdentifier && target.name == 'Color') {
      _colorConstructor(method, arguments);
    } else if (target is SimpleIdentifier &&
        (target.name == 'HSLColor' || target.name == 'HSVColor') &&
        method.startsWith('fromA')) {
      final Expression? alpha = _positional(arguments, 0);
      if (alpha != null) _check(alpha, '${target.name}.$method');
    } else if (method == 'withValues') {
      final Expression? alpha = _named(arguments, 'alpha');
      if (alpha != null) _check(alpha, 'alpha:');
    } else if (method == 'withOpacity' ||
        method == 'withAlpha' ||
        method == 'stateLayer') {
      final Expression? value = _positional(arguments, 0);
      if (value != null) _check(value, method);
    }
    super.visitMethodInvocation(node);
  }

  @override
  void visitInstanceCreationExpression(InstanceCreationExpression node) {
    // `const Color.fromRGBO(...)` names its class as the type; written
    // without `const`, the parser may read the class as an import prefix.
    final ConstructorName constructor = node.constructorName;
    final String? type = constructor.name != null
        ? constructor.type.name.lexeme
        : constructor.type.importPrefix?.name.lexeme;
    final String? named =
        constructor.name?.name ??
        (constructor.type.importPrefix == null
            ? null
            : constructor.type.name.lexeme);
    if (type == 'Color' && named != null) {
      _colorConstructor(named, node.argumentList);
    } else if ((type == 'HSLColor' || type == 'HSVColor') &&
        named != null &&
        named.startsWith('fromA')) {
      final Expression? alpha = _positional(node.argumentList, 0);
      if (alpha != null) _check(alpha, '$type.$named');
    }
    super.visitInstanceCreationExpression(node);
  }
}

/// Every file under `lib/` of the application at [base] that writes an
/// opacity as a number, with its findings.
Map<String, List<OpacityLiteral>> alphaLiteralCensus({String base = '.'}) {
  final Map<String, List<OpacityLiteral>> found =
      <String, List<OpacityLiteral>>{};
  final List<GateSource> sources = libSources(base: base);
  final Map<String, Expression> pool = publicNumberNames(sources);
  for (final GateSource source in sources) {
    final List<OpacityLiteral> findings = opacityLiteralsIn(source, pool: pool);
    if (findings.isNotEmpty) found[source.path] = findings;
  }
  return found;
}

/// What the gate objects to in [census]: a file not in the backlog, or one
/// that holds more than its count.
List<String> alphaLiteralViolations(Map<String, List<OpacityLiteral>> census) {
  final List<String> found = <String>[];
  census.forEach((String path, List<OpacityLiteral> findings) {
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
  List<String> of(String text) => <String>[
    for (final OpacityLiteral o in opacityLiteralsIn(
      GateSource('x.dart', text),
    ))
      '${o.call} ${o.text}',
  ];

  test('the scanner reads an opacity the way the compiler does', () {
    expect(of('final c = ui.color.ink.withValues(alpha: .06);'), <String>[
      'alpha: .06',
    ]);
    expect(of('final c = ink./* overlay */withValues(alpha: .06);'), <String>[
      'alpha: .06',
    ]);
    expect(of('final c = ink.withValues(alpha: 0x1 / 0x10);'), <String>[
      'alpha: 0x1',
      'alpha: 0x10',
    ]);
    expect(of('final c = ink.withValues(red: r, alpha: t * 0.5);'), <String>[
      'alpha: 0.5',
    ]);
    expect(of('final c = ink.withValues(alpha: 0);'), <String>['alpha: 0']);
    expect(of('final c = ink.withOpacity(0.4);'), <String>['withOpacity 0.4']);
    expect(of('final c = ink.withAlpha(0x80);'), <String>['withAlpha 0x80']);
    expect(of('final c = ui.color.stateLayer(.06);'), <String>[
      'stateLayer .06',
    ]);
    expect(of('final c = Color.fromRGBO(0, 0, 0, .06);'), <String>[
      'Color.fromRGBO .06',
    ]);
    expect(of('final c = const Color.fromARGB(20, 0, 0, 0);'), <String>[
      'Color.fromARGB 20',
    ]);
    expect(of('final c = Color.lerp(ui.color.ink, paper, .06);'), <String>[
      'Color.lerp .06',
    ]);
    expect(
      of(
        'const opacity = .06;\n'
        'final c = ink.withValues(alpha: opacity);',
      ),
      <String>['alpha: opacity = 0.06'],
    );
    expect(
      of(
        'class _S { static const double wash = .06; }\n'
        'final c = ink.withValues(alpha: _S.wash);',
      ),
      <String>['alpha: _S.wash = 0.06'],
    );

    expect(
      of(
        'class _S { static double get wash => .06; }\n'
        'final c = ink.withValues(alpha: _S.wash);',
      ),
      <String>['alpha: _S.wash = 0.06'],
    );
    expect(
      of(
        'Color tint(Color ink, {double wash = .06}) => ink.withOpacity(wash);',
      ),
      <String>['withOpacity wash = 0.06'],
    );
    expect(of('final c = HSLColor.fromAHSL(.4, 0, 0, .5);'), <String>[
      'HSLColor.fromAHSL .4',
    ]);
    expect(
      of('Color c() => const HSLColor.fromAHSL(.06, 0, 0, .5).toColor();'),
      <String>['HSLColor.fromAHSL .06'],
    );
    expect(of('final c = const HSVColor.fromAHSV(.2, 0, 0, 1);'), <String>[
      'HSVColor.fromAHSV .2',
    ]);
    expect(of('const Color c = Color.fromRGBO(0, 0, 0, .06);'), <String>[
      'Color.fromRGBO .06',
    ]);
    expect(
      of(
        'double fade() => .06;\n'
        'class _S { static double row() => .1; }\n'
        'final a = ink.withValues(alpha: fade());\n'
        'final b = ink.withOpacity(_S.row());',
      ),
      <String>['alpha: fade() = 0.06', 'withOpacity _S.row() = 0.1'],
    );

    // A token, a value from an animation, another channel and prose are not
    // opacities written as numbers.
    expect(
      of('final c = ui.color.stateLayer(ui.color.hoverOpacity);'),
      isEmpty,
    );
    expect(of('final c = Color.lerp(a, b, animation.value);'), isEmpty);
    expect(of('final c = ink.withValues(red: 0.5);'), isEmpty);
    expect(
      of('final c = ink.withValues(alpha: GroundPalette.scrimOpacity);'),
      isEmpty,
    );
    expect(of('// ink.withValues(alpha: .06)\nvoid f() {}'), isEmpty);
  });

  test('a planted opacity fails the gate', () {
    // The same census and verdict the gate runs, over a temporary
    // application: a new file with a typed opacity, a backlog file that
    // gained a second one, and an opacity named in another file.
    final String base = plantedApplication(<String, String>{
      'lib/src/widgets/hover.dart':
          'Color wash(UiThemeData ui) => ui.color.ink.withValues(alpha: .08);\n',
      'lib/src/app/shell.dart':
          'final Color a = ink.withValues(alpha: .06);\n'
          'final Color b = ink.withOpacity(.12);\n',
      // A public name in one file, the opacity in another.
      'lib/src/washes.dart':
          'abstract final class Washes { static const double row = .1; }\n',
      'lib/src/widgets/row_wash.dart':
          'Color wash(Color ink) => ink.withValues(alpha: Washes.row);\n',
    });
    expect(alphaLiteralViolations(alphaLiteralCensus(base: base)), <String>[
      'lib/src/app/shell.dart holds 2, allowed '
          '${alphaLiteralBacklog['lib/src/app/shell.dart'] ?? 0}:\n'
          '    line 1, a, alpha: .06\n'
          '    line 2, b, withOpacity .12',
      'lib/src/widgets/hover.dart holds 1, allowed 0:\n'
          '    line 1, wash, alpha: .08',
      'lib/src/widgets/row_wash.dart holds 1, allowed 0:\n'
          '    line 1, wash, alpha: Washes.row = 0.1',
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
    final Map<String, List<OpacityLiteral>> census = alphaLiteralCensus();
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
