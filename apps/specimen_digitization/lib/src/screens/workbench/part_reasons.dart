/// The review list's sentences for a part's reason code (wire contract,
/// section 5; planned and not in force).
///
/// A reason about a part names it as `<rule>:<path>`: `part_conflict`,
/// `part_doubt` and `part_no_support` for a part, and `part_bounds_exceeded`
/// for a value whose parts did not fit, named by its first path segment. No
/// server writes these codes yet. Today the review list shows one generic line
/// for a code it does not know; this gives the four a plain sentence and the
/// field to open, and changes nothing for any other code.
library;

import '../../models.dart';
import 'field_parts.dart';

/// The four rules a part's reason code can begin with.
const Set<String> partReasonBases = <String>{
  'part_conflict',
  'part_doubt',
  'part_no_support',
  'part_bounds_exceeded',
};

/// What the review list says about one part reason, and where it leads.
class PartIssue {
  const PartIssue({required this.message, required this.detail, this.fieldKey});

  /// The headline, a sentence a reviewer can act on.
  final String message;

  /// The plain-language next step, or the writer's own words behind it.
  final String detail;

  /// The field the part is carried on, or null when this reader does not
  /// know one.
  final String? fieldKey;
}

/// The sentence and target for the reason code `<base>:<subject>` on
/// [specimen], or null when the subject is not one this reader knows (the
/// review list then shows its generic line, as it does today).
PartIssue? partIssueFor(Specimen specimen, String base, String subject) {
  if (base == 'part_bounds_exceeded') {
    final String? label = partValueLabel(subject);
    if (label == null) return null;
    return PartIssue(
      message: 'Check $label',
      detail:
          'It has more parts than the record can hold, so none were saved. '
          'The value is unchanged.',
      fieldKey: partValueCarrier(subject),
    );
  }

  final PartPath? path = PartPath.tryParse(subject);
  final String? carrier = path?.carrierField;
  if (path == null || path.isRoot || carrier == null) return null;
  final String name = path.label.toLowerCase();

  FieldPart? part;
  for (final Json field in specimen.fields) {
    if (field['field_key'] == carrier) {
      part = FieldParts.of(field).byPath(path.text);
    }
  }

  const String fallback = 'Review the value and its supporting sources.';
  switch (base) {
    case 'part_conflict':
      final Map<String, String> kinds = <String, String>{
        for (final Json row in specimen.evidence)
          if (_idOf(row) case final String id) id: '${row['kind'] ?? ''}',
      };
      final String subjectWord = part == null
          ? 'readings'
          : partConflictSubject(part, kinds);
      final List<String> values = part?.conflictValues ?? const <String>[];
      return PartIssue(
        message: '${_capitalise(subjectWord)} differ for $name',
        detail: values.length < 2
            ? fallback
            : '${values.map(sentenceValue).join(' or ')}.',
        fieldKey: carrier,
      );
    case 'part_doubt':
      return PartIssue(
        message: 'Check $name',
        detail: part?.review?.reason ?? fallback,
        fieldKey: carrier,
      );
    case 'part_no_support':
      return PartIssue(
        message: 'No source supports $name',
        detail: part?.review?.reason ?? fallback,
        fieldKey: carrier,
      );
  }
  return null;
}

String? _idOf(Json row) {
  final Object? id = row['evidence_id'] ?? row['id'];
  return id is String && id.isNotEmpty ? id : null;
}

String _capitalise(String text) =>
    text.isEmpty ? text : '${text[0].toUpperCase()}${text.substring(1)}';
