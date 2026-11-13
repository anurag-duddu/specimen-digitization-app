/// A label's reading units in the readings segment (plan WP 1.6).
///
/// The first pass cuts each label's text into units and judges the image at
/// each one (FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 3). This view
/// shows every unit of one label in reading order: each reader's text there,
/// named by the reader, what the image shows, the first pass's meaning, the
/// fields it may fill, its role and its note.
library;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../reading_alignment.dart';
import '../../reading_units.dart';
import '../../vocabulary.dart';
import '../../widgets/caveat_text.dart';
import '../../widgets/selectable_evidence.dart';
import 'field_presentation.dart';

/// One reader a label's units name.
@immutable
class UnitReader {
  const UnitReader({required this.name, this.source});

  /// What the panel calls the reader.
  final String name;

  /// The reader's whole saved text, which a unit's offsets index; null when
  /// the record holds none for this reader.
  final String? source;
}

/// The name of a reader whose key is a person's transcription.
const String personReaderName = "Person's transcription";

/// The name of a reader whose key the record names nowhere else.
const String unrecordedReaderName = 'Reader not recorded';

/// Whether a person decided [transcription]'s text: a recorded actor, the
/// transcription resolved, and text saved.
bool personDecided(Json transcription) =>
    textOf(transcription['actor'], '').trim().isNotEmpty &&
    transcription['resolved'] == true &&
    textOf(transcription['verbatim_text'], '').isNotEmpty;

/// Every reader key [units] names, each with its name and saved text.
///
/// A key that is the id of one of [observations] is that model's reading,
/// named by [nameOf] and listed in the order of [observations]. Any other key
/// is the label's person-decided [transcription] when there is one
/// ([personDecided]), and otherwise a reader the record does not hold; those
/// follow in the order the units first name them.
Map<String, UnitReader> unitReaders({
  required LabelReadingUnits units,
  required List<Json> observations,
  required Json transcription,
  required String Function(Json observation) nameOf,
}) {
  final Set<String> keys = <String>{
    for (final ReadingUnit unit in units.units) ...unit.readers.keys,
  };
  final Map<String, UnitReader> readers = <String, UnitReader>{};
  for (final Json observation in observations) {
    for (final Object? id in <Object?>[
      observation['id'],
      observation['observation_id'],
    ]) {
      if (id is String && keys.contains(id) && !readers.containsKey(id)) {
        readers[id] = UnitReader(
          name: nameOf(observation),
          source: textOf(
            observation['literal_text'],
            textOf(observation['verbatim_text'], ''),
          ),
        );
      }
    }
  }
  final bool person = personDecided(transcription);
  for (final String key in keys) {
    readers.putIfAbsent(
      key,
      () => person
          ? UnitReader(
              name: personReaderName,
              source: textOf(transcription['verbatim_text'], ''),
            )
          : const UnitReader(name: unrecordedReaderName),
    );
  }
  return readers;
}

/// The units of one label, each reader's text named by its reader.
class ReadingUnitsView extends StatelessWidget {
  const ReadingUnitsView({
    super.key,
    required this.units,
    required this.readers,
    this.compact = false,
  });

  /// The label's units, in reading order.
  final LabelReadingUnits units;

  /// Every reader the units name, in the order [unitReaders] gives them: the
  /// readers that are observations in observation order, then the other keys
  /// in the order the units first name them.
  final Map<String, UnitReader> readers;

  /// Tighter spacing for a short, scrollable inspector.
  final bool compact;

  static const String title = 'Label text by part';
  static const String imageLabel = 'Image: ';
  static const String uncertainImage = 'Uncertain';
  static const String notVisibleImage = 'Not visible';
  static const String matchesImage = 'Matches the image';
  static const String nothingWritten = 'Nothing written here';
  static const String meaningLabel = 'Meaning: ';
  static const String fieldsLabel = 'Possible fields: ';
  static const String roleLabel = 'Role: ';
  static const String noteLabel = 'Note: ';
  static const String mismatch = 'Does not match the saved reading';

  /// "Part 2 · Line 3", or "Part 2 · Lines 3 to 4" across lines.
  static String partHeading(int number, int firstLine, int lastLine) =>
      'Part $number · '
      '${firstLine == lastLine ? 'Line $firstLine' : 'Lines $firstLine to $lastLine'}';

  /// The parts count beside the title.
  static String partsCount(int count) => count == 1 ? '1 part' : '$count parts';

  /// Why a reader's text at a part does not match its saved reading.
  static String mismatchWhy(String reader) =>
      '$reader: the stored position of this part points at other text. '
      'Refresh the record.';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double gap = compact ? ui.space.s2 : ui.space.s3;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        UiSectionHeader(
          title: title,
          role: UiSectionHeaderRole.card,
          meta: Text(
            partsCount(units.units.length),
            style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
          ),
        ),
        SizedBox(height: gap),
        SelectableEvidence(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              for (final (int index, ReadingUnit unit) in units.units.indexed)
                Padding(
                  padding: EdgeInsetsDirectional.only(bottom: gap),
                  child: _part(context, index + 1, unit),
                ),
            ],
          ),
        ),
      ],
    );
  }

  /// The unit's reader keys in [readers]' order, then any it does not hold.
  List<String> _keysOf(ReadingUnit unit) => <String>[
    for (final String key in readers.keys)
      if (unit.readers.containsKey(key)) key,
    for (final String key in unit.readers.keys)
      if (!readers.containsKey(key)) key,
  ];

  String _nameOf(String key) => readers[key]?.name ?? unrecordedReaderName;

  /// True when [key]'s text at [unit] is its saved reading at the unit's
  /// code-point offsets, or when the record holds no saved reading to check.
  bool _matchesSource(String key, UnitReading reading) {
    final String? source = readers[key]?.source;
    if (source == null) return true;
    try {
      return exactCodePointSpan(
            source,
            reading.startCodePoint,
            reading.endCodePoint,
          ) ==
          reading.text;
    } on FormatException {
      return false;
    }
  }

  Widget _part(BuildContext context, int number, ReadingUnit unit) {
    final UiThemeData ui = context.ui;
    final TextStyle key = ui.type.labelSmall.copyWith(
      color: ui.color.inkSecondary,
    );
    final TextStyle detail = ui.type.bodySmall.copyWith(color: ui.color.ink);
    final bool named =
        unit.image != imageUncertain && unit.image != imageNotVisible;
    // Readers that wrote the same text share one entry, each name on its own
    // line: a name can hold the separator `·` (`readerModelName`).
    final Map<String, List<String>> byText = <String, List<String>>{};
    for (final String reader in _keysOf(unit)) {
      byText
          .putIfAbsent(unit.readers[reader]!.text, () => <String>[])
          .add(reader);
    }
    Widget line(String label, String value) => Padding(
      padding: EdgeInsetsDirectional.only(top: ui.space.s1),
      child: Text.rich(
        TextSpan(
          children: <InlineSpan>[
            TextSpan(text: label, style: key),
            TextSpan(text: value, style: detail),
          ],
        ),
      ),
    );

    return Semantics(
      container: true,
      explicitChildNodes: true,
      child: Surface(
        radius: ui.shape.tile,
        boundary: true,
        padding: EdgeInsetsDirectional.all(ui.space.s3),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              partHeading(number, unit.firstLine, unit.lastLine),
              style: ui.type.label,
            ),
            Padding(
              padding: EdgeInsetsDirectional.only(top: ui.space.s1),
              child: Text.rich(
                TextSpan(
                  children: <InlineSpan>[
                    TextSpan(text: imageLabel, style: key),
                    TextSpan(
                      text: switch (unit.image) {
                        imageUncertain => uncertainImage,
                        imageNotVisible => notVisibleImage,
                        _ => unit.image,
                      },
                      style: named ? ui.type.mono.literalDense : detail,
                    ),
                  ],
                ),
              ),
            ),
            for (final MapEntry<String, List<String>> group in byText.entries)
              Padding(
                padding: EdgeInsetsDirectional.only(top: ui.space.s2),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    for (final String reader in group.value)
                      Text(_nameOf(reader), style: key),
                    if (group.key.isEmpty)
                      Text(nothingWritten, style: detail)
                    else
                      Text(group.key, style: ui.type.mono.literalDense),
                    if (named &&
                        group.key.isNotEmpty &&
                        group.key == unit.image)
                      Row(
                        children: <Widget>[
                          const ExcludeSemantics(
                            child: UiIcon(
                              UiIcons.image,
                              size: UiIconSize.small,
                            ),
                          ),
                          SizedBox(width: ui.space.s1),
                          Flexible(
                            child: Text(
                              matchesImage,
                              style: ui.type.labelSmall,
                            ),
                          ),
                        ],
                      ),
                    for (final String reader in group.value)
                      if (!_matchesSource(reader, unit.readers[reader]!))
                        CaveatText(
                          label: mismatch,
                          why: mismatchWhy(_nameOf(reader)),
                        ),
                  ],
                ),
              ),
            if (unit.means.isNotEmpty) line(meaningLabel, unit.means),
            if (unit.fields.isNotEmpty)
              line(
                fieldsLabel,
                unit.fields
                    .map(
                      (String field) => fieldReviewName(<String, dynamic>{
                        'field_key': field,
                        'display_name': vocabularyLabel(field),
                      }),
                    )
                    .join(', '),
              ),
            if (unit.role.isNotEmpty)
              line(roleLabel, vocabularyLabel(unit.role)),
            if (unit.note.isNotEmpty) line(noteLabel, unit.note),
          ],
        ),
      ),
    );
  }
}
