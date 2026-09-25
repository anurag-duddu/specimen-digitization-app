// The review queue's reasons in words (UI.md T3.2).
//
// The lane policy's reason codes, S3's list of 2026-09-24 generated from
// S4's `policy.py`, read as words wherever a reason is shown.

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/models.dart';
import 'package:specimen_digitization/src/reason_codes.dart';
import 'package:specimen_digitization/src/screens/queue/queue_screen.dart';
import 'package:specimen_digitization/src/screens/workbench/blockers.dart';
import 'package:specimen_digitization/src/search_filters.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'widgets/harness.dart';

/// Every code `policy.evaluate` emits today, with the words it reads as.
const Map<String, String> policyReasons = <String, String>{
  'institutional_policy_unapproved': 'Institutional policy not approved',
  'mandatory_semantics_unconfirmed': 'Required field meanings not confirmed',
  'label_coverage_unconfirmed': 'Label coverage not confirmed',
  'independent_observations_missing': 'Two independent readings needed',
  'raw_provenance_missing': 'Raw reading not stored',
  'unresolved_transcription': 'Transcription not resolved',
  'evidence_lineage_invalid': 'Evidence not traced to a label region',
  'mandatory_unresolved': 'Required field has no supported value',
  'evidence_missing': 'Required field cites no evidence',
  'evidence_does_not_support_value': 'Evidence does not contain the value',
  'pixel_lineage_missing': 'Evidence not from a label region',
  'unsupported_parsed': 'Read as not supported by evidence',
  'unsupported_normalized': 'Standardized value not supported by evidence',
  'unsupported_authority_id': 'Authority match not supported by evidence',
  'elevation_range': 'Elevation range reversed',
  'elevation_invalid': 'Elevation is not a number',
  'elevation_units_conflict': 'Meters and feet disagree',
  'date_order': 'Dates out of order',
  'date_precision_requires_review': 'Date is not a full calendar date',
  'identifier_format': 'Catalog number format not recognized',
  'human_approval_required': 'Reviewer approval needed',
  'taxonomy_lookup_missing': 'No taxonomy lookup ran',
  'taxonomy_unresolved': 'Taxonomy not resolved to one accepted name',
};

void main() {
  test("every one of the policy's codes reads in words", () {
    for (final MapEntry<String, String> reason in policyReasons.entries) {
      expect(reasonLabel(reason.key), reason.value, reason: reason.key);
    }
  });

  test('a code with a suffix keeps the field it names', () {
    expect(
      reasonLabel('mandatory_unresolved:country'),
      'Required field has no supported value: country',
    );
  });

  test('an identifier suffix is left out', () {
    expect(
      reasonLabel(
        'independent_observations_missing:7fb0fadb-9e9e-4941-92af-70fd1e197e9d',
      ),
      'Two independent readings needed',
    );
  });

  test('a code this client does not know reads as its own words', () {
    expect(reasonLabel('new_rule_fired'), 'New rule fired');
  });

  test("G45's reason says what the value doesn't look like", () {
    for (final (String code, String words) in <(String, String)>[
      ('value_shape_mismatch:collectors', "Doesn't look like a collector"),
      ('value_shape_mismatch:habitat', "Doesn't look like a habitat"),
      (
        'value_shape_mismatch:collection_code',
        "Doesn't look like a collection code",
      ),
      (
        'value_shape_mismatch:elevation_note',
        "Doesn't look like an elevation note",
      ),
    ]) {
      expect(reasonLabel(code), words, reason: code);
    }
    expect(
      suffixedReasonCodes,
      contains('value_shape_mismatch'),
      reason: 'stored with its field, so the picker leaves it out until T5',
    );
  });

  test("the queue's rows read the words", () {
    expect(
      queueReason(
        Specimen(const <String, dynamic>{
          'reason_codes': <String>[
            'human_approval_required',
            'mandatory_unresolved:country',
          ],
        }),
      ),
      'Reviewer approval needed, '
      'Required field has no supported value: country',
    );
  });

  test('the blockers list reads the words', () {
    final List<ClearanceBlocker> blockers = blockersFor(
      Specimen(const <String, dynamic>{
        'reason_codes': <String>['taxonomy_unresolved'],
      }),
    );
    expect(
      blockers.map((ClearanceBlocker b) => b.message),
      contains('Taxonomy not resolved to one accepted name'),
    );
  });

  testWidgets('the Issue picker offers only codes a filter can find', (
    WidgetTester tester,
  ) async {
    // Until S5's T5 search matches `code:suffix`, a picked code stored with a
    // suffix would find nothing (the coordinator's ruling (b), 2026-09-24).
    await pumpComponent(
      tester,
      SingleChildScrollView(
        child: SearchFilters(
          initial: const <String, String>{},
          configuration: <String, dynamic>{
            'reason_codes': policyReasons.keys.toList(),
          },
        ),
      ),
      size: const Size(1000, 2400),
    );
    final UiSelect<String> issue = tester.widget<UiSelect<String>>(
      find.byWidgetPredicate(
        (Widget w) => w is UiSelect<String> && w.label == 'Issue',
      ),
    );
    final Set<String> offered = <String>{
      for (final UiSelectOption<String> option in issue.options)
        if (option.value.isNotEmpty) option.value,
    };
    expect(offered, <String>{
      'institutional_policy_unapproved',
      'mandatory_semantics_unconfirmed',
      'label_coverage_unconfirmed',
      'date_order',
      'date_precision_requires_review',
      'identifier_format',
      'human_approval_required',
      'taxonomy_lookup_missing',
      'taxonomy_unresolved',
    });
    expect(
      issue.options.map((UiSelectOption<String> o) => o.label),
      contains('Reviewer approval needed'),
    );
  });
}
