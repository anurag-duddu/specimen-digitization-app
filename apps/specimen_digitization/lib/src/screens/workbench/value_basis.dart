/// How a field's value was obtained, worked out for display only.
///
/// The field model v2 records a basis on every value: `label` (the label states
/// it), `derived` (it follows from what is stated plus a known fact, a rule or
/// a lookup) and `inferred` (a reasoned conclusion, probable but not certain).
/// Basis is separate from the layer a record already carries (`verbatim`,
/// `settled`, `derived`). A record written before v2 has no basis, so this
/// file computes one from what the record does hold, and says nothing where
/// that is not enough. Nothing here is stored or sent to the server.
///
/// A wrong chip is worse than none. Wherever the stored values cannot tell the
/// cases apart, the answer is null.
library;

import '../../models.dart';
import 'field_presentation.dart';

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

/// The longest reading, in characters, that can be a field's own wording.
///
/// `verbatim_by_observation` holds what each reader read for the field, but
/// the research path stores the whole observation text there (the server's
/// `evidence.py` keeps `fragment.observation_text`), so a long reading is a
/// label's worth of text and never equals the field's value. A field's own
/// wording is a word, a place name or a short locality. The bound is
/// deliberately low: a reading over it, or one that runs over a line break,
/// is not trusted as the wording as written, and the row shows no chip. A
/// longer true locality therefore shows none, which is the safe side.
const int maxFieldWordingLength = 60;

/// The unit a field holds, for the fields whose key names one.
const Map<String, String> _fieldUnit = <String, String>{
  'elevation_from_m': 'm',
  'elevation_to_m': 'm',
  'elevation_from_ft': 'ft',
  'elevation_to_ft': 'ft',
};

/// The group the date fields belong to, by its title in `field_presentation`.
const String _dateGroup = 'Date';

/// The basis to show beside a field's value, or null to show nothing.
///
/// A [basis] the record states itself wins. A word this app does not know is
/// not guessed around: nothing is shown. Otherwise the basis follows from the
/// [layer] and the values the record holds:
///
/// - `verbatim` gives [ValueBasis.asWritten].
/// - `derived` gives [ValueBasis.derived].
/// - `settled` gives [ValueBasis.derived] when any value present differs from
///   the wording as written, and [ValueBasis.asWritten] when the wording as
///   written is present and every value agrees. Values agree when they match
///   once case, spacing, punctuation, diacritics, thousands separators and
///   unit marks (`'`, `ft`, `m`) are ignored, and plain numbers match by
///   value, so `6400` equals `6400.00` and `1950.7` equals `1950.70` while
///   `1950.7248` does not equal `1950.72`. A written `6400'` read as `6400`,
///   or `Mindanao` confirmed by a lookup, agree. `P.I.` settled as
///   `Philippines`, and `Chimaltenago` as `Chimaltenango`, differ.
/// - On a [fieldKey] that names a unit (the four elevation fields), a wording
///   marked in the other unit differs when its number differs, because that
///   is a conversion, and shows nothing when the number is the same, because
///   a number carried across units cannot be told from a mislabel.
/// - A settled date field shows nothing. A rule parses a date ("3 Sept. 1946"
///   to "1946-09-03") and the PRD calls that basis `label`, which the text
///   comparison cannot tell from a derivation. Its verbatim and derived
///   layers still show their chip.
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
/// readings stand in when they all give the same wording and each is short
/// enough to be a field's own wording ([maxFieldWordingLength]).
ValueBasis? valueBasisFor({
  required String? layer,
  String? fieldKey,
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
      if (fieldKey != null &&
          fieldReviewGroup(<String, dynamic>{'field_key': fieldKey}) ==
              _dateGroup) {
        return null;
      }
      final List<String> present = <String>[?written, ...others];
      if (present.length < 2) return null;
      final String? unit = fieldKey == null ? null : _fieldUnit[fieldKey];
      final String? marked = written == null ? null : _unitMark(written);
      final bool agree = _allAgree(present);
      if (unit != null && marked != null && marked != unit) {
        // Written in the other unit: a different number is a conversion, and
        // the same number is a unit carried across, which shows nothing.
        return agree ? null : ValueBasis.derived;
      }
      if (!agree) return ValueBasis.derived;
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
  fieldKey: field['field_key']?.toString(),
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

/// The one wording every reading gave, or null when they differ, are absent,
/// or are too long to be a field's own wording ([maxFieldWordingLength]).
String? _agreedWording(Iterable<String> readings) {
  final List<String> given = <String>[
    for (final String reading in readings)
      if (_present(reading) != null) reading,
  ];
  if (given.isEmpty) return null;
  for (final String reading in given) {
    if (reading.trim().length > maxFieldWordingLength ||
        reading.contains('\n') ||
        reading.contains('\r')) {
      return null;
    }
  }
  return given.map((String r) => _fold(r).text).toSet().length == 1
      ? given.first
      : null;
}

/// A number followed by a unit mark: `'`, a prime, `ft`, `feet`, `m`, `metres`.
///
/// Group 1 is the digit, group 2 a foot mark, group 3 a unit word.
final RegExp _unitAfterNumber = RegExp(
  '(\\d)\\s*(?:([\'${String.fromCharCode(0x2032)}${String.fromCharCode(0x2019)}])'
  '|(ft|feet|foot|m|meters|meter|metres|metre)\\.?(?![a-z]))',
);

/// The unit the wording carries after a number, `ft` or `m`, or null.
String? _unitMark(String wording) {
  final RegExpMatch? match = _unitAfterNumber.firstMatch(wording.toLowerCase());
  if (match == null) return null;
  if (match[2] != null) return 'ft';
  return switch (match[3]) {
    'ft' || 'feet' || 'foot' => 'ft',
    _ => 'm',
  };
}

/// A value reduced to what two spellings of it share.
///
/// [number] is the canonical form when the value is a plain decimal, so
/// `6400` and `6400.00` meet; [text] is the letters and digits left once case,
/// diacritics, punctuation and spacing are set aside.
typedef _Folded = ({String text, String? number});

_Folded _fold(String raw) {
  final String stripped = raw
      .toLowerCase()
      .replaceAllMapped(_unitAfterNumber, (Match match) => match[1]!)
      .replaceAll(RegExp(r'\s+'), '');
  return (text: _letters(stripped), number: _decimal(stripped));
}

bool _allAgree(List<String> values) {
  final List<_Folded> folded = values.map(_fold).toList();
  return folded.every((_Folded other) => _same(folded.first, other));
}

/// Two plain numbers agree by value. A number and a word never agree, so
/// `6400.5` is not `64005`. Anything else agrees by its letters and digits.
bool _same(_Folded a, _Folded b) {
  if (a.number != null || b.number != null) return a.number == b.number;
  return a.text == b.text;
}

/// The canonical plain decimal in [text], or null when it is not one.
///
/// A thousands comma is dropped. A number with a leading zero ("0042") is an
/// identifier kept as text, not a measurement, so it is not canonicalised.
String? _decimal(String text) {
  final String plain = text.replaceAll(RegExp(r'(?<=\d),(?=\d{3}(?!\d))'), '');
  final RegExpMatch? match = RegExp(
    r'^([+-]?)(\d+)(?:\.(\d+))?$',
  ).firstMatch(plain);
  if (match == null) return null;
  final String whole = match[2]!;
  if (whole.length > 1 && whole.startsWith('0')) return null;
  final String fraction = (match[3] ?? '').replaceFirst(RegExp(r'0+$'), '');
  final String sign = match[1] == '-' ? '-' : '';
  return fraction.isEmpty ? '$sign$whole' : '$sign$whole.$fraction';
}

/// The letters and digits of [text], with diacritics set aside.
String _letters(String text) {
  final StringBuffer out = StringBuffer();
  for (final int rune in text.runes) {
    // Combining marks, as a decomposed accent arrives.
    if (rune >= 0x300 && rune <= 0x36F) continue;
    out.write(_unaccented[rune] ?? String.fromCharCode(rune));
  }
  return out.toString().replaceAll(RegExp(r'[^\p{L}\p{N}]', unicode: true), '');
}

/// The plain letter for each accented Latin letter this collection meets,
/// built from code points so no source line holds an accent.
final Map<int, String> _unaccented = () {
  const Map<String, List<int>> letters = <String, List<int>>{
    'a': <int>[0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0x101, 0x103, 0x105],
    'c': <int>[0xE7, 0x107, 0x10D],
    'd': <int>[0x10F, 0x111],
    'e': <int>[0xE8, 0xE9, 0xEA, 0xEB, 0x113, 0x117, 0x119, 0x11B],
    'g': <int>[0x11F],
    'i': <int>[0xEC, 0xED, 0xEE, 0xEF, 0x12B, 0x131],
    'l': <int>[0x13A, 0x13E, 0x142],
    'n': <int>[0xF1, 0x144, 0x148],
    'o': <int>[0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF8, 0x14D, 0x151],
    'r': <int>[0x159],
    's': <int>[0x15B, 0x15F, 0x161],
    't': <int>[0x163, 0x165],
    'u': <int>[0xF9, 0xFA, 0xFB, 0xFC, 0x16B, 0x16F, 0x171],
    'y': <int>[0xFD, 0xFF],
    'z': <int>[0x17A, 0x17C, 0x17E],
    'ae': <int>[0xE6],
    'oe': <int>[0x153],
    'ss': <int>[0xDF],
  };
  return <int, String>{
    for (final MapEntry<String, List<int>> entry in letters.entries)
      for (final int rune in entry.value) rune: entry.key,
  };
}();
