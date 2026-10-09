/// Picking evidence identifiers off the record itself
/// (audit finding H6.1, severity 4; pass criterion 6.2).
///
/// A reviewer used to have to memorise a hash-like identifier from one tab,
/// close the dialog, find it, reopen the dialog and retype it, for every
/// corrected field. The identifiers live on the record, so the record offers
/// them, named in human terms.
library;

import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../models.dart';
import '../../vocabulary.dart';

/// One identifier the record already holds, with a name a reviewer reads.
@immutable
class EvidenceChoice {
  const EvidenceChoice({required this.id, required this.label});

  /// The identifier sent as `evidence_ids`.
  final String id;

  /// What the reviewer sees instead of the identifier.
  final String label;
}

/// A readable excerpt without treating a retained lookup payload as prose.
///
/// Known candidate values are displayed as reported, without claiming a match
/// is accepted. Unknown structured formats keep their raw body in audit details.
String evidenceDisplaySummary(Json evidence) {
  final excerpt = textOf(evidence['excerpt'], '').trim();
  final source = _evidenceSourceName(
    textOf(evidence['source'], textOf(evidence['source_id'], '')),
  );
  if (excerpt.isEmpty || excerpt == 'Not recorded') {
    return source ?? 'Retained evidence';
  }
  final structured = excerpt.startsWith('{') || excerpt.startsWith('[');
  if (!structured) {
    if (_opaqueIdentifier(excerpt)) return source ?? 'Retained evidence';
    return _shortEvidenceText(excerpt);
  }
  final values = <String>[];
  void add(Object? item) {
    if (item is List) {
      for (final child in item) {
        add(child);
      }
    } else if (item is Map) {
      for (final key in _candidateTextKeys) {
        final value = item[key];
        if (value is String &&
            value.trim().isNotEmpty &&
            !_opaqueIdentifier(value) &&
            !value.trim().startsWith('{') &&
            !value.trim().startsWith('[')) {
          final text = _shortEvidenceText(value.trim());
          if (!values.contains(text)) values.add(text);
          break;
        }
      }
      for (final key in [
        'candidate',
        'candidates',
        'match',
        'result',
        'results',
      ]) {
        if (item[key] is Map || item[key] is List) add(item[key]);
      }
    }
  }

  try {
    add(jsonDecode(excerpt));
  } on FormatException {
    // Canonical capture may retain one JSON candidate per line.
    for (final line in const LineSplitter().convert(excerpt)) {
      try {
        add(jsonDecode(line));
      } on FormatException {
        // Older canonical records stored Python dict repr. Parse only named
        // string properties; never evaluate or rewrite the retained payload.
        for (final key in _candidateTextKeys) {
          final match = RegExp(
            "['\"]${RegExp.escape(key)}['\"]\\s*:\\s*'((?:\\\\.|[^'\\\\])*)'",
          ).firstMatch(line);
          if (match != null) {
            final value = match.group(1)!;
            if (value.trim().isNotEmpty && !_opaqueIdentifier(value)) {
              final text = _shortEvidenceText(
                value.replaceAll(r"\'", "'").replaceAll(r'\n', ' '),
              );
              if (!values.contains(text)) values.add(text);
              break;
            }
          }
        }
      }
    }
  }
  if (values.isEmpty) return source ?? 'Retained source evidence';
  final summary = values.take(3).join(' · ');
  final extra = values.length > 3 ? ' · ${values.length - 3} more' : '';
  return '${source == null ? '' : '$source · '}$summary$extra';
}

const _candidateTextKeys = [
  'value',
  'matched_name',
  'matchedName',
  'scientificName',
  'scientific_name',
  'canonicalName',
  'canonical_name',
  'name',
  'label',
  'display_name',
  'formatted_address',
];

bool _opaqueIdentifier(String value) => RegExp(
  r'^(?:[a-f0-9]{32,}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})$',
  caseSensitive: false,
).hasMatch(value.trim());

String _shortEvidenceText(String value) {
  final text = value.replaceAll(RegExp(r'\s+'), ' ').trim();
  return text.length <= 160 ? text : '${text.substring(0, 157)}…';
}

String? _evidenceSourceName(String source) => switch (source) {
  'global_names_verifier' => 'Global Names Verifier',
  'catalogue_of_life' => 'Catalogue of Life',
  'gbif' => 'GBIF',
  'bugguide' => 'BugGuide',
  'mapcarta' => 'Mapcarta',
  'geolocate' => 'GEOLocate',
  'field_museum_ipt' => 'Field Museum IPT',
  'field_museum_emudata' => 'Field Museum EMu data',
  _ => null,
};

/// Sources a part's lookups name whose identifiers read badly as plain words.
const Map<String, String> _lookupSourceNames = <String, String>{
  'tgn': 'Getty TGN',
  'geonames': 'GeoNames',
};

/// The name of the source a retained evidence row came from, in the words of
/// the screen, or null when the row names none.
///
/// A source this table knows by name keeps its own spelling ("GEOLocate").
/// Any other is the plain-English reading of its identifier, so a source added
/// later still reaches the screen without underscores.
String? evidenceSourceLabel(Json evidence) {
  final String source = textOf(
    evidence['source'],
    textOf(evidence['source_id'], ''),
  ).trim();
  if (source.isEmpty || source == 'Not recorded') return null;
  final String? named =
      _evidenceSourceName(source) ?? _lookupSourceNames[source];
  if (named != null) return named;
  final String plain = vocabularyLabel(source).trim();
  return plain.isEmpty
      ? null
      : '${plain[0].toUpperCase()}${plain.substring(1)}';
}

/// Only retained Evidence identifiers accepted by the field decision API.
/// Observation and region IDs are source locators, not valid citations.
List<EvidenceChoice> evidenceChoices(Specimen specimen) {
  final List<EvidenceChoice> choices = <EvidenceChoice>[];
  final Map<Object?, String> regionNames = <Object?, String>{
    for (final (int i, Json r) in specimen.regions.indexed)
      r['region_id']: 'Label ${i + 1}',
  };

  for (final Json e in specimen.evidence) {
    if (e['field_citation_supported'] == false) continue;
    final String id = textOf(e['evidence_id'], textOf(e['id'], ''));
    if (id.isEmpty || id == 'Not recorded') continue;
    if (choices.any((EvidenceChoice c) => c.id == id)) continue;
    final String where = regionNames[e['region_id']] ?? 'Record';
    final String excerpt = evidenceDisplaySummary(e);
    choices.add(
      EvidenceChoice(
        id: id,
        label: excerpt.isEmpty || excerpt == 'Not recorded'
            ? '$where ${vocabularyLabel(textOf(e['kind'], 'evidence'))}'
            : '$where: $excerpt',
      ),
    );
  }

  return choices;
}

/// A set of evidence identifiers, chosen from the record.
class EvidencePicker extends StatelessWidget {
  const EvidencePicker({
    super.key,
    required this.choices,
    required this.selected,
    required this.onChanged,
    this.required = false,
  });

  /// What this record offers.
  final List<EvidenceChoice> choices;

  /// What is currently chosen.
  final Set<String> selected;

  /// Called with the new selection.
  final ValueChanged<Set<String>> onChanged;

  /// True when the current state cannot be saved without evidence.
  final bool required;

  /// The heading, in both its forms.
  static const String heading = 'Evidence';

  /// The heading when the state cannot be saved without one.
  static const String requiredHeading = 'Evidence on this record (required)';

  /// What the picker says when the record offers nothing to cite.
  static const String emptyMessage =
      'This record carries no evidence to cite yet.';

  /// The error under an empty required picker.
  static const String missingMessage =
      'Choose the evidence that supports this value.';

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          required ? requiredHeading : heading,
          style: ui.type.label.copyWith(color: ui.color.inkSecondary),
        ),
        SizedBox(height: ui.space.s1),
        if (choices.isEmpty)
          Text(emptyMessage, style: ui.type.bodySmall)
        else
          Wrap(
            spacing: ui.space.s2,
            runSpacing: ui.space.s2,
            children: <Widget>[
              for (final EvidenceChoice choice in choices)
                UiChip(
                  label: choice.label,
                  variant: UiChipVariant.filter,
                  selected: selected.contains(choice.id),
                  onPressed: () {
                    final bool on = !selected.contains(choice.id);
                    onChanged(
                      <String>{...selected, if (on) choice.id}
                        ..removeWhere((String id) => !on && id == choice.id),
                    );
                  },
                ),
            ],
          ),
        if (required && selected.isEmpty)
          Padding(
            padding: EdgeInsetsDirectional.only(top: ui.space.s1),
            child: Semantics(
              liveRegion: true,
              child: Text(
                missingMessage,
                style: ui.type.bodySmall.copyWith(
                  color: ui.color.status.blocked.content,
                ),
              ),
            ),
          ),
      ],
    );
  }
}
