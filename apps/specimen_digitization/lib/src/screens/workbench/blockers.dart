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
import '../../thread/thread.dart';
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
/// Order is the order a reviewer works in: the label regions and readings
/// first, then fields, then the operational state, because a run blocker is
/// rarely theirs to fix. The [thread] explains a blocker the record states,
/// and never adds one (UI.md T2.4).
List<ClearanceBlocker> blockersFor(
  Specimen specimen, {
  SpecimenThread? thread,
}) {
  final List<ClearanceBlocker> blockers = <ClearanceBlocker>[];
  final Json run = objectOf(specimen.data['run']);
  final ClearanceBlocker? coverage = _coverageBlocker(specimen, thread);
  if (coverage != null) blockers.add(coverage);

  for (final Json t in objects(specimen.data['transcriptions'])) {
    if (t['resolved'] == true) continue;
    final String region = _regionName(specimen, t['region_id']);
    blockers.add(
      ClearanceBlocker(
        // "Differ" only when the readings do (02 section 2.3). An unresolved
        // region whose readings agree still blocks clearance, because
        // clearance needs completed adjudication (CONTRACTS.md 239-240).
        message: readingsDiffer(t, specimen.observations)
            ? '${_countWord(distinctReadings(t, specimen.observations))} '
                  'readings differ for $region'
            : 'Transcription not resolved for $region',
        detail: 'Resolve the transcription, or record why it cannot be read',
        segment: WorkbenchSegment.readings,
        regionId: t['region_id'] as String?,
      ),
    );
  }

  for (final Json f in specimen.findings) {
    // The coverage entry above states this one, with what was measured.
    if (coverage != null && f['reason_code'] == _coverageCode) continue;
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

  // The workspace publishes each run reason twice, in `reason_codes` and as
  // a validation finding carrying the same code. A reason a finding already
  // states is one blocker, not two.
  final Set<String> stated = <String>{
    for (final Json f in specimen.findings)
      if (f['reason_code'] != null) f['reason_code'].toString(),
    if (coverage != null) _coverageCode,
  };
  for (final Object? code
      in specimen.data['reason_codes'] as List? ?? const <Object?>[]) {
    if (stated.contains(code.toString())) continue;
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

/// The summary the status strip carries, for a record that has blockers
/// (13 section 3.2).
///
/// A record with none carries no summary: a control that opens an empty list
/// is a control that does nothing (pass criterion 5.6), and the decision bar's
/// enabled approval already says that nothing is outstanding. The count starts
/// at one for that reason.
String blockersSummary(int count) =>
    count == 1 ? '1 thing blocks clearance' : '$count things block clearance';

/// What the sheet behind the summary is called.
const String blockersSheetTitle = 'What blocks clearance';

/// What the control that moves to one blocker is called.
const String goToBlockerLabel = 'Go to';

/// A count of readings as the first word of a sentence: "Two readings
/// differ", as 02 section 2.3 writes it.
String _countWord(int count) => switch (count) {
  2 => 'Two',
  3 => 'Three',
  4 => 'Four',
  5 => 'Five',
  _ => '$count',
};

String _regionName(Specimen specimen, Object? regionId) {
  final int index = specimen.regions.indexWhere(
    (Json r) => r['region_id'] == regionId,
  );
  return index < 0 ? 'this record' : 'Label ${index + 1}';
}

/// The reason a failed label coverage check leaves on the record (G15).
const String _coverageCode = 'label_coverage_unconfirmed';

/// The thread's failed coverage check, saying what each failed check
/// measured, while the record still states the check's reason. A reviewer
/// can confirm coverage after the run, and the thread never brings back a
/// blocker the record no longer has (UI.md T2.4).
ClearanceBlocker? _coverageBlocker(Specimen specimen, SpecimenThread? thread) {
  final ThreadCoverageCheck? check = thread?.coverageCheck;
  if (check == null || check.status != 'failed') return null;
  final List<Object?> reasons =
      specimen.data['reason_codes'] as List? ?? const <Object?>[];
  final bool stated =
      reasons.contains(_coverageCode) ||
      specimen.findings.any((Json f) => f['reason_code'] == _coverageCode);
  if (!stated) return null;
  final List<String> measured = <String>[
    for (final ThreadCheck failed in check.checks)
      if (failed.passed == false) ..._measured(failed),
  ];
  return ClearanceBlocker(
    message: vocabularyLabel(_coverageCode),
    detail: measured.isEmpty ? null : measured.join('. '),
    // Readings, beside the label regions the check judged.
    segment: WorkbenchSegment.readings,
  );
}

/// What one failed check measured, from the detail S5 pins for the thread.
/// A check, or a reason, this client does not know is named rather than
/// read into.
List<String> _measured(ThreadCheck check) {
  final Json detail = check.detail;
  final Set<String> reasons = <String>{
    for (final Object? code
        in detail['reason_codes'] as List? ?? const <Object?>[])
      '$code',
  };
  int? count(String key) => detail[key] is int ? detail[key] as int : null;
  final List<String> said = switch (check.name) {
    'region_count' => <String>[
      // No regions also fails the range; it is said once.
      if (reasons.contains('zero_regions'))
        'Found no label regions'
      else if (reasons.contains('label_region_count_out_of_range'))
        _regionCount(count('found'), count('min'), count('max')),
      if (reasons.contains('region_out_of_bounds'))
        'A label region lies outside the photograph',
    ],
    'full_image' => <String>[
      if (reasons.contains('cross_check_detection_outside_labels'))
        _outside(count('counted'), count('outside')),
    ],
    _ => const <String>[],
  };
  return said.isEmpty
      ? <String>['Failed: ${vocabularyLabel(check.name ?? 'a check')}']
      : said;
}

/// How many label regions were found, against the range the check records.
/// A range it does not record is not guessed.
String _regionCount(int? found, int? min, int? max) {
  if (found == null) {
    return "The number of label regions is outside the profile's range";
  }
  final String regions = found == 1 ? '1 label region' : '$found label regions';
  if (min == null || max == null) return 'Found $regions';
  return min == max
      ? 'Found $regions; the profile allows $min'
      : 'Found $regions; the profile allows $min to $max';
}

/// How many of the full image's label-like detections lie outside the label
/// regions.
String _outside(int? counted, int? outside) {
  if (counted == null || outside == null) {
    return 'A label-like detection lies outside the label regions';
  }
  final String verb = outside == 1 ? 'lies' : 'lie';
  return '$outside of $counted label-like detections $verb outside the '
      'label regions';
}
