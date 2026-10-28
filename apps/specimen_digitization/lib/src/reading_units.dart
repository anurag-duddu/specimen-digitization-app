/// A label's reading units, as the server stores them on the run.
///
/// The workspace response carries them at `run.reading_units`, one entry per
/// label (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 3). This file only
/// reads the record. Offsets stay in code points, as the server writes them;
/// nothing here converts them to the UTF-16 offsets a Dart `String` slices by.
library;

import 'models.dart';

/// What one reader wrote at a unit, and where in that reader's own text.
class UnitReading {
  const UnitReading({
    required this.text,
    required this.startCodePoint,
    required this.endCodePoint,
  });

  /// The reader's text at the unit; empty when it wrote nothing there.
  final String text;

  /// The unit's first code point in the reader's text (a Python string index).
  final int startCodePoint;

  /// The code point just past the unit's last one.
  final int endCodePoint;

  /// Null unless [value] is a complete reading whose text spans its offsets.
  static UnitReading? fromJson(Object? value) {
    if (value is! Map) return null;
    final Object? text = value['text'];
    final Object? start = value['start'];
    final Object? end = value['end'];
    if (text is! String || start is! int || end is! int || start < 0) {
      return null;
    }
    if (end - start != text.runes.length) return null;
    return UnitReading(text: text, startCodePoint: start, endCodePoint: end);
  }
}

/// One unit of a label: the keys of the design's section 3.
class ReadingUnit {
  const ReadingUnit({
    required this.id,
    required this.label,
    required this.firstLine,
    required this.lastLine,
    required this.readers,
    required this.image,
    required this.means,
    required this.role,
    required this.fields,
    required this.note,
  });

  /// `<label>:<n>`, n counting from 1 in reading order.
  final String id;
  final String label;

  /// The first and last line the unit covers, counting from 1.
  final int firstLine, lastLine;

  /// Each reader's text at the unit, keyed by reading.
  final Map<String, UnitReading> readers;

  /// One reader's text, `uncertain` or `not visible`.
  final String image;

  /// The first pass's own interpretation; may be empty.
  final String means;

  /// The part of a field's value the unit is; empty when it is none.
  final String role;

  /// The fields the unit could belong to, most likely first. Advice only.
  final List<String> fields;
  final String note;

  /// Null unless [value] is a complete unit.
  static ReadingUnit? fromJson(Object? value) {
    if (value is! Map) return null;
    final Object? id = value['id'];
    final Object? label = value['label'];
    final Object? lines = value['lines'];
    final Object? readers = value['readers'];
    final Object? image = value['image'];
    final Object? means = value['means'];
    final Object? role = value['role'];
    final Object? fields = value['fields'];
    final Object? note = value['note'];
    if (id is! String ||
        label is! String ||
        lines is! List ||
        lines.length != 2 ||
        lines.any((Object? line) => line is! int) ||
        readers is! Map ||
        readers.isEmpty ||
        image is! String ||
        means is! String ||
        role is! String ||
        fields is! List ||
        fields.any((Object? field) => field is! String) ||
        note is! String) {
      return null;
    }
    final Map<String, UnitReading> parsed = <String, UnitReading>{};
    for (final MapEntry<Object?, Object?> entry in readers.entries) {
      final UnitReading? reading = UnitReading.fromJson(entry.value);
      if (entry.key is! String || reading == null) return null;
      parsed[entry.key! as String] = reading;
    }
    return ReadingUnit(
      id: id,
      label: label,
      firstLine: lines[0] as int,
      lastLine: lines[1] as int,
      readers: parsed,
      image: image,
      means: means,
      role: role,
      fields: List<String>.unmodifiable(fields.cast<String>()),
      note: note,
    );
  }
}

/// One label's units, in reading order.
class LabelReadingUnits {
  const LabelReadingUnits({required this.label, required this.units});

  /// The label's region id.
  final String label;
  final List<ReadingUnit> units;

  /// Null unless [value] is a label with at least one unit, all of them its.
  static LabelReadingUnits? fromJson(Object? value) {
    if (value is! Map) return null;
    final Object? label = value['label'];
    final Object? units = value['units'];
    if (label is! String || units is! List || units.isEmpty) return null;
    final List<ReadingUnit> parsed = <ReadingUnit>[];
    for (final Object? unit in units) {
      final ReadingUnit? reading = ReadingUnit.fromJson(unit);
      if (reading == null || reading.label != label) return null;
      parsed.add(reading);
    }
    return LabelReadingUnits(
      label: label,
      units: List<ReadingUnit>.unmodifiable(parsed),
    );
  }
}

/// The run's units by label. Empty for a run stored without units.
///
/// A label whose entry does not parse is left out, so it reads as a label
/// without units rather than as a guess.
Map<String, LabelReadingUnits> readingUnitsOf(Object? run) {
  if (run is! Map || run['reading_units'] is! List) {
    return const <String, LabelReadingUnits>{};
  }
  final Map<String, LabelReadingUnits> found = <String, LabelReadingUnits>{};
  for (final Object? entry in run['reading_units'] as List) {
    final LabelReadingUnits? units = LabelReadingUnits.fromJson(entry);
    if (units != null) found[units.label] = units;
  }
  return Map<String, LabelReadingUnits>.unmodifiable(found);
}

/// The units of the record's current run.
extension SpecimenReadingUnits on Specimen {
  Map<String, LabelReadingUnits> get readingUnits =>
      readingUnitsOf(data['run']);
}
