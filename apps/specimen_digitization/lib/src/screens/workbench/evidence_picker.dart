/// Picking evidence identifiers off the record itself
/// (audit finding H6.1, severity 4; pass criterion 6.2).
///
/// A reviewer used to have to memorise a hash-like identifier from one tab,
/// close the dialog, find it, reopen the dialog and retype it, for every
/// corrected field. The identifiers live on the record, so the record offers
/// them, named in human terms.
library;

import 'package:flutter/material.dart';

import '../../models.dart';
import '../../theme/icons.dart';
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

/// Every evidence identifier on [specimen], named.
///
/// Regions become "Label 2", readings become "Label 2 reading (model)", and
/// recorded evidence keeps its own source and excerpt.
List<EvidenceChoice> evidenceChoices(Specimen specimen) {
  final List<EvidenceChoice> choices = <EvidenceChoice>[];
  final Map<Object?, String> regionNames = <Object?, String>{
    for (final (int i, Json r) in specimen.regions.indexed)
      r['region_id']: 'Label ${i + 1}',
  };

  for (final Json e in specimen.evidence) {
    final String id = textOf(e['evidence_id'], textOf(e['id'], ''));
    if (id.isEmpty || id == 'Not recorded') continue;
    final String where = regionNames[e['region_id']] ?? 'Record';
    final String excerpt = textOf(e['excerpt'], '');
    choices.add(
      EvidenceChoice(
        id: id,
        label: excerpt.isEmpty || excerpt == 'Not recorded'
            ? '$where ${vocabularyLabel(textOf(e['kind'], 'evidence'))}'
            : '$where: $excerpt',
      ),
    );
  }

  for (final Json o in specimen.observations) {
    final String id = textOf(o['id'], textOf(o['observation_id'], ''));
    if (id.isEmpty || id == 'Not recorded') continue;
    if (choices.any((EvidenceChoice c) => c.id == id)) continue;
    final String where = regionNames[o['region_id']] ?? 'Record';
    choices.add(
      EvidenceChoice(
        id: id,
        label: '$where reading (${textOf(o['model_id'], 'model')})',
      ),
    );
  }

  for (final Json r in specimen.regions) {
    final String id = textOf(r['region_id'], '');
    if (id.isEmpty || id == 'Not recorded') continue;
    if (choices.any((EvidenceChoice c) => c.id == id)) continue;
    choices.add(EvidenceChoice(id: id, label: regionNames[r['region_id']]!));
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

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          required ? 'Evidence on this record (required)' : 'Evidence',
          style: theme.textTheme.labelMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        SizedBox(height: context.space.space1),
        if (choices.isEmpty)
          Text(
            'This record carries no evidence to cite yet.',
            style: theme.textTheme.bodySmall,
          )
        else
          Wrap(
            spacing: context.space.space2,
            runSpacing: context.space.space2,
            children: <Widget>[
              for (final EvidenceChoice choice in choices)
                FilterChip(
                  label: Text(choice.label),
                  selected: selected.contains(choice.id),
                  onSelected: (bool on) => onChanged(
                    <String>{...selected, if (on) choice.id}
                      ..removeWhere((String id) => !on && id == choice.id),
                  ),
                ),
            ],
          ),
        if (required && selected.isEmpty)
          Padding(
            padding: EdgeInsets.only(top: context.space.space1),
            child: Semantics(
              liveRegion: true,
              child: Text(
                'Choose the evidence that supports this value.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ),
          ),
      ],
    );
  }
}
