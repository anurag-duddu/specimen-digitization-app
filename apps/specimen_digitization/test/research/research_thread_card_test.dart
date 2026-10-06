import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/research/derivation_models.dart';
import 'package:specimen_digitization/src/research/research_controller.dart';
import 'package:specimen_digitization/src/research/research_models.dart';
import 'package:specimen_digitization/src/research/research_review_block.dart';
import 'package:specimen_digitization/src/research/research_thread_card.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/widgets/evidence_drawer.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'research_fixture.dart';

Future<void> pumpResearchCard(
  WidgetTester tester,
  ResearchThreadCard card, {
  double width = 640,
  double scale = 1,
  bool dark = false,
}) async {
  tester.view.physicalSize = Size(width, 1000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: dark ? AppTheme.dark() : AppTheme.light(),
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(context).copyWith(
            textScaler: TextScaler.linear(scale),
            disableAnimations: true,
          ),
          child: Scaffold(
            body: SingleChildScrollView(
              child: Padding(padding: const EdgeInsets.all(8), child: card),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

ResearchThreadCard readyCard({
  ResearchFieldThread? field,
  VoidCallback? onRetry,
  ValueChanged<ResearchReviewCandidate>? onSelectCandidate,
  bool fieldCentered = false,
  bool paused = false,
  bool unknown = false,
  bool readOnly = false,
  bool historical = false,
  int? canonicalRevision,
  int? reviewSavedRevision,
  ResearchNetworkState state = ResearchNetworkState.ready,
}) => ResearchThreadCard(
  scope: trustedResearchScope(),
  recordRevision: 100,
  fieldKey: 'taxon',
  fieldLabel: 'Taxon',
  field: field ?? fixtureThread().field('taxon'),
  historical: historical,
  canonicalRevision: canonicalRevision,
  reviewSavedRevision: reviewSavedRevision,
  networkState: state,
  paused: paused,
  hasUnknownState: unknown,
  readOnly: readOnly,
  onRetry: onRetry,
  onSelectCandidate: onSelectCandidate,
  fieldCentered: fieldCentered,
  onRefresh: () {},
);

// Local widget variations over the frozen DTO. This helper does not emit a
// server-route fixture or establish server authority for the varied values.
ResearchFieldThread preservedWidgetField({
  String fieldKey = 'city',
  String state = 'unknown',
  String? literal,
  String? parsed,
  String? normalized,
  String reason = 'The saved review deliberately leaves this field unknown.',
  String fieldReason = 'The label does not support a value.',
  String actor = 'ordinary-reviewer',
  String originRunId = 'original-run',
  String originEventId = 'genuine-review-event',
  String? authorityIdentityJson,
}) {
  final threadJson = researchFixture('server-preserved-human-thread');
  final scope = ResearchScope.fromJson(threadJson['scope']);
  final base = threadJson['preserved_human_base'] as Map<String, dynamic>;
  final original = <String, dynamic>{
    ...fixtureField(threadJson, fieldKey)['value'] as Map<String, dynamic>,
    'state': state,
    'literal': literal,
    'parsed': parsed,
    'normalized': normalized,
    'reason': fieldReason,
    'evidence_ids': <String>[],
    'evidence_relations': <String, String>{},
    if (authorityIdentityJson != null)
      'authority_identity': {'raw_numeric_marker': 'widget-numeric-marker'},
  };
  final evidenceId = 'recorded-human-carry-$fieldKey';
  final current = <String, dynamic>{
    ...original,
    'evidence_ids': [evidenceId],
    'evidence_relations': {evidenceId: 'decides'},
  };
  final varied = <String, dynamic>{
    'field_key': fieldKey,
    'work_state': 'waiting_human',
    'value': current,
    'checkpoint': null,
    'blocker_code': 'preserved_human_decision',
    'actions': <String>[],
    'preserved_human': {
      'contract_version': 'preserved-human-field/v1',
      'field_key': fieldKey,
      'value': current,
      'original_value': original,
      'organization_id': scope.organizationId,
      'collection_id': scope.collectionId,
      'specimen_id': scope.specimenId,
      'canonical_run_id': base['canonical_run_id'],
      'fresh_run_revision': 32,
      'origin_run_id': originRunId,
      'origin_event_id': originEventId,
      'origin_revision': 31,
      'actor': actor,
      'reason': reason,
      'created_at': '2026-10-06T14:05:00Z',
      'original_evidence_ids': <String>[],
      'carry_digest': 'b' * 64,
      'proof_digest': 'c' * 64,
      'source_sha256': base['source_sha256'],
    },
  };
  final target = fixtureField(threadJson, fieldKey);
  target
    ..clear()
    ..addAll(varied);
  final outcomes = <String, dynamic>{
    for (final field
        in (threadJson['fields'] as List).cast<Map<String, dynamic>>())
      if (field['preserved_human'] != null)
        field['field_key'] as String: field['preserved_human'],
  };
  var raw = jsonEncode(_canonicalWidgetValue(outcomes));
  if (authorityIdentityJson != null) {
    // Insert numeric metadata as exact text before creating display
    // projections, so web decoding cannot redefine the raw provenance.
    raw = raw.replaceAll(
      '{"raw_numeric_marker":"widget-numeric-marker"}',
      authorityIdentityJson,
    );
  }
  final projections = jsonDecode(raw) as Map<String, dynamic>;
  for (final field
      in (threadJson['fields'] as List).cast<Map<String, dynamic>>()) {
    final projected = projections[field['field_key']];
    if (projected != null) {
      field['preserved_human'] = projected;
      field['value'] = (projected as Map<String, dynamic>)['value'];
    }
  }
  base
    ..['registration_record_revision'] = 32
    ..['outcomes_json'] = raw
    ..['outcome_digest'] = sha256.convert(utf8.encode(raw)).toString();
  return ResearchThread.fromJson(
    threadJson,
    expectedScope: scope,
  ).field(fieldKey)!;
}

Object? _canonicalWidgetValue(Object? value) {
  if (value is Map) {
    final keys = value.keys.cast<String>().toList()..sort();
    return {for (final key in keys) key: _canonicalWidgetValue(value[key])};
  }
  if (value is List) return value.map(_canonicalWidgetValue).toList();
  return value;
}

ResearchThreadCard preservedWidgetCard({
  ResearchFieldThread? field,
  int recordRevision = 32,
  bool fieldCentered = false,
  bool historical = false,
  bool readOnly = false,
  bool paused = false,
  ResearchNetworkState state = ResearchNetworkState.ready,
  VoidCallback? onRetry,
  ValueChanged<ResearchReviewCandidate>? onSelectCandidate,
  List<ResearchDerivationProposal> proposals = const [],
  bool canSelectProposals = false,
}) {
  final retained = field ?? preservedWidgetField();
  return ResearchThreadCard(
    scope: retained.scope,
    recordRevision: recordRevision,
    fieldKey: retained.fieldKey,
    fieldLabel: retained.fieldKey == 'city' ? 'City' : 'Elevation',
    field: retained,
    fieldCentered: fieldCentered,
    historical: historical,
    readOnly: readOnly,
    paused: paused,
    networkState: state,
    onRetry: onRetry,
    onSelectCandidate: onSelectCandidate,
    derivationProposals: proposals,
    canSelectDerivationProposals: canSelectProposals,
    onRefresh: () {},
  );
}

ResearchDerivationProposal preservedWidgetProposal() =>
    ResearchDerivationProposal.fromJson({
      'field_key': 'city',
      'value': 'Separately grounded city proposal',
      'value_layer': 'derived',
      'input_fields': ['country'],
      'input_revisions': [
        ['country', 32],
      ],
      'evidence_ids': ['grounded-proposal-evidence'],
      'authority_id': 'proposal-authority',
      'dataset_ids': ['proposal-dataset'],
      'tool_call_id': 'synthetic-proposal-call',
      'rule_version': 'proposal-rule/v1',
      'selection_id': 'e' * 64,
    });

void main() {
  for (final fieldKey in ['city', 'elevation_from_m']) {
    for (final centered in [false, true]) {
      testWidgets('server-route preserved $fieldKey decision stays human in '
          '${centered ? 'field' : 'full'} presentation', (tester) async {
        var retries = 0;
        var selections = 0;
        final json = researchFixture('server-preserved-human-thread');
        final scope = ResearchScope.fromJson(json['scope']);
        final thread = ResearchThread.fromJson(json, expectedScope: scope);
        final field = thread.field(fieldKey)!;
        final outcome = field.preservedHumanOutcome!;
        await pumpResearchCard(
          tester,
          preservedWidgetCard(
            field: field,
            recordRevision:
                thread.preservedHumanBase!.registrationRecordRevision,
            fieldCentered: centered,
            onRetry: () => retries++,
            onSelectCandidate: (_) => selections++,
          ),
        );
        expect(find.text('Preserved human decision'), findsOneWidget);
        await tester.tap(find.text('Research'));
        await tester.pump();
        expect(find.text('Preserved human decision'), findsOneWidget);
        expect(
          find.text('Unknown. Preserved from the saved review'),
          findsOneWidget,
        );
        expect(find.text('checked original label'), findsOneWidget);
        expect(
          find.text(
            fieldKey == 'city'
                ? 'slope is not a city'
                : 'feet are not asserted metres',
          ),
          findsOneWidget,
        );
        expect(find.text(outcome.actor), findsOneWidget);
        expect(find.text(outcome.createdAt), findsOneWidget);
        for (final misleading in [
          'Research value',
          'No supported value yet.',
          'Needs information',
          'Why it is unresolved',
          'Sources searched',
          'Sources checked',
          'No source has settled this field yet.',
          'Public sources could not settle this field.',
          'Research details',
          'Retry field',
          'Retry',
          'Use this possibility',
        ]) {
          expect(find.text(misleading), findsNothing);
        }
        expect(find.byType(ResearchReviewBlock), findsNothing);
        expect(find.textContaining('research blocker'), findsNothing);
        final drawer = tester.widget<EvidenceDrawer>(
          find.byType(EvidenceDrawer),
        );
        expect(
          (drawer.payload as Map)['outcomes_json'],
          (json['preserved_human_base'] as Map)['outcomes_json'],
        );
        expect((drawer.payload as Map).containsKey('preserved_human'), isFalse);
        await tester.ensureVisible(find.text('Saved review history'));
        await tester.tap(find.text('Saved review history'));
        await tester.pump();
        expect(find.text(outcome.originRunId), findsOneWidget);
        expect(find.text(outcome.originEventId), findsOneWidget);
        expect(
          find.text('Review saved at revision ${outcome.originRevision}'),
          findsOneWidget,
        );
        await tester.ensureVisible(find.text('Preservation in this run'));
        await tester.tap(find.text('Preservation in this run'));
        await tester.pump();
        expect(find.text(outcome.canonicalRunId), findsOneWidget);
        expect(
          find.text('Preserved at revision ${outcome.freshRunRevision}.'),
          findsOneWidget,
        );
        expect(find.text(outcome.proofDigest), findsOneWidget);
        expect(retries, 0);
        expect(selections, 0);
        expect(tester.takeException(), isNull);
      });
    }
  }

  testWidgets('saved supported value keeps its layers and distinct reasons', (
    tester,
  ) async {
    final field = preservedWidgetField(
      state: 'supported',
      literal: 'Original literal value',
      parsed: 'Original parsed value',
      normalized: 'Original normalized value',
    );
    await pumpResearchCard(tester, preservedWidgetCard(field: field));
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(find.text('Original normalized value'), findsOneWidget);
    expect(find.text('Review reason'), findsOneWidget);
    expect(find.text('Saved field reason'), findsOneWidget);
    await tester.tap(find.text('Saved review history'));
    await tester.pump();
    expect(find.text('Original literal value'), findsOneWidget);
    expect(find.text('Original parsed value'), findsOneWidget);
    expect(find.text('Original normalized value'), findsNWidgets(2));
    expect(find.text('Research value'), findsNothing);
    expect(find.text('Resolved from evidence'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('bounded saved text declares excerpts and keeps full details', (
    tester,
  ) async {
    final reason = 'Human reason ' * 100;
    final actor = 'reviewer' * 100;
    final event = 'event' * 100;
    final run = 'run' * 100;
    final value = 'Supported value ' * 100;
    final field = preservedWidgetField(
      state: 'supported',
      normalized: value,
      reason: reason,
      actor: actor,
      originEventId: event,
      originRunId: run,
    );
    await pumpResearchCard(
      tester,
      preservedWidgetCard(field: field, fieldCentered: true),
      width: 320,
      scale: 2,
    );
    await tester.tap(find.text('Research'));
    await tester.pump();
    for (final label in ['Saved field value', 'Review reason', 'Saved by']) {
      expect(
        find.text('$label (excerpt; full text in saved review details)'),
        findsOneWidget,
      );
    }
    await tester.ensureVisible(find.text('Saved review history'));
    await tester.tap(find.text('Saved review history'));
    await tester.pump();
    for (final label in ['Original run', 'Review event']) {
      expect(
        find.text('$label (excerpt; full text in saved review details)'),
        findsOneWidget,
      );
    }
    final drawer = tester.widget<EvidenceDrawer>(find.byType(EvidenceDrawer));
    final raw = (drawer.payload as Map)['outcomes_json'] as String;
    final retained = (jsonDecode(raw) as Map)['city'] as Map;
    expect(retained['reason'], reason);
    expect(retained['actor'], actor);
    expect(retained['origin_event_id'], event);
    expect(retained['origin_run_id'], run);
    expect((retained['value'] as Map)['normalized'], value);
    final semantics = tester.ensureSemantics();
    try {
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    } finally {
      semantics.dispose();
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('saved provenance export retains exact raw numeric metadata', (
    tester,
  ) async {
    const authorityIdentityJson =
        '{"floating":1.0,"integer":1,"large_integer":9007199254740993}';
    final field = preservedWidgetField(
      state: 'supported',
      normalized: 'A saved human value',
      authorityIdentityJson: authorityIdentityJson,
    );
    final raw = field.preservedHumanOutcomesJson!;
    await pumpResearchCard(
      tester,
      preservedWidgetCard(field: field, fieldCentered: true),
    );
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(find.text('A saved human value'), findsOneWidget);
    final drawer = tester.widget<EvidenceDrawer>(find.byType(EvidenceDrawer));
    final payload = drawer.payload as Map;
    expect(payload.keys, ['outcomes_json']);
    expect(payload['outcomes_json'], raw);
    final pretty = EvidenceDrawer.pretty(payload);
    final copiedRaw = (jsonDecode(pretty) as Map)['outcomes_json'] as String;
    expect(utf8.encode(copiedRaw), utf8.encode(raw));
    expect(copiedRaw, contains('"floating":1.0'));
    expect(copiedRaw, contains('"integer":1'));
    expect(copiedRaw, contains('"large_integer":9007199254740993'));
    expect(pretty, isNot(contains('9007199254740992')));
    expect(payload.containsKey('preserved_human'), isFalse);
    expect(payload.containsKey('original_value'), isFalse);
  });

  testWidgets('isolated field does not export projected metadata as original', (
    tester,
  ) async {
    final json = researchFixture('server-preserved-human-thread');
    final scope = ResearchScope.fromJson(json['scope']);
    final isolated = ResearchFieldThread.fromJson(
      fixtureField(json, 'city'),
      scope,
    );
    expect(isolated.preservedHumanOutcomesJson, isNull);
    await pumpResearchCard(tester, preservedWidgetCard(field: isolated));
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(
      find.text('Unknown. Preserved from the saved review'),
      findsOneWidget,
    );
    expect(find.byType(EvidenceDrawer), findsNothing);
    expect(
      find.text('Full saved provenance is unavailable for this view.'),
      findsOneWidget,
    );
  });

  testWidgets(
    'separate suggestion requires an explicit ordinary review choice',
    (tester) async {
      final proposal = preservedWidgetProposal();
      ResearchReviewCandidate? selected;
      await pumpResearchCard(
        tester,
        preservedWidgetCard(
          fieldCentered: true,
          proposals: [proposal],
          canSelectProposals: true,
          onSelectCandidate: (candidate) => selected = candidate,
        ),
      );
      await tester.tap(find.text('Research'));
      await tester.pump();
      expect(selected, isNull);
      expect(
        find.text('Unknown. Preserved from the saved review'),
        findsOneWidget,
      );
      final block = tester.widget<ResearchReviewBlock>(
        find.byType(ResearchReviewBlock),
      );
      expect(block.field, isNull);
      expect(block.canSelectCandidates, isFalse);
      block.onSelectCandidate!(
        ResearchReviewCandidate.fromJson({
          'label': 'Native source possibility',
          'source_id': 'gbif',
          'selection_id': proposal.selectionId,
          'selection_value': proposal.value,
        }),
      );
      expect(selected, isNull);
      await tester.ensureVisible(find.text('Use this suggestion'));
      await tester.tap(find.text('Use this suggestion'));
      await tester.pump();
      expect(selected?.selectionId, proposal.selectionId);
      expect(selected?.selectionValue, proposal.value);
      expect(
        find.text('Unknown. Preserved from the saved review'),
        findsOneWidget,
      );
    },
  );

  testWidgets('historical carry keeps separate suggestions read-only', (
    tester,
  ) async {
    var selections = 0;
    await pumpResearchCard(
      tester,
      preservedWidgetCard(
        historical: true,
        fieldCentered: true,
        proposals: [preservedWidgetProposal()],
        canSelectProposals: true,
        onSelectCandidate: (_) => selections++,
      ),
    );
    await tester.tap(find.text('Research'));
    await tester.pump();
    final button = tester.widget<UiButton>(
      find.widgetWithText(UiButton, 'Use this suggestion'),
    );
    expect(button.onPressed, isNull);
    expect(selections, 0);
    expect(
      find.text('Unknown. Preserved from the saved review'),
      findsOneWidget,
    );
    expect(find.text('Research value'), findsNothing);
  });

  testWidgets('selectable possibility returns its verified source candidate', (
    tester,
  ) async {
    final json = researchFixture('failed-thread');
    final taxon = fixtureField(json, 'taxon');
    taxon['work_state'] = 'waiting_human';
    taxon['checkpoint']['resolution']['work_state'] = 'waiting_human';
    taxon['actions'] = ['review_proposal'];
    taxon['review'] = {
      'question_reason': 'semantic_ambiguity',
      'reason': 'Two source possibilities remain.',
      'question': {
        'field_key': 'taxon',
        'question': 'Which retained source candidate is supported?',
        'reason': 'semantic_ambiguity',
        'coverage': [
          {
            'source_id': 'gbif',
            'field_key': 'taxon',
            'state': 'exhausted',
            'source_version': 'test-v1',
            'qualification_digest': 'a' * 64,
            'exact_join_attempted': true,
            'query_digest': 'b' * 64,
            'receipt_ids': ['coverage-receipt'],
            'candidate_count': 1,
            'coverage_limit': 'bounded test scope',
            'reason': 'Search completed within the fixture scope',
          },
        ],
        'evidence_ids': ['source-evidence'],
      },
      'evidence': [
        {
          'evidence_id': 'source-evidence',
          'source_id': 'geolocate',
          'kind': 'lookup',
          'outcome': 'ambiguous',
        },
      ],
      'candidates': [
        {
          'label': 'Mindanao',
          'source_id': 'geolocate',
          'selection_id': 'b' * 64,
          'selection_value': 'Philippines',
          'evidence_id': 'source-evidence',
        },
      ],
      'evidence_not_shown': 0,
      'candidates_not_shown': 0,
    };
    taxon['checkpoint']['resolution']['question'] = taxon['review'].remove(
      'question',
    );
    final field = ResearchThread.fromJson(
      json,
      expectedScope: trustedResearchScope(),
    ).field('taxon')!;
    ResearchReviewCandidate? selected;
    await pumpResearchCard(
      tester,
      readyCard(
        field: field,
        fieldCentered: true,
        onSelectCandidate: (candidate) => selected = candidate,
      ),
    );
    await tester.tap(find.text('Research'));
    await tester.pumpAndSettle();
    expect(find.text('Mindanao'), findsOneWidget);
    expect(find.text('Proposed field value'), findsOneWidget);
    expect(find.text('Philippines'), findsOneWidget);
    await tester.tap(find.text('Use this possibility'));
    await tester.pump();
    expect(selected?.selectionId, 'b' * 64);
    expect(selected?.label, 'Mindanao');
    expect(selected?.selectionValue, 'Philippines');
  });

  testWidgets('historical report shows its saved revisions and disables choice', (
    tester,
  ) async {
    final json = researchFixture('failed-thread')
      ..['historical'] = true
      ..['canonical_revision'] = 41
      ..['review_saved_revision'] = 42;
    final taxon = fixtureField(json, 'taxon');
    taxon['work_state'] = 'waiting_human';
    taxon['checkpoint']['resolution']['work_state'] = 'waiting_human';
    taxon['actions'] = ['review_proposal'];
    taxon['review'] = {
      'question_reason': 'semantic_ambiguity',
      'reason': 'Two source possibilities remain.',
      'evidence': [],
      'candidates': [
        {
          'label': 'Mindanao',
          'source_id': 'geolocate',
          'selection_id': 'c' * 64,
          'selection_value': 'Philippines',
        },
      ],
      'evidence_not_shown': 0,
      'candidates_not_shown': 0,
    };
    final resolution = taxon['checkpoint']['resolution'] as Map;
    resolution['question'] = {
      'field_key': 'taxon',
      'question': 'Which retained source candidate is supported?',
      'reason': 'semantic_ambiguity',
      'coverage': [
        {
          'source_id': 'gbif',
          'field_key': 'taxon',
          'state': 'exhausted',
          'source_version': 'test-v1',
          'qualification_digest': 'a' * 64,
          'exact_join_attempted': true,
          'query_digest': 'b' * 64,
          'receipt_ids': ['coverage-receipt'],
          'candidate_count': 1,
          'coverage_limit': 'bounded test scope',
          'reason': 'Search completed within the fixture scope',
        },
      ],
    };
    final thread = ResearchThread.fromJson(
      json,
      expectedScope: trustedResearchScope(),
    );
    var selections = 0;
    await pumpResearchCard(
      tester,
      readyCard(
        field: thread.field('taxon'),
        fieldCentered: true,
        historical: thread.historical,
        canonicalRevision: thread.canonicalRevision,
        reviewSavedRevision: thread.reviewSavedRevision,
        onSelectCandidate: (_) => selections++,
      ),
    );
    expect(find.textContaining('Historical report ·'), findsOneWidget);
    await tester.tap(find.text('Research'));
    await tester.pumpAndSettle();
    expect(
      find.textContaining('record revision 41; review saved at revision 42'),
      findsOneWidget,
    );
    final button = tester.widget<UiButton>(
      find.widgetWithText(UiButton, 'Use this possibility'),
    );
    expect(button.onPressed, isNull);
    expect(
      button.disabledReason,
      'This field is read-only or the research result is no longer actionable.',
    );
    expect(selections, 0);
  });

  testWidgets('collapsed disclosure is lazy and touch reveal requests once', (
    tester,
  ) async {
    var reads = 0;
    await pumpResearchCard(
      tester,
      ResearchThreadCard(
        scope: trustedResearchScope(),
        recordRevision: 100,
        fieldKey: 'taxon',
        fieldLabel: 'Taxon',
        onLoad: () => reads++,
      ),
    );
    expect(reads, 0);
    expect(find.text('As written'), findsNothing);
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(reads, 1);
    expect(find.byType(SingleChildScrollView), findsOneWidget);
    expect(find.byType(UiDisclosure), findsOneWidget);
    expect(find.byType(Surface), findsWidgets);
  });

  testWidgets('keyboard disclosure reveal and advertised retry work', (
    tester,
  ) async {
    var retries = 0;
    await pumpResearchCard(tester, readyCard(onRetry: () => retries++));
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(find.text('As written'), findsOneWidget);
    await tester.tap(find.text('Retry field'));
    await tester.pump();
    expect(retries, 1);
  });

  for (final disabled in [
    'paused',
    'unknown',
    'historical',
    'busy',
    'blocked',
  ]) {
    testWidgets('disabled retry cannot activate: $disabled', (tester) async {
      var retries = 0;
      var field = fixtureThread().field('taxon')!;
      if (disabled == 'blocked') {
        final json = researchFixture('failed-thread');
        fixtureField(json, 'taxon')['blocker_code'] = 'research_retry_blocked';
        field = ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ).field('taxon')!;
      }
      await pumpResearchCard(
        tester,
        readyCard(
          field: field,
          onRetry: () => retries++,
          paused: disabled == 'paused',
          unknown: disabled == 'unknown',
          readOnly: disabled == 'historical',
          state: disabled == 'busy'
              ? ResearchNetworkState.submitting
              : ResearchNetworkState.ready,
        ),
      );
      await tester.tap(find.text('Research'));
      await tester.pump();
      final button = tester.widget<UiButton>(
        find.widgetWithText(
          UiButton,
          disabled == 'busy' ? 'Queuing retry' : 'Retry field',
        ),
      );
      expect(button.onPressed, isNull);
      if (disabled == 'blocked') {
        expect(find.textContaining('Retry blocked.'), findsOneWidget);
        expect(button.disabledReason, 'Retry is blocked for this field.');
      }
      expect(retries, 0);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets(
    'prerequisite, question and policy exception remain visible without new actions',
    (tester) async {
      final json = researchFixture('failed-thread');
      final raw = fixtureField(json, 'taxon');
      raw['work_state'] = 'waiting_human';
      raw['actions'] = ['supply_information', 'review_proposal'];
      final resolution = raw['checkpoint']['resolution'] as Map;
      resolution['work_state'] = 'waiting_human';
      resolution['source_coverage'] = [
        {
          'source_id': 'labels',
          'field_key': 'taxon',
          'state': 'exhausted',
          'source_version': 'v1',
          'coverage_limit': 'Current label only',
          'qualification_digest': 'a' * 64,
          'exact_join_attempted': true,
          'exact_join_proven': true,
          'query_digest': 'b' * 64,
          'receipt_ids': ['synthetic-label-search-receipt'],
          'candidate_count': 0,
          'reason': 'No additional supported value',
        },
      ];
      resolution['question'] = {
        'field_key': 'taxon',
        'question': 'Which reading is correct?',
        'reason': 'semantic_ambiguity',
        'coverage': resolution['source_coverage'],
      };
      resolution['exception'] = {
        'field_key': 'taxon',
        'dependency': 'qualified source',
        'policy_version': 'v1',
        'reason': 'Source unavailable',
        'reevaluate_when': 'Source becomes available',
      };
      final field = ResearchThread.fromJson(
        json,
        expectedScope: trustedResearchScope(),
      ).field('taxon');
      await pumpResearchCard(tester, readyCard(field: field));
      await tester.tap(find.text('Research'));
      await tester.pump();
      expect(find.text('Which reading is correct?'), findsOneWidget);
      expect(find.textContaining('Current label only'), findsOneWidget);
      expect(find.textContaining('Policy exception:'), findsOneWidget);
      expect(
        find.textContaining('not available in this view yet'),
        findsNWidgets(2),
      );
      expect(find.widgetWithText(UiButton, 'Supply information'), findsNothing);
      expect(find.widgetWithText(UiButton, 'Review proposal'), findsNothing);
    },
  );

  testWidgets(
    'retains all three value layers and evidence without a review mutation',
    (tester) async {
      final json = researchFixture('failed-thread');
      final country = fixtureField(json, 'country');
      final value = <String, dynamic>{
        ...country['value'] as Map<String, dynamic>,
        'literal': 'Written layer',
        'parsed': 'Interpreted layer',
        'normalized': 'Standardized layer',
      };
      country['value'] = value;
      country['checkpoint']['resolution']['value'] = value;
      final field = ResearchThread.fromJson(
        json,
        expectedScope: trustedResearchScope(),
      ).field('country');
      await pumpResearchCard(
        tester,
        ResearchThreadCard(
          scope: trustedResearchScope(),
          recordRevision: 100,
          fieldKey: 'country',
          fieldLabel: 'Country',
          field: field,
          networkState: ResearchNetworkState.ready,
          onRefresh: () {},
        ),
      );
      await tester.tap(find.text('Research'));
      await tester.pump();
      for (final text in [
        'Written layer',
        'Interpreted layer',
        'Standardized layer',
      ]) {
        expect(find.text(text), findsOneWidget);
      }
      expect(find.text('1 evidence reference'), findsOneWidget);
      expect(find.text('Approve'), findsNothing);
    },
  );

  testWidgets('loading, denial and wrong field binding hide value layers', (
    tester,
  ) async {
    for (final state in [
      ResearchNetworkState.loading,
      ResearchNetworkState.error,
      ResearchNetworkState.denied,
    ]) {
      await pumpResearchCard(tester, readyCard(state: state));
      await tester.tap(find.text('Research'));
      await tester.pump();
      expect(find.text('As written'), findsNothing);
      expect(tester.takeException(), isNull);
    }
    await pumpResearchCard(
      tester,
      readyCard(field: fixtureThread().field('country')),
    );
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(find.text('Synthetic country'), findsNothing);
    expect(find.textContaining('could not be verified'), findsWidgets);
  });

  for (final width in [320.0, 768.0]) {
    for (final scale in [1.0, 2.0]) {
      for (final dark in [false, true]) {
        testWidgets('fits width ${width.toString()} scale '
            '${scale.toString()}${dark ? ' dark' : ' light'}', (tester) async {
          await pumpResearchCard(
            tester,
            readyCard(onRetry: () {}),
            width: width,
            scale: scale,
            dark: dark,
          );
          await tester.tap(find.text('Research'));
          await tester.pump();
          expect(tester.takeException(), isNull);
          expect(find.byType(SingleChildScrollView), findsOneWidget);
          final semantics = tester.ensureSemantics();
          try {
            await expectLater(
              tester,
              meetsGuideline(androidTapTargetGuideline),
            );
            await expectLater(
              tester,
              meetsGuideline(labeledTapTargetGuideline),
            );
          } finally {
            semantics.dispose();
          }
        });
      }
    }
  }

  for (final source in <String, String>{
    'global_names_verifier': 'Global Names Verifier',
    'catalogue_of_life': 'Catalogue of Life',
    'gbif': 'GBIF',
    'bugguide': 'BugGuide',
    'mapcarta': 'Mapcarta',
    'geolocate': 'GEOLocate',
    'field_museum_ipt': 'Field Museum IPT',
    'field_museum_emudata': 'Field Museum EMu data',
    'unknown_registry_source': 'Research source',
    // Retired 2026-10-03 (owner G-geo-1); a stored row reads generically.
    'google_maps': 'Research source',
  }.entries) {
    testWidgets(
      'displays approved source name and scope without raw provenance codes: '
      '${source.key}',
      (tester) async {
        final json = researchFixture('failed-thread');
        final raw = fixtureField(json, 'taxon');
        raw['work_state'] = 'waiting_source';
        raw['actions'] = [];
        raw['blocker_code'] = 'source_prerequisite';
        raw['checkpoint']['resolution']['work_state'] = 'waiting_source';
        raw['checkpoint']['resolution']['source_coverage'] = [
          {
            'source_id': source.key,
            'field_key': 'taxon',
            'state': 'unqualified',
            'source_version': 'v1',
            'coverage_limit': 'Current input and collection only',
            'reason': 'scope_join_not_proven',
          },
        ];
        final field = ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ).field('taxon')!;
        await pumpResearchCard(tester, readyCard(field: field));
        await tester.tap(find.text('Research'));
        await tester.pump();
        expect(find.textContaining('${source.value}:'), findsOneWidget);
        expect(
          find.textContaining('Source needs qualification before use.'),
          findsOneWidget,
        );
        expect(
          find.textContaining('Scope: Current input and collection only'),
          findsOneWidget,
        );
        expect(find.textContaining(source.key), findsNothing);
        expect(find.textContaining('scope_join_not_proven'), findsNothing);
        expect(find.textContaining('unqualified'), findsNothing);
        expect(
          field.checkpoint!.resolution.sourceCoverage.single.sourceId,
          source.key,
        );
        expect(
          field.checkpoint!.resolution.sourceCoverage.single.reason,
          'scope_join_not_proven',
        );
        expect(
          find.widgetWithText(UiButton, 'Supply information'),
          findsNothing,
        );
        expect(find.widgetWithText(UiButton, 'Review proposal'), findsNothing);
        expect(find.widgetWithText(UiButton, 'Retry field'), findsNothing);
      },
    );
  }

  for (final state in <String, String>{
    'not_attempted': 'Search has not started.',
    'unqualified': 'Source needs qualification before use.',
    'inaccessible': 'Source is unavailable.',
    'schema_only':
        'Source structure is available; records have not been searched.',
    'failed': 'Search could not be completed.',
    'searched': 'Search completed.',
    'exhausted': 'Search completed within the recorded scope.',
  }.entries) {
    testWidgets(
      'describes scoped source state without inventing absence: ${state.key}',
      (tester) async {
        final json = researchFixture('failed-thread');
        final raw = fixtureField(json, 'taxon');
        raw['work_state'] = 'waiting_source';
        raw['actions'] = [];
        raw['checkpoint']['resolution']['work_state'] = 'waiting_source';
        raw['checkpoint']['resolution']['source_coverage'] = [
          {
            'source_id': 'gbif',
            'field_key': 'taxon',
            'state': state.key,
            'source_version': 'v1',
            'coverage_limit': 'Typed name query only',
            if (state.key == 'exhausted') 'qualification_digest': 'a' * 64,
            if (state.key == 'exhausted') 'exact_join_attempted': true,
            if (state.key == 'exhausted') 'exact_join_proven': true,
            if (state.key == 'exhausted') 'query_digest': 'b' * 64,
            if (state.key == 'exhausted')
              'receipt_ids': ['synthetic-name-query-receipt'],
            if (state.key == 'exhausted') 'candidate_count': 0,
            'reason': 'transport_or_policy_code',
          },
        ];
        final field = ResearchThread.fromJson(
          json,
          expectedScope: trustedResearchScope(),
        ).field('taxon');
        await pumpResearchCard(tester, readyCard(field: field));
        await tester.tap(find.text('Research'));
        await tester.pump();
        expect(find.textContaining(state.value), findsOneWidget);
        expect(
          find.textContaining('Scope: Typed name query only'),
          findsOneWidget,
        );
        expect(find.textContaining('transport_or_policy_code'), findsNothing);
        expect(find.textContaining('No supported value'), findsNothing);
        expect(find.text('Which reading is correct?'), findsNothing);
        expect(
          find.widgetWithText(UiButton, 'Supply information'),
          findsNothing,
        );
        expect(find.widgetWithText(UiButton, 'Review proposal'), findsNothing);
      },
    );
  }

  for (final width in [320.0, 640.0]) {
    for (final state in [
      ResearchNetworkState.error,
      ResearchNetworkState.denied,
    ]) {
      testWidgets('network state has accurate disabled explanations at width '
          '${width.toString()}: ${state.name}', (tester) async {
        await pumpResearchCard(
          tester,
          readyCard(state: state),
          width: width,
          scale: 2,
        );
        await tester.tap(find.text('Research'));
        await tester.pump();
        expect(find.widgetWithText(UiButton, 'Retry field'), findsNothing);
        expect(find.widgetWithText(UiButton, 'Retry'), findsNothing);
        expect(find.text('As written'), findsNothing);
        final refresh = tester
            .widgetList<UiButton>(find.byType(UiButton))
            .singleWhere((button) => button.label.startsWith('Refresh'));
        if (state == ResearchNetworkState.denied) {
          expect(refresh.onPressed, isNull);
          expect(refresh.disabledReason, 'Research access is unavailable.');
          expect(
            find.textContaining(
              'Research access is unavailable for this collection.',
            ),
            findsOneWidget,
          );
        } else {
          expect(refresh.onPressed, isNotNull);
          expect(refresh.disabledReason, isNull);
          expect(
            find.textContaining('Refresh before retrying this field.'),
            findsOneWidget,
          );
        }
      });
    }
  }

  testWidgets('record change recreates the disclosure collapsed', (
    tester,
  ) async {
    await pumpResearchCard(tester, readyCard(onRetry: () {}));
    await tester.tap(find.text('Research'));
    await tester.pump();
    expect(find.text('As written'), findsOneWidget);
    await pumpResearchCard(
      tester,
      ResearchThreadCard(
        scope: trustedResearchScope(),
        recordRevision: 101,
        fieldKey: 'taxon',
        fieldLabel: 'Taxon',
        field: fixtureThread().field('taxon'),
        networkState: ResearchNetworkState.ready,
      ),
    );
    expect(find.text('As written'), findsNothing);
  });
}
