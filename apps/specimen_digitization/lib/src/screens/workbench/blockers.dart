/// One list of everything that blocks clearance
/// (audit finding H6.3, severity 4; pass criterion 6.3).
///
/// Today a reviewer assembles this list from five places on every record:
/// validation findings, reason codes, the run blocker, phase findings and the
/// operational panel. This collects them once, in plain words, each with the
/// control that resolves it.
library;

import 'package:flutter/foundation.dart';

import '../../models.dart';
import '../../review_context.dart';
import '../../vocabulary.dart';
import 'workbench_layout.dart';

/// One unmet gate, and where the reviewer goes to resolve it.
@immutable
class ClearanceBlocker {
  const ClearanceBlocker({
    required this.message,
    required this.segment,
    this.detail,
    this.fieldKey,
    this.regionId,
  });

  /// What is outstanding, as a sentence a reviewer can act on.
  final String message;

  /// Where the control that resolves it lives.
  final WorkbenchSegment segment;

  /// The rule or the source, one line, for the reviewer who wants it.
  final String? detail;

  /// The field this belongs to, when it belongs to one.
  final String? fieldKey;

  /// The label region this belongs to, when it belongs to one.
  final String? regionId;

  /// The anchor the evidence pane scrolls to.
  String? get anchor => fieldKey ?? regionId;
}

/// Everything that currently blocks clearance on [specimen].
///
/// Order is the order a reviewer works in: readings first, then fields, then
/// the operational state, because a run blocker is rarely theirs to fix.
List<ClearanceBlocker> blockersFor(Specimen specimen) {
  final List<ClearanceBlocker> blockers = <ClearanceBlocker>[];
  final Json run = objectOf(specimen.data['run']);

  for (final Json t in objects(specimen.data['transcriptions'])) {
    if (t['resolved'] == true) continue;
    blockers.add(
      ClearanceBlocker(
        message:
            'Two readings differ for '
            '${_regionName(specimen, t['region_id'])}',
        detail: 'Resolve the transcription, or record why it cannot be read',
        segment: WorkbenchSegment.readings,
        regionId: t['region_id'] as String?,
      ),
    );
  }

  for (final Json f in specimen.findings) {
    final String? field = f['field_key'] as String?;
    blockers.add(
      ClearanceBlocker(
        message: textOf(
          f['message'],
          vocabularyLabel(textOf(f['reason_code'], 'Validation finding')),
        ),
        detail: <String>[
          if (field != null && field.isNotEmpty) vocabularyLabel(field),
          if (f['severity'] != null) vocabularyLabel(textOf(f['severity'])),
          if (f['rule_id'] != null) textOf(f['rule_id']),
        ].join(' · '),
        segment: WorkbenchSegment.fields,
        fieldKey: field,
      ),
    );
  }

  for (final Object? code
      in specimen.data['reason_codes'] as List? ?? const <Object?>[]) {
    blockers.add(
      ClearanceBlocker(
        message: vocabularyLabel(code.toString()),
        detail: 'Recorded by the server on this version',
        segment: WorkbenchSegment.fields,
      ),
    );
  }

  final String blocker = textOf(
    run['blocker'],
    textOf(specimen.data['blocker'], ''),
  );
  if (blocker.isNotEmpty && blocker != 'Not recorded') {
    blockers.add(
      ClearanceBlocker(
        message: 'Processing is blocked: ${vocabularyLabel(blocker)}',
        detail: 'Open Processing for the run detail and what is permitted',
        segment: WorkbenchSegment.fields,
      ),
    );
  }

  return blockers;
}

/// The summary line above the list (blueprint 6.1).
String blockersSummary(int count) => switch (count) {
  0 => 'Nothing outstanding. Approval is available.',
  1 => '1 thing blocks clearance',
  _ => '$count things block clearance',
};

String _regionName(Specimen specimen, Object? regionId) {
  final int index = specimen.regions.indexWhere(
    (Json r) => r['region_id'] == regionId,
  );
  return index < 0 ? 'this record' : 'Label ${index + 1}';
}
