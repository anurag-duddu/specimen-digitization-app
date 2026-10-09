/// How a field's value was obtained, worked out for display only.
///
/// The field model v2 records a basis on every value: `label` (the label states
/// it), `derived` (it follows from what is stated plus a known fact, a rule or
/// a lookup) and `inferred` (a reasoned conclusion, probable but not certain).
/// Basis is separate from the layer a record already carries (`verbatim`,
/// `settled`, `derived`). A record written before v2 has no basis, so this
/// file computes one from what the record does hold, and says nothing where
/// that is not enough. Nothing here is stored or sent to the server.
library;

import '../../models.dart';

/// The three ways a value can have been obtained.
enum ValueBasis {
  /// The label states the value, as written.
  asWritten('label', 'As written', 'as written'),

  /// The value follows from what is stated plus a fact, a rule or a lookup.
  derived('derived', 'Derived', 'derived'),

  /// A reasoned conclusion that is probable but not certain.
  ///
  /// No record written before v2 produces this. The model and the chip carry
  /// it so a later writer can use it without another app release.
  inferred('inferred', 'Inferred', 'inferred');

  const ValueBasis(this.wire, this.label, this._spoken);

  /// The word the wire uses, as the field model v2 names it.
  final String wire;

  /// The chip's text. At most 20 characters (UX writing, 4.13).
  final String label;

  final String _spoken;

  /// What a screen reader hears: a complete phrase that stands alone
  /// (UX writing, 4.16).
  String get semanticsLabel => 'Basis: $_spoken';

  /// The basis a wire value names, or null for a word this app does not know.
  static ValueBasis? fromWire(Object? value) {
    for (final ValueBasis basis in values) {
      if (basis.wire == value) return basis;
    }
    return null;
  }
}

/// The basis to show beside a field's value, or null to show nothing.
///
/// A [basis] the record states itself wins. A word this app does not know is
/// not guessed around: nothing is shown. Otherwise the basis follows from the
/// [layer] and the values the record holds:
///
/// - `verbatim` gives [ValueBasis.asWritten].
/// - `derived` gives [ValueBasis.derived].
/// - `settled` gives [ValueBasis.asWritten] when the wording as written agrees
///   with every other value present once case, spacing and unit marks (`'`,
///   `ft`, `m`) are ignored, and [ValueBasis.derived] when any value present
///   differs. A written `6400'` parsed as `6400`, or `Mindanao` confirmed by a
///   lookup, agree. `P.I.` settled as `Philippines` differs.
/// - Where the stored values cannot tell the two apart, nothing is shown
///   rather than a guess: a lone value, or values that agree when no wording
///   as written is held to say the label stated them.
/// - A layer this app does not know, or none, shows nothing.
///
/// A record written before v2 is never shown as [ValueBasis.inferred]; only a
/// stated [basis] can say so.
///
/// The wording as written is the [literal] when there is one. A settled value
/// often has none, because its wording sits with each [readings] entry, so the
/// readings stand in when they all give the same wording.
ValueBasis? valueBasisFor({
  required String? layer,
  Object? basis,
  String? literal,
  String? parsed,
  String? normalized,
  Iterable<String> readings = const <String>[],
}) {
  final String? written = _present(literal) ?? _agreedWording(readings);
  final List<String> others = <String>[
    ?_present(parsed),
    ?_present(normalized),
  ];
  // A field with no value has no basis to show.
  if (written == null && others.isEmpty) return null;
  if (basis != null) return ValueBasis.fromWire(basis);
  switch (layer) {
    case 'verbatim':
      return ValueBasis.asWritten;
    case 'derived':
      return ValueBasis.derived;
    case 'settled':
      final List<String> present = <String>[?written, ...others];
      if (present.length < 2) return null;
      final Set<String> folded = present.map(_fold).toSet();
      if (folded.length > 1) return ValueBasis.derived;
      return written == null ? null : ValueBasis.asWritten;
  }
  return null;
}

/// The basis to show for a field of a specimen record, or null.
///
/// Reads only what the record already carries: an optional `basis`, the
/// `layer`, and the literal, parsed and normalized values with the readings'
/// wording. A basis for a part of a value is not read yet.
ValueBasis? fieldValueBasis(Json field) => valueBasisFor(
  layer: field['layer'] is String ? field['layer'] as String : null,
  basis: field['basis'],
  literal: _stringOf(field['literal_value']),
  parsed: _stringOf(field['parsed_value']),
  normalized: _stringOf(field['normalized']),
  readings: <String>[
    if (field['verbatim_by_observation'] case final Map<dynamic, dynamic> by)
      ...by.values.whereType<String>(),
  ],
);

String? _stringOf(Object? value) => value is String ? value : null;

String? _present(String? value) =>
    value == null || value.trim().isEmpty ? null : value;

/// The one wording every reading gave, or null when they differ or are absent.
String? _agreedWording(Iterable<String> readings) {
  final List<String> given = <String>[
    for (final String reading in readings)
      if (_present(reading) != null) reading,
  ];
  if (given.isEmpty) return null;
  return given.map(_fold).toSet().length == 1 ? given.first : null;
}

/// A number followed by a unit mark: `'`, a prime, `ft`, `feet`, `m`, `metres`.
final RegExp _unitAfterNumber = RegExp(
  r"(\d)\s*(?:['\u2032\u2019]|(?:ft|feet|foot|m|meters|meter|metres|metre)\.?(?![a-z]))",
);

/// The text with case, spacing and unit marks after a number set aside.
String _fold(String text) => text
    .toLowerCase()
    .replaceAllMapped(_unitAfterNumber, (Match match) => match[1]!)
    .replaceAll(RegExp(r'\s+'), '');
