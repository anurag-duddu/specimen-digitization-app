// The named pixel gate's reader, kept apart from its test so the planted
// cases and the census share one definition.
//
// A named size is a number given a name and then used to lay something out:
// `static const double switcherMaxWidth = 280` followed by
// `SizedBox(width: switcherMaxWidth)`. The brief that asked for the gate says
// "values > 1 used for layout", so both halves are read from the syntax tree.
//
// The name. Every declarator of every variable declared `double` or `num`, or
// declared without a type and given a double (`final w = 280.0`), at the top
// level, as a field or as a local; a field given its value in a constructor's
// initializer list (`: width = 280`); a parameter's default, counted by its
// reads, in its body or its initializer list, or, for a `super.` parameter
// named for a dimension, by the superclass it is handed to; and every getter,
// and every method or function with no parameters, that returns `double` or
// `num` from one expression. An `int` counts through `.toDouble()`, and a
// list, map or record of sizes through an index or a field.
//
// The number. Its value is evaluated, so `0x118`, `280 * 1` and `35 * 8` are
// the sizes they are. A number that multiplies a value or divides one is a
// factor in a derivation, `targetMin * 2`, and is not a size; a list index is
// not either. A size is a number above 1, the brief's threshold.
//
// The use. The name is used for layout when one of its reads reaches, through
// arithmetic, a conditional, a switch's case, `min`, `max`, `clamp` or
// rounding: an argument or
// a variable whose name holds a dimension word (`width`, `maxHeight`,
// `heightCap`, `padding`, `cornerRadius`, an edge such as `top`); an argument
// of a geometry constructor (`EdgeInsets`, `BoxConstraints`, `Size`,
// `Offset`, `Radius`, `BorderRadius`, `SizedBox`, `Rect`, `Positioned`,
// `ConstrainedBox`, `LimitedBox`, `Padding`); a comparison or a sum with a
// measured size (`constraints.maxWidth`, an `available` width, a `distance`,
// or a local initialised from one); or another named size. A number used only
// for a timeout, a zoom limit, a gesture's travel ratio or a count is not a
// layout decision and is not counted. A size declared and never read is not
// counted until something reads it.
//
// Not read, and left to review: an enum's constructor arguments
// (`wide(280)`), an assignment or a cascade (`..strokeWidth = stroke`), a
// constructor not named above (`FixedColumnWidth`), and an `int` turned into
// a double other than by `.toDouble()` (`rail * 1.0`).

import 'package:analyzer/dart/ast/ast.dart';
import 'package:analyzer/dart/ast/token.dart';

import 'gate_support.dart';

/// The brief's threshold: a size is a number above this.
const num namedSizeFloor = 1;

/// Argument and variable names that carry a dimension: any name that
/// contains a dimension word (`width`, `maxHeight`, `heightCap`, `fontSize`,
/// `cornerRadius`), and the edge names of an inset.
final RegExp layoutName = RegExp(
  r'width|height|extent|radius|padding|margin|gap|spacing|inset|indent'
  r'|offset|size|thickness|elevation|dimension'
  r'|^(?:top|bottom|left|right|start|end|horizontal|vertical|all)$',
  caseSensitive: false,
);

/// Constructors and functions whose arguments are geometry.
const Set<String> geometryCalls = <String>{
  'BorderRadius',
  'BorderRadiusDirectional',
  'BoxConstraints',
  'ConstrainedBox',
  'EdgeInsets',
  'EdgeInsetsDirectional',
  'LimitedBox',
  'Offset',
  'Padding',
  'Positioned',
  'PositionedDirectional',
  'RRect',
  'Radius',
  'Rect',
  'Size',
  'SizedBox',
};

/// What the other side of a comparison or a sum names when it is a measured
/// size: the layout's constraints and sizes, an available width, a distance.
final RegExp measuredSize = RegExp(
  r'width|height|extent|constraints|sizeOf|\.size\b|biggest|smallest'
  r'|shortestSide|longestSide|offset|\bdx\b|\bdy\b|pixels|available'
  r'|distance',
  caseSensitive: false,
);

/// A design-system size: a spacing token such as `ui.space.s4`.
final RegExp _sizeToken = RegExp(r'\bspace\.\w+');

/// Whether [other] is a measured size: it names one, or it is a local or a
/// parameter of the enclosing functions whose name or initializer does.
bool _measured(Expression other) {
  if (measuredSize.hasMatch(other.toSource())) return true;
  if (other is! SimpleIdentifier) return false;
  for (AstNode? n = other.parent; n != null; n = n.parent) {
    if (n is FunctionExpression || n is MethodDeclaration) {
      final FormalParameterList? parameters = switch (n) {
        FunctionExpression(:final FormalParameterList? parameters) =>
          parameters,
        MethodDeclaration(:final FormalParameterList? parameters) => parameters,
        _ => null,
      };
      for (final FormalParameter p in parameters?.parameters ?? const []) {
        if (p.name?.lexeme == other.name) return false;
      }
    }
    if (n is Block) {
      for (final Statement st in n.statements) {
        if (st.offset >= other.offset) break;
        if (st is VariableDeclarationStatement) {
          for (final VariableDeclaration v in st.variables.variables) {
            if (v.name.lexeme == other.name) {
              return measuredSize.hasMatch(v.initializer?.toSource() ?? '');
            }
          }
        }
      }
    }
  }
  return false;
}

/// A named number: its declaration, its value expression and where it is.
class NamedNumber {
  /// Records [name], declared at [node] with [value], in the declaration
  /// [site], in the file [path], read as [kind].
  NamedNumber(
    this.path,
    this.name,
    this.site,
    this.node,
    this.value, {
    this.kind = NumberKind.value,
  });

  /// How it reaches layout.
  final NumberKind kind;

  /// The file.
  final String path;

  /// The name it is read by.
  final String name;

  /// The declaration it sits in, as [siteOf] names it.
  final String site;

  /// The declaring node: a variable declaration or a function or method.
  final AstNode node;

  /// The expression it holds or returns.
  final Expression value;

  /// The class it belongs to, or null.
  String? get owner => site.contains('.') ? site.split('.').first : null;
}

const Set<String> _sized = <String>{'double', 'num'};

/// How a named number is read.
enum NumberKind {
  /// A `double` or `num`: any read can reach layout.
  value,

  /// An `int`: it reaches layout only through `.toDouble()`, so a count that
  /// divides a width is not a size.
  integer,

  /// A list, set, map or record of `double` or `num`: an element reaches
  /// layout through an index or a field.
  collection,

  /// A parameter's default value: used for layout when the parameter is
  /// named for a dimension, or read on to layout in its body or its class.
  parameter,
}

bool _sizedType(TypeAnnotation? type) => switch (type) {
  NamedType(:final Token name) => _sized.contains(name.lexeme),
  _ => false,
};

/// Whether [type] is a list, set, map or record whose values are `double` or
/// `num`.
bool _sizedCollection(TypeAnnotation? type) => switch (type) {
  NamedType(:final Token name, :final TypeArgumentList? typeArguments) =>
    const <String>{'List', 'Set', 'Iterable', 'Map'}.contains(name.lexeme) &&
        typeArguments != null &&
        _sizedType(typeArguments.arguments.last),
  RecordTypeAnnotation(
    :final NodeList<RecordTypeAnnotationPositionalField> positionalFields,
    :final RecordTypeAnnotationNamedFields? namedFields,
  ) =>
    <TypeAnnotation>[
      for (final RecordTypeAnnotationPositionalField f in positionalFields)
        f.type,
      for (final RecordTypeAnnotationNamedField f
          in namedFields?.fields ?? const <RecordTypeAnnotationNamedField>[])
        f.type,
    ].any(_sizedType),
  _ => false,
};

/// Every named number [source] declares.
List<NamedNumber> namedNumbersIn(GateSource source) {
  final _NameVisitor visitor = _NameVisitor(source);
  source.unit.accept(visitor);
  return visitor.found;
}

class _NameVisitor extends CodeVisitor {
  _NameVisitor(this.source);

  final GateSource source;
  final List<NamedNumber> found = <NamedNumber>[];

  @override
  void visitVariableDeclaration(VariableDeclaration node) {
    final Expression? value = node.initializer;
    final AstNode? list = node.parent;
    if (value != null && list is VariableDeclarationList) {
      final TypeAnnotation? type = list.type;
      final num? literal = numberOf(value, literalsOnly: true);
      final bool typedLiteral = switch (value) {
        ListLiteral(:final TypeArgumentList? typeArguments) ||
        SetOrMapLiteral(
          :final TypeArgumentList? typeArguments,
        ) => typeArguments != null && _sizedType(typeArguments.arguments.last),
        RecordLiteral() => numericLiteralsIn(
          value,
        ).any((Literal l) => l is DoubleLiteral),
        _ => false,
      };
      final NumberKind? kind = _sizedType(type)
          ? NumberKind.value
          : type == null && literal is double
          ? NumberKind.value
          : (type is NamedType && type.name.lexeme == 'int') ||
                (type == null && literal is int)
          ? NumberKind.integer
          : _sizedCollection(type) || (type == null && typedLiteral)
          ? NumberKind.collection
          : null;
      if (kind != null) {
        found.add(
          NamedNumber(
            source.path,
            node.name.lexeme,
            siteOf(node),
            node,
            value,
            kind: kind,
          ),
        );
      }
    }
    super.visitVariableDeclaration(node);
  }

  @override
  void visitConstructorFieldInitializer(ConstructorFieldInitializer node) {
    // `const Box() : width = 280`, and `: _w = width` after a parameter's
    // default: the field's value, written in the constructor rather than at
    // the field.
    final TypeAnnotation? type = _fieldType(node);
    final NumberKind? kind = _sizedType(type)
        ? NumberKind.value
        : type is NamedType && type.name.lexeme == 'int'
        ? NumberKind.integer
        : null;
    if (kind != null) {
      found.add(
        NamedNumber(
          source.path,
          node.fieldName.name,
          siteOf(node),
          node,
          node.expression,
          kind: kind,
        ),
      );
    }
    super.visitConstructorFieldInitializer(node);
  }

  /// The declared type of the field [node] initialises, from its class.
  static TypeAnnotation? _fieldType(ConstructorFieldInitializer node) {
    final ClassBody? body = node.thisOrAncestorOfType<ClassDeclaration>()?.body;
    if (body is! BlockClassBody) return null;
    for (final ClassMember m in body.members) {
      if (m is FieldDeclaration &&
          m.fields.variables.any(
            (VariableDeclaration v) => v.name.lexeme == node.fieldName.name,
          )) {
        return m.fields.type;
      }
    }
    return null;
  }

  @override
  void visitDefaultFormalParameter(DefaultFormalParameter node) {
    final Expression? value = node.defaultValue;
    final NormalFormalParameter parameter = node.parameter;
    final bool sized = switch (parameter) {
      SimpleFormalParameter(:final TypeAnnotation? type) => _sizedType(type),
      FieldFormalParameter() || SuperFormalParameter() =>
        value != null && numberOf(value, literalsOnly: true) != null,
      _ => false,
    };
    final String? name = parameter.name?.lexeme;
    if (value != null && sized && name != null) {
      found.add(
        NamedNumber(
          source.path,
          name,
          siteOf(node),
          node,
          value,
          kind: NumberKind.parameter,
        ),
      );
    }
    super.visitDefaultFormalParameter(node);
  }

  void _function(
    AstNode node,
    String name,
    TypeAnnotation? returns,
    FormalParameterList? parameters,
    FunctionBody body,
  ) {
    if (returns is! NamedType || !_sized.contains(returns.name.lexeme)) return;
    if (parameters != null && parameters.parameters.isNotEmpty) return;
    final Expression? value = switch (body) {
      ExpressionFunctionBody(:final Expression expression) => expression,
      BlockFunctionBody(:final Block block)
          when block.statements.length == 1 &&
              block.statements.single is ReturnStatement =>
        (block.statements.single as ReturnStatement).expression,
      _ => null,
    };
    if (value != null) {
      found.add(NamedNumber(source.path, name, siteOf(node), node, value));
    }
  }

  @override
  void visitMethodDeclaration(MethodDeclaration node) {
    _function(
      node,
      node.name.lexeme,
      node.returnType,
      node.parameters,
      node.body,
    );
    super.visitMethodDeclaration(node);
  }

  @override
  void visitFunctionDeclaration(FunctionDeclaration node) {
    if (node.parent is CompilationUnit) {
      _function(
        node,
        node.name.lexeme,
        node.returnType,
        node.functionExpression.parameters,
        node.functionExpression.body,
      );
    }
    super.visitFunctionDeclaration(node);
  }
}

Expression _unwrap(AstNode node) {
  AstNode n = node;
  while (n.parent is ParenthesizedExpression) {
    n = n.parent!;
  }
  return n as Expression;
}

/// The sizes [value] writes: each largest part written in numbers alone whose
/// value is above the floor and that is neither a factor nor an index.
List<num> sizesIn(Expression value) {
  final List<num> found = <num>[];
  void visit(Expression e) {
    final num? number = numberOf(e, literalsOnly: true);
    if (number != null) {
      if (number.abs() <= namedSizeFloor) return;
      final Expression outer = _unwrap(e);
      final AstNode? parent = outer.parent;
      if (parent is IndexExpression && parent.index == outer) return;
      if (parent is BinaryExpression) {
        final Expression other = parent.leftOperand == outer
            ? parent.rightOperand
            : parent.leftOperand;
        final bool derived = numberOf(other, literalsOnly: true) == null;
        final TokenType op = parent.operator.type;
        final bool divisor =
            parent.rightOperand == outer &&
            (op == TokenType.SLASH || op == TokenType.TILDE_SLASH);
        if (derived && (op == TokenType.STAR || divisor)) return;
      }
      if (parent is ArgumentList &&
          parent.parent is MethodInvocation &&
          (parent.parent! as MethodInvocation).methodName.name == 'pow') {
        return;
      }
      found.add(number);
      return;
    }
    for (final Expression child in _children(e)) {
      visit(child);
    }
  }

  visit(value);
  return found;
}

List<Expression> _children(Expression e) => switch (e) {
  ParenthesizedExpression(:final Expression expression) => <Expression>[
    expression,
  ],
  BinaryExpression(
    :final Expression leftOperand,
    :final Expression rightOperand,
  ) =>
    <Expression>[leftOperand, rightOperand],
  PrefixExpression(:final Expression operand) => <Expression>[operand],
  ConditionalExpression(
    :final Expression condition,
    :final Expression thenExpression,
    :final Expression elseExpression,
  ) =>
    <Expression>[condition, thenExpression, elseExpression],
  MethodInvocation(
    :final Expression? target,
    :final ArgumentList argumentList,
  ) =>
    <Expression>[?target, ...argumentList.arguments],
  FunctionExpressionInvocation(:final ArgumentList argumentList) =>
    argumentList.arguments,
  InstanceCreationExpression(:final ArgumentList argumentList) =>
    argumentList.arguments,
  NamedExpression(:final Expression expression) => <Expression>[expression],
  AsExpression(:final Expression expression) => <Expression>[expression],
  PostfixExpression(:final Expression operand) => <Expression>[operand],
  PropertyAccess(:final Expression? target) => <Expression>[?target],
  // An index, and any arithmetic inside it, is a position in a list.
  IndexExpression(:final Expression? target) => <Expression>[?target],
  ListLiteral(:final NodeList<CollectionElement> elements) => <Expression>[
    for (final CollectionElement e in elements)
      if (e is Expression) e,
  ],
  SetOrMapLiteral(:final NodeList<CollectionElement> elements) => <Expression>[
    for (final CollectionElement e in elements)
      if (e is Expression) e else if (e is MapLiteralEntry) e.value,
  ],
  RecordLiteral(:final NodeList<Expression> fields) => fields.toList(),
  // A switch picks one of its cases' values; its patterns are not values.
  SwitchExpression(:final NodeList<SwitchExpressionCase> cases) => <Expression>[
    for (final SwitchExpressionCase c in cases) c.expression,
  ],
  _ => <Expression>[],
};

/// Whether the read [node] of a named number reaches a layout position, or
/// another named number for which [layoutOf] answers yes.
bool reachesLayout(
  SimpleIdentifier node,
  bool Function(AstNode declaration) layoutOf,
) {
  AstNode current = node;
  final AstNode? parent0 = node.parent;
  if (parent0 is IndexExpression && parent0.target == node) {
    // An element of a named collection, `widths[1]`.
    current = parent0;
  } else if (parent0 is PrefixedIdentifier &&
      parent0.prefix == node &&
      RegExp(r'^\$\d+$|^[a-z]').hasMatch(parent0.identifier.name) &&
      parent0.identifier.name != 'toDouble') {
    // A field of a named record, `size.$1` or `size.width`.
    current = parent0;
  } else if (node.parent is PrefixedIdentifier &&
      (node.parent! as PrefixedIdentifier).identifier == node) {
    current = node.parent!;
  } else if (node.parent is PropertyAccess &&
      (node.parent! as PropertyAccess).propertyName == node) {
    current = node.parent!;
  } else if (node.parent is MethodInvocation &&
      (node.parent! as MethodInvocation).methodName == node) {
    // A named number written as a method or function with no parameters.
    current = node.parent!;
  }
  while (true) {
    final AstNode? parent = current.parent;
    switch (parent) {
      case ParenthesizedExpression() ||
          PrefixExpression() ||
          AsExpression() ||
          PostfixExpression():
        current = parent!;
      case BinaryExpression(:final Token operator):
        final TokenType op = operator.type;
        if (op == TokenType.LT ||
            op == TokenType.LT_EQ ||
            op == TokenType.GT ||
            op == TokenType.GT_EQ) {
          final Expression other = parent.leftOperand == current
              ? parent.rightOperand
              : parent.leftOperand;
          return _measured(other);
        }
        if (op != TokenType.QUESTION_QUESTION) {
          // Beside a measured size or a spacing token the units decide: a
          // size plus or minus it makes it a size, and so does it divided by
          // a size; a size times it makes it a factor, `width * (1 - scale)`,
          // and a size divided by it is a count or a size, `width / ratio`,
          // so neither says it is one.
          final Expression other = parent.leftOperand == current
              ? parent.rightOperand
              : parent.leftOperand;
          if (_measured(other) || _sizeToken.hasMatch(other.toSource())) {
            if (op == TokenType.PLUS || op == TokenType.MINUS) return true;
            final bool dividend = parent.leftOperand == current;
            return dividend &&
                (op == TokenType.SLASH || op == TokenType.TILDE_SLASH);
          }
        }
        if (op == TokenType.QUESTION_QUESTION ||
            op == TokenType.PLUS ||
            op == TokenType.MINUS ||
            op == TokenType.STAR ||
            op == TokenType.SLASH ||
            op == TokenType.TILDE_SLASH) {
          current = parent;
        } else {
          return false;
        }
      case ConditionalExpression(:final Expression condition):
        if (condition == current) return false;
        current = parent;
      case SwitchExpressionCase(:final Expression expression):
        // A case's value is the switch's; its pattern and guard are not.
        if (expression != current) return false;
        current = parent.parent!;
      case ConstructorFieldInitializer(
        :final SimpleIdentifier fieldName,
        :final Expression expression,
      ):
        // `: _w = width`: the field holds it from here on. The field's own
        // name on the left is not a read.
        if (expression != current) return false;
        return layoutName.hasMatch(fieldName.name) || layoutOf(parent);
      case MethodInvocation(:final SimpleIdentifier methodName):
        if (const <String>{
          'min',
          'max',
          'clamp',
          'toDouble',
          'abs',
          'floor',
          'ceil',
          'round',
          'truncate',
          'floorToDouble',
          'ceilToDouble',
          'roundToDouble',
        }.contains(methodName.name)) {
          current = parent;
        } else if (methodName.name == 'translate') {
          return true;
        } else {
          return false;
        }
      case ArgumentList():
        final AstNode? call = parent.parent;
        final String? name = switch (call) {
          MethodInvocation(
            :final Expression? target,
            :final SimpleIdentifier methodName,
          ) =>
            target is SimpleIdentifier && geometryCalls.contains(target.name)
                ? target.name
                : methodName.name,
          InstanceCreationExpression(:final ConstructorName constructorName) =>
            constructorName.type.importPrefix?.name.lexeme != null &&
                    geometryCalls.contains(
                      constructorName.type.importPrefix!.name.lexeme,
                    )
                ? constructorName.type.importPrefix!.name.lexeme
                : constructorName.type.name.lexeme,
          _ => null,
        };
        if (name != null && geometryCalls.contains(name)) return true;
        if (call is MethodInvocation &&
            const <String>{'min', 'max'}.contains(call.methodName.name)) {
          current = call;
        } else if (call is MethodInvocation &&
            call.methodName.name == 'clamp') {
          current = call;
        } else {
          return false;
        }
      case NamedExpression(:final Label name):
        if (layoutName.hasMatch(name.label.name)) return true;
        final AstNode? list = parent.parent;
        if (list is ArgumentList) {
          current = parent;
        } else {
          return false;
        }
      case VariableDeclaration(:final Token name):
        return layoutName.hasMatch(name.lexeme) || layoutOf(parent);
      case ExpressionFunctionBody():
        return layoutOf(
          parent.parent is FunctionExpression
              ? parent.parent!.parent!
              : parent.parent!,
        );
      case ReturnStatement():
        final AstNode? body = parent.parent?.parent;
        if (body is BlockFunctionBody) {
          return layoutOf(
            body.parent is FunctionExpression
                ? body.parent!.parent!
                : body.parent!,
          );
        }
        return false;
      default:
        return false;
    }
  }
}

/// Every named size in [sources]: a named number that writes a size and is
/// used for layout, with the sizes it writes, by file.
Map<String, List<String>> namedSizes(List<GateSource> sources) {
  final List<NamedNumber> names = <NamedNumber>[
    for (final GateSource s in sources) ...namedNumbersIn(s),
  ];
  final Map<AstNode, NamedNumber> byNode = <AstNode, NamedNumber>{
    for (final NamedNumber n in names) n.node: n,
  };
  final Map<String, List<SimpleIdentifier>> reads =
      <String, List<SimpleIdentifier>>{};
  final Map<SimpleIdentifier, String> fileOf = <SimpleIdentifier, String>{};
  for (final GateSource s in sources) {
    s.unit.accept(_ReadCollector(s.path, reads, fileOf));
  }

  final Map<CompilationUnit, String> pathOf = <CompilationUnit, String>{
    for (final GateSource s in sources) s.unit: s.path,
  };
  final Map<AstNode, bool> memo = <AstNode, bool>{};
  bool layoutOf(AstNode declaration) {
    final bool? known = memo[declaration];
    if (known != null) return known;
    memo[declaration] = false;
    final NamedNumber? n = byNode[declaration];
    final bool result;
    final List<SimpleIdentifier> named = n == null
        ? const <SimpleIdentifier>[]
        : reads[n.name] ?? const <SimpleIdentifier>[];
    if (n != null && n.kind == NumberKind.parameter) {
      // By its reads, not its name: `padding = 1.08` can be a multiplier.
      // A `super.` parameter is read by the superclass, which this file may
      // not hold, under the same name: named for a dimension, it is one.
      final DefaultFormalParameter parameter = n.node as DefaultFormalParameter;
      result =
          (parameter.parameter is SuperFormalParameter &&
              layoutName.hasMatch(n.name)) ||
          named.any(
            (SimpleIdentifier r) =>
                fileOf[r] == n.path &&
                _inParameterScope(r, parameter) &&
                reachesLayout(r, layoutOf),
          );
    } else if (n != null && n.kind == NumberKind.integer) {
      result = named.any(
        (SimpleIdentifier r) =>
            _refersTo(r, fileOf[r]!, n) &&
            _toDouble(r) &&
            reachesLayout(r, layoutOf),
      );
    } else if (n != null) {
      result = named.any(
        (SimpleIdentifier r) =>
            _refersTo(r, fileOf[r]!, n) && reachesLayout(r, layoutOf),
      );
    } else if (declaration is VariableDeclaration &&
        declaration.parent?.parent is VariableDeclarationStatement) {
      // A local the size passes through, read only inside its own function.
      final AstNode? body = declaration.thisOrAncestorOfType<FunctionBody>();
      final String? path = pathOf[declaration.root];
      result =
          body != null &&
          (reads[declaration.name.lexeme] ?? const <SimpleIdentifier>[]).any(
            (SimpleIdentifier r) =>
                fileOf[r] == path &&
                r.offset > declaration.offset &&
                r.thisOrAncestorOfType<FunctionBody>() == body &&
                reachesLayout(r, layoutOf),
          );
    } else {
      result = false;
    }
    memo[declaration] = result;
    return result;
  }

  final Map<String, List<String>> found = <String, List<String>>{};
  final Map<String, GateSource> byPath = <String, GateSource>{
    for (final GateSource s in sources) s.path: s,
  };
  for (final NamedNumber n in names) {
    final List<num> sizes = sizesIn(n.value);
    if (sizes.isEmpty || !layoutOf(n.node)) continue;
    final GateSource source = byPath[n.path]!;
    found
        .putIfAbsent(n.path, () => <String>[])
        .add(
          'line ${source.lineOf(n.node.offset)}, ${n.name} = '
          '${n.value.toSource()}',
        );
  }
  return found;
}

/// Whether [read] is the target of `.toDouble()`, directly or through its
/// owner, `Owner.count.toDouble()`.
bool _toDouble(SimpleIdentifier read) {
  AstNode node = read;
  final AstNode? parent = read.parent;
  if (parent is PrefixedIdentifier && parent.identifier == read) node = parent;
  final AstNode? call = node.parent;
  return call is MethodInvocation &&
      call.target == node &&
      call.methodName.name == 'toDouble';
}

/// Whether [read] can be the parameter [parameter]: inside its function's
/// body, or, for a `this.` or `super.` parameter, anywhere in its class or as
/// `widget.name` and the like in the same file.
bool _inParameterScope(
  SimpleIdentifier read,
  DefaultFormalParameter parameter,
) {
  final NormalFormalParameter p = parameter.parameter;
  if (p is FieldFormalParameter || p is SuperFormalParameter) {
    final ClassDeclaration? owner = parameter
        .thisOrAncestorOfType<ClassDeclaration>();
    final AstNode? parent = read.parent;
    final bool member =
        (parent is PrefixedIdentifier && parent.identifier == read) ||
        (parent is PropertyAccess && parent.propertyName == read);
    return member || read.thisOrAncestorOfType<ClassDeclaration>() == owner;
  }
  final AstNode? function = parameter.parent?.parent;
  // A constructor's initializer list, `: _w = width`, reads its parameters.
  if (function is ConstructorDeclaration &&
      read.thisOrAncestorOfType<ConstructorInitializer>()?.parent == function) {
    return true;
  }
  final FunctionBody? body = switch (function) {
    FunctionExpression(:final FunctionBody body) => body,
    MethodDeclaration(:final FunctionBody body) => body,
    ConstructorDeclaration(:final FunctionBody body) => body,
    _ => null,
  };
  return body != null && read.thisOrAncestorOfType<FunctionBody>() == body;
}

/// Whether [read], in the file [path], can refer to [n]: in its own file, or
/// through its owner, or by name for a public top-level declaration.
bool _refersTo(SimpleIdentifier read, String path, NamedNumber n) {
  if (n.name.startsWith('_') && path != n.path) return false;
  final AstNode? parent = read.parent;
  final Expression? target = switch (parent) {
    PrefixedIdentifier(:final SimpleIdentifier prefix)
        when parent.identifier == read =>
      prefix,
    PropertyAccess(:final Expression? target)
        when parent.propertyName == read =>
      target,
    _ => null,
  };
  if (target == null) return path == n.path || n.owner == null;
  if (n.owner == null) return target is SimpleIdentifier;
  return true;
}

class _ReadCollector extends CodeVisitor {
  _ReadCollector(this.path, this.reads, this.fileOf);

  final String path;
  final Map<String, List<SimpleIdentifier>> reads;
  final Map<SimpleIdentifier, String> fileOf;

  @override
  void visitSimpleIdentifier(SimpleIdentifier node) {
    if (node.parent is! Label) {
      reads.putIfAbsent(node.name, () => <SimpleIdentifier>[]).add(node);
      fileOf[node] = path;
    }
    super.visitSimpleIdentifier(node);
  }
}
